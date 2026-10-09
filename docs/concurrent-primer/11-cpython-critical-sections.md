# CPython critical sections

In conventional concurrency terminology, a critical section is a region that remains exclusively locked from entry to exit. A **CPython critical section** has different semantics.

CPython critical sections are a deadlock-avoidance layer over `PyMutex`. They acquire per-object locks, but the runtime may temporarily suspend the section, release its locks, and reacquire them later.

The rule to remember is:

> A CPython critical section protects an object while its lock is held, but code must not assume that the object remains unchanged across an operation that can suspend the section.

Critical sections were added in Python 3.13. They lock in the free-threaded build and are no-ops in the default build. The [build-contract section](#critical-sections-are-no-ops-in-the-default-build) explains the consequences.

## Use critical sections for Python object state

An extension type can use its object's per-object lock to protect mutable fields:

```c
typedef struct {
    PyObject_HEAD
    PyObject *value;     /* Protected by this object's critical section. */
    uint64_t version;    /* Protected by this object's critical section. */
} HolderObject;
```

Use `self`'s critical section for every competing read or write of `self->value` and `self->version`. Keep checks and updates that depend on both fields together. For example, read `value` while holding that section:

```c
static PyObject *
Holder_get_value(HolderObject *self, void *closure)
{
    PyObject *result;

    Py_BEGIN_CRITICAL_SECTION(self);
    result = Py_XNewRef(self->value);
    Py_END_CRITICAL_SECTION();

    if (result == NULL) {
        Py_RETURN_NONE;
    }
    return result;
}
```

The strong reference keeps the result alive after the critical section ends. The critical section itself does not create a reference to `self` or to any pointer loaded from it. The caller must already keep `self` alive for the complete operation.

A writer follows the same locking rule:

```c
static int
Holder_set_value(HolderObject *self, PyObject *value)
{
    PyObject *old;

    Py_BEGIN_CRITICAL_SECTION(self);
    old = self->value;
    self->value = Py_XNewRef(value);
    self->version++;
    Py_END_CRITICAL_SECTION();

    Py_XDECREF(old);
    return 0;
}
```

The old reference is released after unlocking so that arbitrary deallocation code does not run while this operation depends on holding the object's lock.

## The macros form a lexical block

The single-object API uses a matching pair:

```c
Py_BEGIN_CRITICAL_SECTION(obj);
/* protected code */
Py_END_CRITICAL_SECTION();
```

The macros introduce a local C scope and private bookkeeping variables. The begin and end must appear as a matching pair in that scope.

Do not use `return`, `goto`, `break`, or `continue` to leave the section before the end macro. The begin macro opens a plain C block, not a loop. A `break` or `continue` that targets an enclosing loop skips the end macro:

```c
Py_BEGIN_CRITICAL_SECTION(obj);
if (error) {
    return NULL;  /* Wrong: skips Py_END_CRITICAL_SECTION(). */
}
Py_END_CRITICAL_SECTION();
```

Instead, record the result, end the section, and then return. Cleanup labels can be used only when their control flow preserves the macro's generated scope and always executes the matching end.

Testing only in the default build can hide these errors. Its no-op critical sections do not leave a lock held when an early exit skips the end macro.

The low-level `PyCriticalSection_Begin()` and `PyCriticalSection_End()` functions exist for cases where the C macros cannot be used. Their state structures are private bookkeeping, not general lock objects. Use them only in the same paired pattern as the macros.

## Each thread has a stack of critical sections

In a free-threaded build, CPython records critical sections in the attached `PyThreadState`. The stack includes active and suspended sections. Entering a section normally pushes its bookkeeping onto this per-thread stack. Ending it removes the top entry.

Some shortcuts do not push a new entry. Recursive entry can reuse locks held by the top-most section. During a stop-the-world pause, the slow acquisition path can also skip locking and stack bookkeeping rather than wait for a suspended thread. An uncontended fast-path acquisition can still lock and push an entry during that pause. These are implementation details, not reasons to omit a matching end.

The stack lets CPython find locks that must be released when the thread would otherwise block. It also lets the runtime resume the appropriate enclosing section later.

A critical section therefore requires an attached thread state. It is not a synchronization primitive for an arbitrary native thread that has not attached to Python.

The stack follows lexical nesting, but nesting does not guarantee that every enclosing object's lock remains held. Suspension changes which stack entries are active.

## Detachment suspends all active sections

Suppose code in a critical section tries to acquire a `PyMutex` that another thread holds. Waiting while retaining the current object's lock can create a cycle:

```text
Thread 1 holds object A and waits for object B.
Thread 2 holds object B and waits for object A.
```

Before the thread blocks and detaches, CPython suspends its active critical sections. It releases the mutexes held by those sections and marks the stack entries inactive. Other threads can then acquire those object locks.

When execution is ready to continue, CPython reacquires the lock or locks for the top relevant section. Ending an inner section can cause an inactive outer section to be resumed.

All detachment suspends active critical sections, not only detachment while waiting for a lock. Calls such as `PyEval_SaveThread()` and `Py_BEGIN_ALLOW_THREADS` detach explicitly. C API operations can detach internally when they block on a `PyMutex`.

Running Python bytecode is also a possible suspension point. At evaluation safe points, a thread can detach to honor a stop-the-world request, such as a free-threaded GC pause. In a free-threaded build with the GIL re-enabled at runtime, a GIL hand-off also detaches the thread. A Python callback, `__eq__`, `__hash__`, or finalizer can therefore suspend the section even if it never waits for a lock.

This behavior avoids many lock-order deadlocks. It also means another thread can modify the protected object before the section resumes.

## Restore invariants before any possible suspension

Complete related field updates before calling potentially suspending code. Suppose readers use `self->version` to detect changes to `self->value`. Do not call out between updating those fields:

```c
PyObject *old;

Py_BEGIN_CRITICAL_SECTION(self);
old = self->value;
self->value = Py_NewRef(replacement);
call_that_may_block();       /* The section may release self's lock. */
self->version++;
Py_END_CRITICAL_SECTION();

Py_XDECREF(old);
```

If the call suspends the section, another thread can acquire `self`'s lock. That reader can see the new value with the old version and wrongly conclude that the value has not changed.

Arrange the update so that the invariant is valid before the call:

```c
PyObject *old;

Py_BEGIN_CRITICAL_SECTION(self);
old = self->value;
self->value = Py_NewRef(replacement);
self->version++;
Py_END_CRITICAL_SECTION();

Py_XDECREF(old);
```

More generally, complete the state transition before invoking code that can block, detach, run a finalizer, or enter an uncontrolled callback. If work must continue after a suspension point, treat protected observations made before it as stale and revalidate them after the lock is reacquired.

## Reacquisition does not restore old facts

Reacquiring a mutex establishes ordering with changes made by intervening lock holders. It does not roll the object back to its earlier state.

This pattern is unsafe:

```c
Py_BEGIN_CRITICAL_SECTION(self);
PyObject *item = self->value;
call_that_may_suspend();
use_object(item);  /* self->value and item's lifetime may have changed. */
Py_END_CRITICAL_SECTION();
```

The code needs a strong reference obtained while the lock is held, and it must decide whether a changed `self->value` invalidates the operation logically:

```c
PyObject *item;

Py_BEGIN_CRITICAL_SECTION(self);
item = Py_XNewRef(self->value);
Py_END_CRITICAL_SECTION();

if (item != NULL) {
    call_without_object_lock(item);
    Py_DECREF(item);
}
```

If the operation requires `self->value` to remain the same, moving the call outside the section is not enough. The design may need a version check, a state transition that reserves the operation, or a direct mutex protocol that safely remains locked across the call.

## Nested single-object sections do not lock two objects reliably

It is tempting to nest two single-object sections:

```c
Py_BEGIN_CRITICAL_SECTION(a);
Py_BEGIN_CRITICAL_SECTION(b);
/* use a and b */
Py_END_CRITICAL_SECTION();
Py_END_CRITICAL_SECTION();
```

If acquiring `b` blocks, CPython can suspend the section for `a` and release `a`'s lock. The inner code can then run without `a` remaining locked. The nesting therefore does not provide reliable simultaneous ownership.

Even when both acquisitions happen immediately in one test run, correctness cannot depend on the absence of contention.

Use the two-object form when one invariant requires both locks:

```c
Py_BEGIN_CRITICAL_SECTION2(a, b);
/* Both object locks protect this operation together. */
Py_END_CRITICAL_SECTION2();
```

CPython orders the two locks consistently by address. If the two arguments refer to the same mutex, the implementation treats them as one lock.

The pair can still be suspended together by a later blocking operation. The two-object form guarantees simultaneous locking while the section is active; it does not convert it into an unsuspendable region.

## At most two object locks are supported

The public critical-section API supports one object or two objects at once. It does not provide a three-object form.

Do not build a three-object operation by nesting another single section around a two-object section. Suspension means the outer lock may not remain active.

Instead, reconsider the ownership model. Options include:

- protect the relationship with one separately owned mutex;
- use one object as the owner of the complete invariant;
- copy or retain stable inputs, then update objects in separate phases;
- impose an explicit direct-mutex order when no arbitrary Python execution occurs; or
- redesign the API so no operation needs three mutable objects locked together.

The correct choice depends on what other threads are allowed to observe between phases.

## Recursive entry avoids deadlock but can release outer locks

Re-entering a critical section on an object already locked by this thread's critical sections does not deadlock merely because the same mutex is needed again.

If the mutex belongs to the top-most section, CPython can skip the new acquisition and stack entry. This is a performance shortcut. If an earlier section holds the mutex, the attempted acquisition instead causes detachment and suspension of the outer sections. Their locks are released, and the inner section can acquire the mutex.

The general suspend-and-resume mechanism prevents the recursive deadlock. The top-most shortcut is not the only safe case.

Do not treat this as ordinary recursive-mutex ownership. Other threads can modify the object between the outer and inner acquisitions. More complex nesting can also leave other outer objects unlocked while the inner section runs.

Prefer explicit helper contracts and callback boundaries over relying on recursive entry. If an algorithm requires continuous recursive ownership, use a purpose-built design and document its ownership rules.

## Object locks exclude only cooperating operations

Holding an object's critical section prevents another operation that tries to acquire the same per-object lock from proceeding concurrently. It does not stop every possible access to the object's memory.

Another path may:

- read immutable fields without locking;
- use a representation-specific lock-free fast path;
- perform atomic access to selected fields; or
- incorrectly access fields directly without synchronization.

The object's implementation must define which fields require its critical section and which use another protocol. A critical section is not a magic barrier around all bytes reachable from the object.

Unpublished construction state, immutable fields, and thread-local state normally need no lock. A helper may also rely on the caller already holding the required lock. Document that requirement and do not assume it survives a suspending call.

It also protects only the chosen object. Locking a list does not automatically protect the mutable objects stored in that list.

## Built-in APIs usually manage their own locking

Public operations on core containers generally perform the locking they need. An extension should not normally wrap every call to `PyList_Append()` or `PyDict_SetItem()` in an external critical section.

Use an external section when several operations must follow one object-level rule or when an API explicitly requires it. `PyDict_Next()` is a notable example: when another thread may modify the dictionary, the caller must hold the dictionary's critical section for the iteration.

```c
Py_BEGIN_CRITICAL_SECTION(dict);
PyObject *key;
PyObject *value;
Py_ssize_t pos = 0;
while (PyDict_Next(dict, &pos, &key, &value)) {
    /* Use key and value according to their reference-lifetime rules. */
}
Py_END_CRITICAL_SECTION();
```

Do not infer that every borrowed reference returned inside the loop remains valid after the section ends. Acquire strong references if they must escape the protected region. Avoid calls in the loop body that can suspend the section and allow the dictionary to change; otherwise the iteration itself must be redesigned to tolerate that change.

## Use critical sections to acquire `ob_mutex`

Every Python object in the free-threaded build has an `ob_mutex` used by this mechanism. Extension code must acquire it through critical sections, not directly with `PyMutex_Lock()`.

CPython's interpreter has specialized non-blocking fast paths that acquire `ob_mutex` directly. Those paths have separate contracts. They are not a model for ordinary extension or core code.

Direct locking bypasses the critical-section stack. If code later blocks while holding that direct lock, CPython cannot suspend it as part of critical-section deadlock avoidance. Mixing direct and critical-section acquisition of the same `ob_mutex` can deadlock.

Use:

```c
Py_BEGIN_CRITICAL_SECTION(obj);
...
Py_END_CRITICAL_SECTION();
```

For independent extension state, add a separate `PyMutex` field rather than reusing `ob_mutex`.

## Mutex-backed critical sections support non-object state

Python 3.14 added critical-section variants that take explicit `PyMutex` pointers:

```c
Py_BEGIN_CRITICAL_SECTION_MUTEX(&state->mutex);
/* Protected operation that may enter the C API. */
Py_END_CRITICAL_SECTION();
```

There is also a two-mutex form:

```c
Py_BEGIN_CRITICAL_SECTION2_MUTEX(&a->mutex, &b->mutex);
/* Both mutexes are active together. */
Py_END_CRITICAL_SECTION2();
```

These variants are useful for C state that is not itself a `PyObject` but must call into the C API in ways that could otherwise create lock-order deadlocks.

They have the same suspension semantics as object critical sections. If the protected invariant requires the mutex to remain held continuously, use direct `PyMutex_Lock()` instead and design callback and lock ordering accordingly.

The [build contract below](#critical-sections-are-no-ops-in-the-default-build) applies to these macros too. In particular, their default-build no-op behavior cannot protect native-thread accesses outside the GIL.

## Critical sections are no-ops in the default build

In the default GIL-enabled build, `Py_GIL_DISABLED` is not defined. The macros normally expand to lexical braces without locking. When using the limited API, the object macros call functions that do nothing in this build. Correctness then relies on the GIL for accesses made by attached threads.

In a free-threaded build with the GIL re-enabled at runtime, critical sections still acquire per-object locks. They still suspend when the thread detaches, including on GIL hand-off. Enabling the GIL at runtime does not change the compiled API.

This lets one source tree support both builds:

```c
Py_BEGIN_CRITICAL_SECTION(self);
self->version++;
Py_END_CRITICAL_SECTION();
```

In the default GIL-enabled build, the attached caller's GIL supplies serialization. In the free-threaded build, the object's mutex does.

This equivalence applies only when the old access was genuinely protected by the GIL. Background native threads, detached regions, and process-global state accessed outside Python's attachment rules need synchronization in both builds.

The object-based macros, functions, and state structures are available in the limited API and Stable ABI from Python 3.15. The explicit `_MUTEX` variants are not. See the [C API synchronization documentation](https://docs.python.org/3.15/c-api/synchronization.html#python-critical-section-api) for the public API.

## Recognize CPython's generated code and internal helpers

Core contributors will often see Argument Clinic's `@critical_section` directive instead of handwritten macros. By default, it wraps the generated implementation call in a critical section on `self`. It can name one or two target objects to generate the corresponding one-object or two-object form. Generated locking has the same suspension rules.

The internal header [`pycore_critical_section.h`](https://github.com/python/cpython/blob/main/Include/internal/pycore_critical_section.h) also provides diagnostic and specialized helpers:

- `_Py_CRITICAL_SECTION_ASSERT_OBJECT_LOCKED(op)` and `_Py_CRITICAL_SECTION_ASSERT_MUTEX_LOCKED(m)` check the top-most section, not all enclosing sections. They perform checks only in `Py_DEBUG` free-threaded builds. The object check is skipped when `Py_REFCNT(op) == 1`. These are diagnostics, not a synchronization or lifetime guarantee.
- `Py_BEGIN_CRITICAL_SECTION_SEQUENCE_FAST(original)` and its matching end lock only an exact `list` in the free-threaded build. The argument is the original input to `PySequence_Fast()`, not its result. This specialized helper does not lock arbitrary sequences.

## Choose between a direct mutex and a critical section

Use a direct `PyMutex` when:

- the mutex must remain held continuously;
- the code has a controlled lock order;
- it does not invoke arbitrary callbacks while locked; and
- the state needs protection in both build configurations independently of the GIL.

Use a CPython critical section when:

- the state follows CPython's per-object locking model;
- the operation may enter C API paths that block or reenter;
- temporary release avoids otherwise difficult lock-order deadlocks; and
- the operation can tolerate revalidation after suspension.

These questions help identify where suspension affects the choice:

1. Can any operation inside block, detach, run a finalizer, or invoke arbitrary Python?
2. Are invariants restored before every possible suspension point?
3. Which observations must be revalidated after reacquisition?
4. Do two objects need the simultaneous two-object form?

The next CPython-specific mechanism is [stop-the-world coordination](12-stop-the-world.md), used when one or two object locks cannot provide the required global view.

---

Next: [Stop-the-world](12-stop-the-world.md)
