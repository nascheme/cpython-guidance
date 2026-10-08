# CPython's concurrency model

CPython has two related build configurations:

- the default GIL-enabled build, where `Py_GIL_DISABLED` is not defined and a global interpreter lock serializes most execution within an interpreter; and
- the free-threaded build, in which the GIL can remain disabled and several threads can execute Python code in the same interpreter at the same time.

Free-threaded CPython was introduced in Python 3.13. It does not remove synchronization. It replaces synchronization that the GIL supplied with finer-grained mechanisms such as per-object locking, `PyMutex`, atomic operations, modified reference counting, stop-the-world pauses, and QSBR.

Code must be explicit about which build assumptions it uses.

## The GIL serializes attached threads in the traditional build

A **thread state**, represented by `PyThreadState`, stores a thread's execution state for one interpreter. Most of the C API requires the current operating-system thread to have an attached thread state.

In the traditional build, attaching a thread state requires acquiring that interpreter's GIL. Only one thread state can be attached to the interpreter at a time. This means only one thread at a time normally executes its Python bytecode or calls C API operations that require attachment.

The GIL therefore supplied broad mutual exclusion for much internal state. Code running with the GIL held could often access interpreter globals or object fields without a separate mutex, provided that every competing access also required the same GIL.

That qualification matters. The GIL has never protected:

- C code that accesses the state after releasing the GIL;
- another process;
- state modified by code that does not follow the GIL rule;
- all operating-system or library state; or
- an invariant across a call that can release the GIL and run other code.

The GIL was a synchronization rule, not a reason to ignore ownership and reentrancy.

## Free threading allows several attached threads

In a free-threaded build with the GIL disabled, several threads may have thread states attached to the same interpreter simultaneously. They may execute Python bytecode and C API functions in parallel on different CPU cores.

An attached thread state is still required for most Python APIs. Removing the GIL does not make thread-state management optional. The thread state carries the current exception, interpreter association, evaluation state, allocator and reference-counting data, and other per-thread information.

This changes a common inference:

```text
Traditional build:
attached to interpreter => holds that interpreter's GIL

Free-threaded build with GIL disabled:
attached to interpreter =/=> exclusive execution
```

Code that used attachment as proof of exclusive access needs another rule in the free-threaded build.

## The free-threaded build can run with the GIL enabled

An executable built for free threading does not guarantee that the GIL is disabled at every moment in every process. The GIL can be enabled at runtime, including when an imported extension module has not declared support for running without it.

Extension modules declare free-threading support during module initialization. Multi-phase modules use the `Py_mod_gil` slot with `Py_MOD_GIL_NOT_USED`. Single-phase modules can use `PyUnstable_Module_SetGIL()`. Its declaration exists only in the free-threaded build, so guard the call when supporting both builds:

```c
/* After successfully creating the module object m. */
#ifdef Py_GIL_DISABLED
PyUnstable_Module_SetGIL(m, Py_MOD_GIL_NOT_USED);
#endif
```

The `Py_GIL_DISABLED` macro identifies the free-threaded build at compile time. It does not mean that an extension may omit synchronization and depend on a runtime GIL. Code advertised as free-threading compatible must remain correct when the GIL is disabled.

Keep the build configuration separate from the runtime GIL state. Critical-section macros such as `Py_BEGIN_CRITICAL_SECTION` expand to plain blocks in the default GIL-enabled build. In a free-threaded build, they still use critical-section locking even when the GIL has been re-enabled at runtime. The free-threaded reference-counting, QSBR, and stop-the-world mechanisms also remain in use.

The mutex-backed critical-section macros, such as `Py_BEGIN_CRITICAL_SECTION_MUTEX`, are no-ops in the default build too. They cannot protect extension state accessed outside the GIL there. Use direct `PyMutex_Lock()` / `PyMutex_Unlock()` calls when that state needs mutex protection in both builds.

## Attached, detached, and suspended are distinct states

For normal execution and stop-the-world coordination, distinguish three thread-state concepts:

- **Attached:** the thread may call most Python APIs and execute Python code.
- **Detached:** the thread is not currently allowed to call most Python APIs. It can later attach itself again.
- **Suspended:** the thread state has been suspended, for example for a stop-the-world operation. The thread cannot resume itself. The thread controlling the pause allows it to attach again.

Attachment and detachment apply in both builds. Suspension is specific to the free-threaded build. These are not an exhaustive list of internal states. CPython also tracks shutdown and waiting states.

A thread normally detaches around a blocking operation:

