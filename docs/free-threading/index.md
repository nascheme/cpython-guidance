# Free-threading guidance for CPython contributors

Practical guidance for contributors working on free-threading in CPython.
It draws on recurring feedback in CPython code reviews and explains common
mistakes and how to avoid them.

This guidance was written by a CPython core developer and reviewed by other core
developers. It is not official CPython policy.

This document concerns CPython internals. While some advice might be relevant
for third-party extension modules, it is suggested you first start with [the free-threading extension
guide](https://docs.python.org/3/howto/free-threading-extensions.html).

## Contents

- [Critical sections](#cs)
  - [Whether a critical section is needed](#cs-needed)
  - [Critical section has the wrong extent](#cs-scope)
  - [Critical section locks the wrong object](#cs-object)
  - [Critical section leaked on an error path](#cs-leak)
  - [Critical section suspension semantics](#cs-suspend)
  - [Argument Clinic @critical_section](#cs-clinic)
- [Atomics and memory ordering](#atomic)
  - [Whether an access must be atomic](#atomic-needed)
  - [One side of the access is atomic, the other is not](#atomic-asymmetric)
  - [Memory ordering is wrong](#atomic-ordering)
  - [Read-modify-write is not atomic](#atomic-rmw)
- [Reference handling](#ref)
  - [Borrowed reference is not safe here](#ref-borrowed)
  - [tp_iternext and shared iterators](#ref-iternext)
  - [Deferred reference counting and VM stack references](#ref-model)
- [Lock choice and discipline](#lock)
  - [Wrong synchronization mechanism](#lock-choice)
  - [Lock ordering and deadlock](#lock-order)
  - [Lock lives at the wrong scope](#lock-scope)
- [Stop-the-world](#stw)
  - [Unsafe work while the world is stopped](#stw-misuse)
  - [Stop-the-world where a lock would do](#stw-overuse)
- [Tests](#test)
  - [Needs a test](#test-missing)
  - [The test cannot actually hit the race](#test-cannot-race)
  - [Test placement and gating](#test-gating)
  - [ThreadSanitizer](#test-tsan)
- [Performance](#perf)
  - [Regression in the default build](#perf-default-build)
  - [Scaling and contention](#perf-scaling)
- [Observable behaviour](#semantics)
  - [Define the thread-safety contract](#semantics-change)
  - [Why the code is already safe, with no mechanism named](#semantics-justify-no-race)
- [Dual-build portability](#build)
  - [Build guards and the FT_* wrappers](#build-guard)

<a id="cs"></a>

## Critical sections

_needed or not, wrong scope, wrong object, leaks, suspension_

<a id="cs-needed"></a>

### Whether a critical section is needed

A critical section protects an object's mutable state. Use one when another
thread can access the same state at the same time and at least one thread can
change it.

Protect reads as well as writes. Suppose code changes `self->exports` while
holding `self`'s critical section. Every competing read of `self->exports`
must hold the same critical section:

```c
Py_ssize_t exports;
Py_BEGIN_CRITICAL_SECTION(self);
exports = self->exports;
Py_END_CRITICAL_SECTION();
```

Locking only the code that changes the field is not enough. An unlocked read
can overlap a write.

Some operations depend on more than one access. They may read a field, check
its value, and then use another field based on that result. Keep these steps
in the same critical section. Otherwise, another thread can change the
object after the check but before the value is used. A call to a helper can
also access the object indirectly. Check what called functions do before
deciding that a method does not need locking.

A critical section is not needed when no competing thread can change the
state. Common examples are a new object that has not yet been published,
immutable state, thread-local state, and code whose caller already holds the
required lock. A method also does not need its object lock when it does not
access the object's state, either directly or through a called function. Do
not add a critical section only because a function receives an object as an
argument.

Identify which fields can change after publication. Work that depends only
on arguments or immutable state can happen before acquiring the lock. Once
code reads mutable protected state, keep the critical section until it no
longer depends on that state.

A containing object's lock can protect a private contained object. This is
safe only when every access to the contained object goes through the
containing object and follows the same locking rule. Document this ownership
rule. Use lock-held helpers and lock assertions to make the rule clear.

For an Argument Clinic entry point, use `@critical_section` when the whole
operation needs the object's lock. For other code, a small wrapper can enter
the critical section and call a lock-held implementation.

When code intentionally does not take a lock because of a less obvious
safety rule, document that rule and assert it where possible. For example, a
constructor-only helper can explain that the object has not been published
and, when applicable, assert `_PyObject_IsUniquelyReferenced(obj)`.

<a id="cs-scope"></a>

### Critical section has the wrong extent

Protect the complete operation on mutable state. First list the fields the
operation reads or writes. Then identify which object's lock protects each
field. Acquire that lock before the first relevant read, and keep dependent
checks and uses in the same critical section.

Do not unlock after reading a pointer if another thread can invalidate it
before the pointer is used. Obtain an owned reference or copy while locked,
or keep the lock through the use. The same rule applies to a check followed
by an update: another thread must not be able to change the checked state
between those steps.

Keep unrelated work outside the section. Type checks, argument conversion,
and result construction often do not need the object's lock. Where
practical, use the protected part only to read or update the object's
internal state.

When the lock is already held, prefer a suitable lock-held helper such as
`_PyList_AppendTakeRef()` instead of a public helper that acquires another
critical section. This avoids extra work and unnecessary nested critical
sections.

If a call that can suspend the critical section or invoke arbitrary code
must occur inside it, assume the protected state may change. Do not carry
borrowed pointers or checked conditions across the call without revalidating
them afterward. See [Critical section suspension
semantics](#critical-section-suspension-semantics).

Do not split a dependent operation solely to impose a lock order. Python
critical sections avoid lock-order deadlocks by suspending an active outer
section when another acquisition blocks. This means another thread may
change the outer object while its section is suspended. If the operation
needs two objects to remain protected together, use
`Py_BEGIN_CRITICAL_SECTION2()` rather than two nested sections. See [Critical
section suspension semantics](#critical-section-suspension-semantics).

<a id="cs-object"></a>

### Critical section locks the wrong object

`Py_BEGIN_CRITICAL_SECTION(obj)` locks only `obj`. It does not automatically
protect other objects that `obj` refers to. It also does not protect an
object that refers to `obj`.

Start by listing the mutable fields that the operation reads or changes.
For each field, identify which object's lock protects it. Then lock that
object. Do not assume that `self` is always the right object.

For example, a set iterator uses state from two objects. The set owns the
table of entries. The iterator owns its current position and whether it is
exhausted. Locking the set protects the table, but not fields stored in the
iterator. Locking the iterator does not protect the set's table.

Container operations usually lock the container, not the items in it.
Comparing an item with other elements does not by itself mean that the item
must be locked. The container lock protects the structure of the heap, list,
set, or table.

Sometimes an operation uses mutable state from two different objects and
needs both objects to remain consistent. Use
`Py_BEGIN_CRITICAL_SECTION2` to lock both objects in that case. Do not lock a
second object only because the function receives it or mentions it. Lock it
only when the operation depends on mutable state that its lock protects.

Do not omit a required lock because of concerns about lock ordering.
Critical sections are designed to avoid lock-ordering and re-entrancy
deadlocks. Avoid unnecessary locks because they add work and protect no state
that the operation needs.

<a id="cs-leak"></a>

### Critical section leaked on an error path

Treat `Py_BEGIN_CRITICAL_SECTION` and `Py_END_CRITICAL_SECTION` as a single
lexical region. Every control-flow path after the begin must reach the
matching end.  A `return`, error `goto`, or a jump beyond the end leaves
the object mutex held and can deadlock later users.

Perform type checks and other validation that can return before entering the
section, rather than acquiring a lock for an object that may not have the
required layout.

Keep error handling simple enough to audit this pairing. Prefer a
`_lock_held` helper that asserts its object is locked, plus a small
wrapper that opens and closes the section around the call. For Argument
Clinic methods, `@critical_section` can generate that wrapper.

Avoid using `goto` to manage a critical section: it makes skipped cleanup
easy to introduce and has been reported to cause MSVC compile problems.  If
cleanup is needed, structure the paths so they converge on the explicit
`Py_END_CRITICAL_SECTION`.

<a id="cs-suspend"></a>

### Critical section suspension semantics

Code between `Py_BEGIN_CRITICAL_SECTION` and
`Py_END_CRITICAL_SECTION` is not guaranteed to hold the lock continuously.
A call can suspend the critical section. The lock is released and acquired
again before execution continues. The object may have changed while the lock
was released. Acquiring the lock again does not restore the old state.

A critical section can be suspended when the thread detaches, such as during
a blocking operation. It can also happen when code enters another critical
section and has to wait for that object's lock. Calls that run arbitrary
Python code can re-enter the interpreter and modify objects that the caller
was using.

Some re-entrant calls are easy to miss:

- `Py_DECREF` can run deallocation code when the reference count reaches
  zero. This can invoke weak-reference callbacks or a `__del__` method.
- A comparison can call methods such as `__eq__` or `__lt__`.
- Hashing and conversions can call methods such as `__hash__`, `__index__`,
  or `__int__`.
- Descriptors, callbacks, and calls through type slots can also execute
  arbitrary Python code.

Treat each such call as a point where data you depend on can change under
you. A borrowed pointer may no longer be valid. A saved list index may no
longer be in range. A condition checked before the call may no longer be
true. Two fields that agreed before the call may no longer agree afterward.

This problem also exists in a build with the GIL. It does not require two
threads. A `__del__` or `__eq__` method can run in the current thread and
modify an object before the C function resumes. The GIL does not protect C
code from changes made by re-entrant calls.

Do not carry a borrowed pointer or a checked condition across a possible
re-entry point. Take an owned reference or a stable copy while the object is
locked when that is sufficient. After the call, read the mutable state again
and repeat any checks that later code depends on. Remember that an owned
reference protects an object's lifetime, but not its mutable contents.

When the caller already holds the required lock, use a suitable `_LockHeld`
helper instead of an ordinary API that enters another critical section.
This can avoid suspending the outer critical section only to acquire another
lock. It does not make callbacks safe. If the helper can run arbitrary code,
the caller must still allow for re-entry and recheck mutable state afterward.

A typical wrapper and lock-held helper have this form:

```c
static PyObject *
operation_lock_held(MyObject *self)
{
    _Py_CRITICAL_SECTION_ASSERT_OBJECT_LOCKED(self);
    /* Read or update protected state. */
    ...
}

static PyObject *
operation(MyObject *self)
{
    PyObject *result;
    Py_BEGIN_CRITICAL_SECTION(self);
    result = operation_lock_held(self);
    Py_END_CRITICAL_SECTION();
    return result;
}
```

The helper must not reacquire `self`'s critical section. Its name and
assertion make the caller's locking responsibility explicit. Calls inside
the helper can still suspend the section or invoke arbitrary code, so the
same revalidation rules apply.

<a id="cs-clinic"></a>

### Argument Clinic @critical_section

For a Clinic-defined method, getter, or setter whose operation is protected
by its receiver, put `@critical_section` on the Clinic declaration. Argument
Clinic then generates the entry-point wrapper that acquires the critical
section and calls the `_impl` function while it is held. This places locking
at the API boundary, keeps the implementation focused on its operation,
and avoids repeated free-threading boilerplate while keeping the existing
signature and behavior.

Do not add `Py_BEGIN_CRITICAL_SECTION` again inside an implementation
reached through such an annotated wrapper. If a helper must be called both
from a protected Clinic entry point and elsewhere, make its locking contract
explicit - for example, use a `lock_held` helper and arrange for the caller
to acquire the section - rather than nesting ad hoc wrappers.

Use manual locking only where Clinic cannot describe the required object
or call boundary; otherwise convert the entry point, including getsets, to
Clinic and let the directive own the acquisition. The directive locks `self`
by default; it can name arguments instead, but lock only what the operation
actually mutates - locking an argument as well needs justification.

One accepted exception to converting: when Clinic would force duplicating a
docstring shared across entry points, a manual wrapper around the impl is
the preferred approach.

<a id="atomic"></a>

## Atomics and memory ordering

_needed or not, asymmetric, ordering, RMW_

<a id="atomic-needed"></a>

### Whether an access must be atomic

Decide from what other threads can do to the state, not from the generated
code. A data race is undefined behavior in C even when it looks harmless
on current hardware or survives stress testing. Plain accesses are safe
when the state is thread-local, immutable after publication, or protected
by a lock that every competing access holds. If accesses can overlap,
add synchronization; prefer a critical section or mutex unless measured
performance requires a lock-free design.

Correct lock-free code requires reasoning about every competing access,
object lifetime, publication, and memory ordering. Passing tests does not
prove that an atomic protocol is correct. See [Memory ordering is
wrong](#memory-ordering-is-wrong) for CPython-specific guidance and [Mara
Bos, *Rust Atomics and Locks*](https://mara.nl/atomics/) for a general
introduction to atomics and memory ordering.

Locks are usually easier to reason about because they protect the invariant
of an operation, not just individual field accesses. In `unregister_task`,
for example, checking and changing links in a shared task list belongs
under the same lock; making each link access atomic would still let another
thread see the list part-way through an update. The `PyMutex` used by Python
critical sections is a fast, lightweight mutex based on the WebKit mutex
design. Do not assume that replacing it with atomics is an optimization. Use
atomics when the state really can be accessed independently and profiling
shows that locking is a meaningful cost or a scaling bottleneck for shared
reads.

The cost of an atomic depends on the operation, memory order, and CPU
architecture. Naturally aligned relaxed loads and stores generally compile
to ordinary machine loads and stores, including on AMD64. Acquire loads
and release stores also commonly need no extra CPU instruction on AMD64,
but impose ordering constraints and can require stronger instructions on
architectures with weak memory ordering, such as ARM64. Sequentially
consistent operations, explicit fences, and atomic read-modify-write
operations may require more expensive serialization. Even relaxed atomics can inhibit
compiler optimizations such as coalescing adjacent stores, and writes to
heavily shared cache lines can cause cache-line contention.

Hot accessors sometimes justify a design that keeps reads plain and
moves synchronization to a rare writer. `Py_TYPE`, for example, is an
extremely common operation, while changing an object's type is rare. CPython
therefore keeps `Py_TYPE` as a plain load and uses a stop-the-world pause in
`object_set_class`, ensuring that readers are at safe points before the type
is changed. Making both `Py_TYPE` and `Py_SET_TYPE` atomic would remove the
C data race between those accesses, but would add cost to every type read
and would not by itself ensure that a thread is no longer acting on the old
type. See [Stop-the-world where a lock would
do](#stop-the-world-where-a-lock-would-do) for the access pattern that can
justify this exceptional design.

Do not add atomics merely to quiet TSan or as the default response to shared
state. When a plain access is intentional, document why it is safe, such as
a lock being held, immutability after publication, or synchronization being
performed by a rare writer.

<a id="atomic-asymmetric"></a>

### One side of the access is atomic, the other is not

A lock on the writer does not make a concurrent unlocked reader safe. If
a field is read with an atomic load, a plain store to the same field can
still overlap it and form a data race. The reverse mix is just as unsafe:
an atomic store does not protect a plain load. Both sides of a potentially
concurrent access must follow the same synchronization scheme.

For a field that needs lock-free reads, use atomic operations for every
concurrent read *and* write; `ob_size`, for example, needs atomic stores as
well as atomic loads. Use relaxed atomics only when no ordering with other
memory is needed. Publishing a pointer or flag that makes earlier writes
visible requires stronger ordering. See [Memory ordering is
wrong](#memory-ordering-is-wrong). Relaxed loads and stores are generally
cheaper than a critical section.

A `PyObject*` field is harder: a setter like `Py_XSETREF` must also release
the old reference, and an atomic store alone cannot do that safely. Do not
respond by making only the getter atomic. Either use a full atomic update
protocol or put both reads and writes under a critical section; the critical
section is usually simpler and is the right choice when the path is not
performance-critical.

<a id="atomic-ordering"></a>

### Memory ordering is wrong

Pick the ordering from what the access must make visible. When installing a
pointer to newly initialized data -- a resized array's replacement buffer,
an object being stored into a list -- do the initialization first and
publish the pointer with a "release" store.  This ensures every prior write
is visible before the pointer is. A reader that loads the pointer and then
reads the data behind it needs the matching "acquire" load.  The pair
guarantees that a reader that sees the new pointer also sees the contents
written before it was published.

Do not validate memory ordering only by testing on AMD64. For ordinary
loads and stores, acquire and release operations commonly use the same CPU
instructions as relaxed operations on AMD64, although their
compiler-ordering constraints still differ. A missing acquire or release may
remain hidden there and fail on an ARM64 system such as Apple Silicon or AWS
Graviton.

Run a test that performs both sides of the synchronization protocol under
ThreadSanitizer. The test must make the potentially conflicting operations
overlap and reach the accesses whose ordering is in question. TSan can
report a missing happens-before relationship without waiting for the
hardware to expose it. However, it examines only executed paths and does not
detect every logical error involving atomics. A clean TSan run does not
prove that the memory ordering is correct. Choose the ordering from the
required visibility.

Do not reach for stronger orderings by default. Moving already-published
items around, as in list's `ins1()` or heapq's siftdown, publishes nothing
new, so "relaxed" is enough. A "release" store is more expensive than a
relaxed store on ARM64.

Using `seq_cst` by default is a code smell. It often means the protocol's
actual ordering requirements have not been identified. Use it only when
correctness requires a single total order among the sequentially consistent
operations. Otherwise, select the weakest ordering that provides the
required visibility and ordering.

<a id="atomic-rmw"></a>

### Read-modify-write is not atomic

A read-modify-write must be protected as one operation. If two threads both
load a shared value, compute a replacement, and store it, one update can
silently overwrite the other. `++`, `+=`, and bit-mask updates are
load-then-store operations even when written as a single C expression.

Prefer putting the complete update under a critical section for per-object
state or a mutex for independently owned shared state. This is usually the
clearest and least error-prone solution, especially when the update involves
multiple fields, reference ownership, or other invariants. Every competing
access must follow the same locking discipline; locking only one update path
does not make unlocked accesses safe.

Use an atomic read-modify-write only when the state is an independent scalar
and measured performance justifies the additional complexity. In that case,
use a primitive that performs the whole update atomically: `_Py_atomic_add_*`
for a counter, or atomic AND or OR for a bit mask. An atomic load followed by
an atomic store is still two separate operations and can still lose an
intervening update. If no primitive expresses the operation, a
compare-exchange loop may be required, including careful handling of retries,
memory ordering, and object lifetime.

Replacing a `PyObject*` field illustrates why locking should be the default.
`Py_XSETREF` must replace the pointer and decref the old reference safely;
making only the store atomic is insufficient, while a correct lock-free
replacement requires a more complicated compare-exchange protocol. The
`func_code` review therefore kept the whole replacement under a critical
section. A hot, independent scalar such as a bit mask may instead justify an
atomic operation, as with the atomic AND used to clear a dict watcher bit.

<a id="ref"></a>

## Reference handling

_borrowed refs, Py_NewRef, tp_iternext, the FT model_

<a id="ref-borrowed"></a>

### Borrowed reference is not safe here

Obtain an owned reference before releasing the lock that protects a borrowed
pointer. After the lock is released, another thread can remove the value,
drop its last reference, and free it. A later `Py_INCREF()` is too late
because it may access freed memory.

Prefer an API that returns a new reference, such as `PyList_GetItemRef()`, and
handle failure if concurrent mutation removed the item. When reading under a
critical section, call `Py_NewRef()` before leaving the section. Keep stealing
operations explicit: `PyList_SET_ITEM()` and `_PyList_AppendTakeRef()` require
an owned reference to transfer.

Optimistic lock-free code needs a safe acquisition protocol, not a direct
incref of the loaded pointer. Deferred or immortal values can be used under
their specific lifetime rules. Otherwise use `_Py_TryXGetRef()` or
`_Py_TryIncrefCompare()`, and retry under the object's critical section if it
fails.

<a id="ref-iternext"></a>

### tp_iternext and shared iterators

The default goal for concurrent use of one iterator is crash-freedom. Two
threads calling `tp_iternext` on the same iterator must not access freed
memory, corrupt reference counts, or damage the iterator or its container.
They do not necessarily need to receive each item exactly once or in a
predictable order.

Concurrent calls may repeat, skip, or interleave values when the iterator's
contract allows that behavior. Callers that need a specific division of the
input can provide their own synchronization. Array iteration follows the list
model: several threads can consume the same iterator without crashing, but
they may receive repeated values.

Crash-freedom still requires enough synchronization to protect memory and
reference ownership. Updates to the iterator's position must not cause an
invalid access. A value taken from a mutable container must remain alive
while it is used. If memory safety depends on state from both the iterator
and its container remaining consistent, protect both with
`Py_BEGIN_CRITICAL_SECTION2()`.

Do not fully serialize `tp_iternext` only because concurrent calls are
possible. Add stronger synchronization when the iterator has a useful
shared-consumption contract, such as guaranteeing that each item is returned
only once, and when that guarantee provides enough value to justify its
performance and implementation cost. Match comparable built-in iterators
unless the type has a reason to promise more.

In the free-threaded build, do not mark exhaustion by clearing the iterator's
owning reference to its container. Two threads can reach exhaustion and both
release the reference. Keep the container reference until the iterator is
destroyed. Record exhaustion in separate state, such as the iterator's
position. `itertools.cycle` and `reversed` use this pattern.

<a id="ref-model"></a>

### Deferred reference counting and VM stack references

Deferred reference counting changes when an object can be destroyed. An
ordinary object can be destroyed when its reference count reaches zero. An
object using deferred reference counting may remain alive until a later
garbage-collection pass.

This delay can improve performance by avoiding reference-count contention on
commonly shared objects. It can also change visible behavior. Do not enable
deferred reference counting for an object when correctness depends on a
`__del__` method or weak-reference callback running as soon as the reference
count reaches zero.

Deferred reference counting does not remove the normal ownership rules for
`PyObject*` references. Code must still obtain an owned reference when the
object could otherwise be removed or freed. Immortal objects have another
special lifetime: they are never destroyed. When correctness depends on an
object being deferred or immortal, make that assumption explicit in the
code.

The following guidance applies only to code in the interpreter VM. Most
CPython code, including extension modules, should continue to use ordinary
`PyObject*` ownership APIs. `_PyStackRef` is the internal representation used
by the evaluation stack and frame locals. See `InternalDocs/stackrefs.md`
when working in `Python/bytecodes.c`, the generated opcode evaluator, or
helpers that directly produce values for the evaluation stack.

A deferred `_PyStackRef` keeps its object alive only after the reference is
stored somewhere that the garbage collector scans. This includes the
interpreter evaluation stack and frame locals such as
`_PyInterpreterFrame.localsplus`. A `_PyStackRef` held only in a C local
variable is not visible to the garbage collector. If no visible reference
remains, a call that triggers garbage collection can allow the object to be
destroyed.

Code generated from `bytecodes.c` normally writes opcode results directly to
the interpreter evaluation stack. This makes deferred `_PyStackRef` values
visible to the garbage collector. A hand-written C helper does not get this
protection automatically. Before it calls any function that can run Python
code or trigger garbage collection (an "escaping call"), it must write the
result to the evaluation stack or another location scanned by the garbage
collector. Do not leave the only reference in a C local variable. The
garbage collector cannot see that reference and may destroy the object. This
requires extra care in opcode paths such as `LOAD_ATTR`, where descriptor
lookup can run arbitrary Python code.

<a id="lock"></a>

## Lock choice and discipline

_primitive choice, lock order, lazy init, scope_

<a id="lock-choice"></a>

### Wrong synchronization mechanism

Choose synchronization from the state that must stay unchanged for the whole
operation. For per-object state, start with the object's critical section.
For shared state owned by a module, interpreter, or external library, start
with a `PyMutex` at that same scope. These choices usually make the ownership
and protected fields easier to understand than atomics do.

Use an atomic operation only for independent scalar state when measured
performance justifies the extra complexity. See [Whether an access must be
atomic](#whether-an-access-must-be-atomic) and [Read-modify-write is not
atomic](#read-modify-write-is-not-atomic). If an operation must preserve a
relationship among fields or safely replace an owned reference, protect the
complete operation with a lock.

Check what can run while a raw `PyMutex` is held. Unlike a Python critical
section, it is not suspended to avoid re-entrancy or lock-order deadlocks.
Its waiting path cooperates with thread-state detachment, so waiting for a
`PyMutex` does not by itself deadlock with the GIL or the free-threaded
garbage collector. This does not make the mutex re-entrant or prevent cycles
among mutexes. Do not hold it across finalizers, callbacks, or conversions
such as `__index__` without a clear deadlock argument. A per-object `PyMutex`
can still be appropriate for plain memory work that cannot call Python, as
in compression code.

Treat stop-the-world as exceptional, not as an ordinary synchronization
mechanism. Use it only for a genuinely global transition whose readers do
not take a common lock. Changing an object's type is one example: readers use
`Py_TYPE()` throughout the runtime, so locking only the writer does not stop
a thread from continuing to act on the old type. See [Unsafe work while the
world is stopped](#unsafe-work-while-the-world-is-stopped) and [Stop-the-world
where a lock would do](#stop-the-world-where-a-lock-would-do).

<a id="lock-order"></a>

### Lock ordering and deadlock

When one operation must lock two Python objects together, prefer
`Py_BEGIN_CRITICAL_SECTION2()` to two manually nested critical sections.
Nested Python critical sections avoid lock-order deadlocks by releasing an
active outer section when acquisition blocks. That also means another thread
can change the outer object during the inner section. The two-object form
keeps the relationship between both objects protected as one operation.

A single critical section can also work well for shared state owned by one
Python object, such as module-level state associated with a module object. If
every access uses that owner's lock, re-entrant acquisition does not deadlock
as a raw `PyMutex` can. Re-entry may still modify the protected state, so
revalidate any assumptions after a call that can invoke arbitrary code. Do
not use a per-interpreter owner's lock for process-global state shared across
interpreters. See [Critical section suspension
semantics](#critical-section-suspension-semantics).

Treat plain `PyMutex` locks differently. They are not re-entrant. A helper
that acquires a mutex already held by its caller can deadlock immediately.
Name lock-held helpers clearly, document which lock the caller owns, and do
not reacquire it inside the helper.

Avoid holding a plain mutex across a call that can invoke arbitrary Python
code or an external callback. Re-entrant code may take the same mutex or
another mutex in the opposite order. If the call must occur while object
state is protected, consider a Python critical section or restructure the
operation so the callback runs outside the raw lock.

<a id="lock-scope"></a>

### Lock lives at the wrong scope

Put the lock at the same scope as the shared resource. Ask whether the state
belongs to one object, one interpreter, one process, or one thread. Then make
every conflicting access use a lock that all users of that resource share.

A per-object critical section or a mutex in module state cannot protect
process-global state across subinterpreters. If a non-thread-safe libc or
external-library interface uses global storage, use a process-global
`PyMutex`. Keep the mutex around only the calls that share that storage when
the library's contract permits it. Conversely, put truly thread-local state
in `PyThreadState` instead of building a shared cache protected by a mutex.

Do not serialize an entire extension merely because one part is not thread
safe. Identify which operations conflict. For example, readline history-file
operations may need one lock, while updating an unrelated Python hook may be
able to proceed concurrently. The lock should cover all accesses to its
resource and no unrelated work.

<a id="stw"></a>

## Stop-the-world

__PyEval_StopTheWorld misuse and overuse_

<a id="stw-misuse"></a>

### Unsafe work while the world is stopped

Stop-the-world is a big hammer. It pauses every affected interpreter thread,
including threads doing unrelated work. Frequent pauses can destroy
multi-threaded performance. Do not choose stop-the-world only because it is
simpler than deciding which state to lock.

Prefer a critical section for per-object state or a `PyMutex` for other
narrowly owned shared state. Use stop-the-world only for a whole-interpreter
change that cannot be protected efficiently with a narrower mechanism. One
case that can justify it is a very rare update to state read on many hot
paths. Changing an object's type follows this pattern. The rare
`__class__` assignment stops the world so that common `Py_TYPE()` reads can
remain plain and inexpensive.

Stop-the-world is a general runtime mechanism. The garbage collector is one
user of it, but stopping the world does not mean that garbage collection is
in progress. Put work that requires all other threads to be paused directly
between `_PyEval_StopTheWorld()` and `_PyEval_StartTheWorld()`. Do not infer
that state from GC flags.

Keep the stopped region short. Structure the operation in this order:

1. Perform validation and other preparation that does not require the world
   to be stopped.
2. Stop the world.
3. Perform only the global state change that requires all other threads to
   be paused.
4. Start the world again on every control-flow path.
5. Perform cleanup, reference releases, and error reporting after other
   threads can run again.

Code inside the stopped region must not wait for a mutex or critical-section
lock. A suspended thread may hold that lock and cannot run to release it.
Use direct field access or a suitable lock-held helper when the
stop-the-world pause already provides the required exclusion.

Code inside the stopped region must also avoid running arbitrary Python
code. In particular, `Py_DECREF()` can invoke a finalizer when it releases
the last reference. Error reporting can allocate memory or re-enter the
interpreter. If the protected operation detects an error, record the failure,
restart the world, and then release references or report the error.

<a id="stw-overuse"></a>

### Stop-the-world where a lock would do

Do not stop every interpreter thread to protect state owned by one object or
subsystem. Use the narrowest shared mechanism: a critical section for
per-object state, or a `PyMutex` for independently owned shared state. This
lets unrelated threads continue running.

Consider stop-the-world for the opposite access pattern: a whole-interpreter
value that is read on many hot paths and changed very rarely. A pause around
the rare GC-threshold update was suggested so all ordinary readers could
remain unsynchronized. Compare that design with the cost and complexity of
adding synchronization to every read.

Make the tradeoff explicit. A pause is not a shortcut for avoiding lock
design, and a lock is not automatically cheaper when it burdens ubiquitous
readers. Avoid stop-the-world in diagnostics and fatal-error paths, where a
deadlock can suppress the report itself.

<a id="test"></a>

## Tests

_missing, cannot race, gating, TSan, build-only failures_

<a id="test-missing"></a>

### Needs a test

A regression test is normally expected with every bug fix. The test should
exercise the code path and conflicting operations that caused the bug.
Without the fix, it should demonstrate the bug by failing or producing the
expected TSan report. With the fix, it should pass reliably across supported
hardware. Run it against both versions before submitting the PR. A test that
also passes without the fix does not protect against the bug returning.

Put the test near related tests. A test that is specific to the free-threaded
build generally belongs in `Lib/test/test_free_threading/`. If the module
already has a `test_free_threading_*` file, class, or section, add the test
there instead. Follow the existing organization rather than creating another
location for the same module.

Useful hints for concurrency regression tests:

- Start with the reproducer from the issue when it exercises the same code
  path. Reduce it to the smallest reliable unit test.
- Make the conflicting operations overlap. A barrier or other explicit
  coordination is usually better than relying only on timing.
- If normal execution does not reliably demonstrate the race, run the
  unfixed and fixed versions under TSan. The test must still reach the
  intended concurrent path.
- Assert the behavior the API actually promises. Some operations promise
  only crash-freedom. Others must preserve a stronger property, such as the
  heap invariant. Do not assert one exact ordering when thread scheduling
  makes several results valid.
- Use `threading_helper.catch_threading_exception` when exceptions raised in
  worker threads might otherwise be missed.
- Cover separate changed implementations separately. For example, bounded
  and unbounded `lru_cache` paths need separate tests when both were changed.
- Mark tests that start threads with
  `@threading_helper.requires_working_threading()` so they skip platforms
  without working thread support.

<a id="test-cannot-race"></a>

### The test cannot actually hit the race

Make the two conflicting operations overlap on purpose. Start workers with a
barrier, then repeat the exact read and mutation involved in the bug. For
example, subscript an array while another thread repeatedly resizes it.
`threading_helper.run_concurrently()` already provides a barrier when its
interface fits the test. When the bug requires a specific precondition or
handoff between threads, coordinate it with a `Barrier`, `Event`, or
`Condition` instead of `time.sleep()`. A sleep does not guarantee that
another thread has reached the required point and can make the test
platform-dependent or flaky.

Do not set a stop event immediately after `Thread.start()`; workers may exit
before they contend. Prefer a fixed number of short operations, or let the
writer set the event after it completes its loop. Repeated small mutations
create more useful interleavings than one large mutation. Keep the test fast
enough for normal CI; reviews have used a target below 100 ms.

Assert an invariant that holds under every allowed schedule, not one exact
sequence of results. Confirm that the setup reaches the synchronization path
changed by the fix. Object-sharing transitions can select a different locked
path and accidentally hide the race. Finally, run the test against the
unfixed code. It should fail, crash, or produce the expected TSan report.

<a id="test-gating"></a>

### Test placement and gating

Put the regression beside the module's other free-threading tests. Use its
existing `test_free_threading_*` class or group, or place a dedicated test in
`Lib/test/test_free_threading/`. Follow the local organization instead of
creating a third location for the same module.

Every test that starts threads needs
`@threading_helper.requires_working_threading()` so it skips platforms such
as WASI. Use `threading_helper` lifecycle helpers such as `start_threads()`
or `reap_threads`, and add `@support.requires_resource("cpu")` when the test
is intentionally CPU intensive.

Gate on the behavior, not the diagnostic tool. Use
`support.Py_GIL_DISABLED` only when the test is meaningful solely in a
free-threading-capable build. Do not substitute a TSan check: TSan can run on
the default build and can find races there. If the regression is valid with
the GIL enabled, run it in both builds.

A free-threading-capable build can be started with its GIL enabled. When the
test specifically requires the GIL to be off, check
`sys._is_gil_enabled()` at runtime and give a precise skip reason.

<a id="test-tsan"></a>

### ThreadSanitizer

Run a race regression under TSan instead of waiting for a reproducible crash.
Verify that the test reaches the intended concurrent path. Where practical,
confirm locally that the unfixed code reports the race and that the fixed
code runs cleanly. If TSan stays quiet in both versions, check whether object
sharing, a lock, or another condition sent the test down a different path.
For build and usage instructions, see [Using Thread Sanitizer to validate
and test thread
safety](https://py-free-threading.github.io/thread_sanitizer/).

Add tests that create their own concurrent workload to `TSAN_TESTS` in
`Lib/test/libregrtest/tsan.py`. Add a test to `TSAN_PARALLEL_TESTS` when the
regression-test runner must execute it concurrently with
`--parallel-threads`. These are different ways to create concurrency. Choose
the one that reproduces the race the test is meant to cover.

TSan runs in CI are expected to report no errors. The suppression files for
both the GIL and free-threaded builds currently contain no active
suppressions. Treat every new report as a CPython bug until it has been
investigated. Fix the cause rather than adding a suppression or skipping the
workload under TSan.

A regression test that exposes an existing TSan report must be added together
with the fix. Do not first add it to `TSAN_TESTS` or `TSAN_PARALLEL_TESTS` and
leave CI failing. Confirm locally that the test reports the race without the
fix and runs cleanly with the fix.

<a id="perf"></a>

## Performance

_default-build regression, scaling and contention_

<a id="perf-default-build"></a>

### Regression in the default build

Keep the traditional GIL build's hot path unchanged unless sharing the new
code has negligible cost. The GIL already protects ordinary object access in
that build. If a free-threading fix adds real synchronization or obscures a
previously simple path, use `#ifdef Py_GIL_DISABLED` and leave the original
GIL implementation easy to read.

Check the generated cost before adding a separate branch. A Python critical
section is a no-op in the GIL build, and some free-threading atomic wrappers
compile to an ordinary access there. In those cases, an `#ifdef` may add code
without improving performance.

Also check whether the concurrent use is worth supporting. Do not slow common
single-threaded operations to provide stronger results for a use case that
still needs caller-side locking. State the promised behavior first, then
benchmark both builds. Keep one implementation when its cost is negligible.
If the GIL build regresses, put only the costly free-threading operation
behind `#ifdef Py_GIL_DISABLED` rather than duplicating more code than
necessary.

<a id="perf-scaling"></a>

### Scaling and contention

First decide whether concurrent use of the same object is useful. Do not
assume that every operation must scale well when many threads call it at
once. Several threads consuming one iterator, for example, receive
interleaved parts of the input. They usually still need their own
coordination to make the result useful.

Start with the simplest correct design. This is often one critical section
or mutex that serializes access to the shared state. A simple locking design
is easier to review, test, and maintain. Do not add sharded locks, atomics, or
lock-free paths only because concurrent calls are possible.

Consider a more complex design when there is evidence that the simple design
is a problem. Evidence may come from real applications, an established
scaling benchmark, or an operation that is already known to run concurrently
in common workloads. A microbenchmark for an unlikely use case is not enough
by itself.

When scaling matters, measure performance as threads are added. A lock that
is cheap without contention can become a serialization point when many
threads use the same object, module state, or external library. Use a
representative multi-threaded workload. A single-thread benchmark cannot
show contention.

Only then consider narrowing or splitting the lock. Lock the smallest
resource that needs protection and hold the lock only for the required part
of the operation. For example, serialize calls into a non-thread-safe library
without also serializing unrelated Python work. Preserve an existing
lock-free read path when its safety rules are clear and measurements show
that it matters.

More complex concurrency control must provide a measured benefit large
enough to justify its additional correctness and maintenance cost. If real
workloads do not suffer from contention, keep the simple design.

<a id="semantics"></a>

## Observable behaviour

_behaviour change, and why code is already safe_

<a id="semantics-change"></a>

### Define the thread-safety contract

Before changing synchronization, state what behavior the operation should
provide. Compare the behavior before and after the PR. For free-threading
changes, also compare the GIL and free-threaded builds. If both C and
pure-Python implementations exist, check whether they still provide the same
behavior.

Adding a lock is not only an implementation detail. It can make operations
run one at a time when they previously overlapped. It can prevent callers
from observing intermediate state. It can also change when an exception is
raised. These changes may be visible to users.

Decide which guarantee is useful for the operation:

- Must concurrent calls only avoid crashes and memory corruption?
- Must each individual access be safe?
- Must the whole operation see one consistent version of the object?
- Must concurrent mutations be fully serialized?
- Does the caller still need its own lock to obtain a meaningful result?

Do not provide the strongest guarantee automatically. Stronger
synchronization can cost more and may not make concurrent use useful.
Crash-freedom is enough for some operations. Other operations, such as
updates to several related fields, may require full serialization.

A safe individual access does not guarantee a consistent result for a whole
operation. For example, a lock-free `list.index()` can run while another
thread calls `list.reverse()`. Each element read can be memory-safe, while
the search still observes some elements before the reverse and others after
it. This is an intermediate result. It is not necessarily a torn machine
read or a C data race.

State which entry points provide the guarantee. A supported Python operation
may be thread-safe even when a lower-level C API is not. For example,
`obj.__class__ = new_type` can be safe while direct concurrent use of
`Py_SET_TYPE()` remains unsupported. Do not imply that every path is safe
when only one path performs the required synchronization.

Document a public thread-safety guarantee when users need to rely on it.
Describe weaker guarantees accurately. Also explain the intended behavior in
the PR so reviewers can decide whether the synchronization implements the
right contract rather than only hiding a reported race.

<a id="semantics-justify-no-race"></a>

### Why the code is already safe, with no mechanism named

Do not add synchronization only because code can run without the GIL. For
each field, explain why a conflicting access cannot overlap. Common reasons
are: the object is immutable after publication, the state belongs to one
thread, construction finishes before publication, or destruction begins only
after other references are gone. For example, `tp_dealloc` cannot run
concurrently on the same reachable object.

Check the exact operation rather than making a broad claim about its
surrounding function. `UNPACK_SEQUENCE` can read a tuple without locking
because tuple contents are immutable. The list case must keep the size check
and element pushes together because another thread can resize the list.
Likewise, an abstract sequence API may already provide the required safety,
while direct access to list internals needs explicit protection.

Separate a possible performance loss from a correctness failure. Ask what
happens if the state changes between a check and its later use. It may be
acceptable to do extra work or miss an optimization. It is never acceptable
to access freed memory, use an invalid index, lose a reference, or perform an
update using assumptions that are no longer true. In those cases, use
synchronization or check the state again before using it. Put any non-obvious
reason that the change is harmless in a comment beside the code.

<a id="build"></a>

## Dual-build portability

_Py_GIL_DISABLED guards and the FT_* wrappers_

<a id="build-guard"></a>

### Build guards and the FT_* wrappers

Keep the common source path when the two builds implement the same
operation. Use an `FT_*` wrapper for an access that must be atomic only
without the GIL, rather than spelling a raw `_Py_atomic_*` operation at each
call site: the wrapper supplies the free-threaded operation and expands to
the ordinary operation in the default build. The same applies to the other
`FT_*` wrappers for locks, weak references, and inlining. This preserves
the GIL build's existing code and avoids making its hot paths pay for
synchronization they do not need.

Use `#ifdef Py_GIL_DISABLED` when the representation or algorithm genuinely
differs, and arrange it so the default branch remains recognizable as
the original simple code. Do not add a build split solely to wrap a
primitive that has a suitable `FT_*` form, but do split a call site if
the wrapper cannot preserve its required semantics. In particular, check
return values and side effects: an atomic fetch-add and `value += n` need
not have the same result value.

Do not guard the critical-section macros either: `Py_BEGIN_CRITICAL_SECTION`
already compiles to nothing in the default build. The one sanctioned
exception to "just use the wrapper" is a handful of hot paths
(`new_reference()`, `_Py_IsOwnedByCurrentThread()`) where stores are atomic
only in `_Py_THREAD_SANITIZER` builds, so plain stores to adjacent fields
can coalesce; that pattern needs a measured, performance-sensitive path to
justify it and should not be blindly copied elsewhere.