```c
Py_BEGIN_ALLOW_THREADS
blocking_system_call();
Py_END_ALLOW_THREADS
```

These macros remain meaningful in a free-threaded build. Detaching lets stop-the-world coordination account for the thread. Code inside the detached region must not use APIs that require an attached thread state. Violating this rule can crash or race. It is not reliably rejected.

Detaching also suspends active CPython critical sections and releases their locks in a free-threaded build. Another thread can then lock the same objects and modify their protected fields. Do not assume that a critical-section lock acquired before `Py_BEGIN_ALLOW_THREADS` remains held inside it. [Chapter 11](11-cpython-critical-sections.md) explains suspension and revalidation after resuming.

A thread created outside Python must attach an appropriate thread state before calling most of the C API. In Python 3.15 and later, `PyThreadState_Ensure()` takes a `PyInterpreterGuard *` and returns a `PyThreadStateToken *`. Pair a successful call with `PyThreadState_Release()` using that token.

Older code commonly uses `PyGILState_Ensure()` and `PyGILState_Release()`. Those APIs assume the main interpreter when attaching a foreign thread and generally do not support subinterpreters. The 3.15 API is not a drop-in replacement.

Stop native threads that call into Python before interpreter finalization. In Python 3.14 and later, a non-finalizing thread that tries to attach through an API such as `PyGILState_Ensure()` during finalization can hang permanently.

Do not reinterpret "GIL" API names as no-ops. Their attachment and detachment effects remain part of the free-threaded execution model.

## Stop-the-world operations use thread-state transitions

Some runtime operations need a view that cannot be obtained by locking one object. Cyclic garbage collection is the primary example.

In a free-threaded build, CPython requests a stop-the-world pause. Attached threads reach safe points and become suspended. Detached threads are prevented from reattaching while the pause is active. Once the required threads are stopped, the initiating thread can perform the global operation.

Afterward, CPython starts the world again. Suspended thread states are made eligible to return to their prior execution flow.

This is different from ordinary mutual exclusion. A mutex excludes competitors from one protected invariant. Stop-the-world coordination prevents Python execution across a whole interpreter or runtime scope. It is correspondingly more expensive and belongs on infrequent paths that truly need global consistency.

[Chapter 12](12-stop-the-world.md) describes the stop-the-world implementation and its scopes in more detail.

## The GIL's old assumptions must be replaced individually

Removing the GIL exposes several different synchronization needs. There is no single replacement lock.

For each old access, ask what property the GIL supplied:

- Was it protecting mutable fields of one Python object?
- Was it protecting independent interpreter or extension state?
- Was it making a reference acquisition indivisible with container access?
- Was it serializing a process-global cache?
- Was it preventing object destruction during an operation?
- Was it providing a global snapshot?

The replacement follows from the answer:

- per-object critical sections protect many object invariants;
- a separate `PyMutex` protects independently owned state;
- atomic operations are an alternative for independent scalar state when measured performance justifies their extra complexity;
- strong-reference APIs combine lookup with safe reference acquisition;
- QSBR delays reclamation for selected unlocked readers; and
- stop-the-world pauses support global operations.

Using one mechanism everywhere would either be incorrect or recreate unnecessary global serialization.

## Container safety does not make compound operations atomic

Core mutable containers such as lists, dictionaries, and sets use internal locking in the free-threaded build. An operation such as `PyList_Append()` locks the list as needed to protect its mutation.

This makes documented container operations safe from internal corruption under their stated contracts. It does not make an arbitrary sequence of calls atomic:

```c
if (PyList_Size(list) > 0) {
    item = PyList_GetItemRef(list, 0);
}
```

Another thread may empty the list between the size check and lookup. Each call can be individually thread-safe while the compound check-and-use operation has a race condition.

When several accesses form one invariant, protect the complete operation. In this example, the list's critical section protects its length and item slots. Keep the size check and lookup together, without a call that can suspend the section between them. Competing mutations must follow the list's synchronization protocol. Locking the list does not lock the mutable contents of its items.

Some optimized read paths avoid locking. They use atomic access and safe reclamation protocols designed for the specific representation. Their existence does not make direct struct-field access safe for general C code.

This is the data-race versus race-condition distinction from chapter 1 applied to container APIs. Internal synchronization protects the container; callers must still protect their compound operations. Do not infer transactionality from the GIL either: callbacks and explicit GIL release can let other code intervene even in the traditional build.

## Direct field access bypasses API synchronization

C code can often see CPython structure definitions or use accessor macros that expand to direct field access. In a free-threaded build, this may bypass locking, validation, atomic operations, or reference acquisition performed by a function API.

For example, macros such as `PyList_GET_ITEM()` do not lock the list. They are unsafe when another thread can modify that list concurrently. Directly reading a mutable field of an extension object has the same issue unless the caller holds the lock that protects it.

Prefer documented function APIs when sharing is possible. If internal code deliberately uses an unlocked fast path, it needs a representation-specific proof covering data races, ordering, and lifetime.

The fact that one field is machine-word-sized is not such a proof.

## Borrowed references need renewed scrutiny

A borrowed reference is valid only while some owner keeps the object alive. Under the GIL, code could often borrow an item from a container and use it before another Python thread could mutate the container.

That pattern can fail under free threading:

```c
PyObject *item = PyList_GetItem(list, 0);  /* Borrowed. */
use_object(item);
```

There are two separate hazards. `PyList_GetItem()` reads the item slot without locking or an atomic load, so the pointer read itself can race with a concurrent store. Another thread can also replace the item and release the list's reference. The borrowed object may be destroyed before `use_object()` runs.

Use an API that returns a strong reference when the container may be modified concurrently:

```c
PyObject *item = PyList_GetItemRef(list, 0);
if (item == NULL) {
    return -1;
}
use_object(item);
Py_DECREF(item);
```

The function performs lookup and acquisition under the container's synchronization rule. Loading a borrowed pointer and calling `Py_INCREF()` afterward may be too late, for the same reason described in the reclamation sections.

Borrowing remains safe when the pointer lookup is race-free and an ownership rule prevents the owner from dropping the reference during use. An immutable tuple kept alive by the caller is a common example. Effectively private argument containers are another. State those access and ownership rules instead of banning all borrowed references.

## Reference counting is concurrency-aware

Traditional CPython commonly updates one `ob_refcnt` field while holding the GIL. Making every reference-count update an atomic read-modify-write would add cost even for objects used by only one thread. Heavily shared objects could also suffer cache-line contention.

Free-threaded CPython therefore uses several techniques, including biased reference counting, deferred reference counting for selected objects, and immortal objects.

At a conceptual level:

- operations performed by an object's owning thread can often update its local reference count without atomic read-modify-write operations;
- references from other threads are accounted for separately and merged when needed;
- selected references can be accounted for later rather than on every interpreter-stack operation; and
- immortal objects do not need reference-count updates.

These are CPython implementation mechanisms. Extension authors should continue to follow the public new-reference, borrowed-reference, `Py_INCREF()`, and `Py_DECREF()` contracts. Do not directly manipulate reference-count fields or infer lifetime from one internal counter.

Reference counting also does not replace locking of an object's mutable contents. An owned reference keeps the object alive. It does not stop another thread from modifying the object.

## Extension state may now be genuinely shared

A C extension may have static variables, caches, freelists, counters, or mutable fields that were accessed only while the GIL was held. If the module declares free-threading support, several attached threads can reach that state concurrently.

For each field, choose an explicit rule:

- move genuinely per-thread data to thread-local storage;
- put per-interpreter state in module or interpreter-associated storage;
- protect an extension object's mutable fields with that object's critical section, with readers and writers following the same rule;
- protect independently owned shared state with a separate `PyMutex`;
- consider atomic operations for independent scalar state when measured performance justifies the added complexity; or
- remove a cache whose synchronization cost exceeds its benefit.

Module state being per-interpreter does not make it per-thread. Threads attached to the same interpreter can still access it concurrently.

Avoid using a Python object's reserved per-object mutex directly for unrelated extension state. Add a separate mutex whose ownership and protected fields are clear. A later section covers `PyMutex` and another covers CPython critical sections.

## Review code under both build models

For code that supports both CPython configurations, ask:

1. Which accesses were formerly serialized by the GIL?
2. Which of those can now occur from several attached threads?
3. Which object or mutex protects each mutable invariant?
4. Do direct field accesses or macros bypass that protection?
5. Does every borrowed reference remain valid under concurrent mutation?
6. Can any call block, detach, invoke Python, or run a callback?
7. Does an owned reference protect lifetime without being mistaken for content locking?
8. Does extension initialization correctly declare whether the module supports a disabled GIL?

The following CPython-specific sections explain the main replacement mechanisms. [Chapter 10](10-pymutex.md) begins with `PyMutex`, the lightweight mutex underlying many of CPython's locks and critical sections.

---

Next: [`PyMutex`](10-pymutex.md)
