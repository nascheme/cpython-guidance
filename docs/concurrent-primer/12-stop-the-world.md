# Stop-the-world

A stop-the-world pause stops other CPython threads in a defined scope. The thread that requested the pause can then change state that those threads might otherwise access.

CPython uses this mechanism when one object lock is not enough. Cyclic garbage collection is an important example. Some rare runtime changes also use it so that common readers do not need to take a lock.

Stop-the-world is a large and costly form of synchronization. It is an internal CPython mechanism, not a general extension API.

The main rule is:

> Use stop-the-world only for a global change that needs every affected thread to stop. Keep the stopped region short.

## A pause can cover one interpreter or the runtime

CPython has two internal forms of stop-the-world:

- `_PyEval_StopTheWorld(interp)` stops threads for one interpreter.
- `_PyEval_StopTheWorldAll(runtime)` stops threads for all interpreters.

Each form has a matching start operation: `_PyEval_StartTheWorld(interp)` or `_PyEval_StartTheWorldAll(runtime)`. The caller must restart the same scope on every path.

All four calls are no-ops in the default GIL-enabled build, where `Py_GIL_DISABLED` is not defined. In that build, any exclusion comes from the relevant GIL, not from these calls. Code relying on that exclusion must not release the GIL in the region.

For example, `Py_BEGIN_ALLOW_THREADS` releases the GIL, and running Python code can allow a GIL switch. These calls do not supply runtime-wide exclusion across interpreters with separate GILs.

The pause mechanism is compiled into free-threaded builds, where `Py_GIL_DISABLED` is defined. It remains active even when the GIL is re-enabled at runtime in such a build. The thread-state transitions below describe that mechanism.

Use the narrowest scope that provides the required view. A runtime-wide pause delays more work than an interpreter-wide pause.

The word *world* therefore needs a scope. An interpreter pause does not mean that every native thread in the process has stopped. It coordinates the Python thread states that belong to that interpreter. A runtime-wide pause coordinates thread states across all interpreters.

## Attached threads stop at safe points

When a pause is requested, CPython records the request and asks other attached threads to stop. The evaluation loop checks for this request at safe points. Each affected thread changes its state from attached to suspended.

A detached thread is not executing Python code or using APIs that require attachment. CPython can move such a thread directly to the suspended state. This also prevents it from attaching while the pause is active.

The requesting thread waits until every other affected thread state is suspended. Only then does the stop operation return. At that point, `world_stopped` is true for that stop-the-world state.

When the caller starts the world again, CPython moves the suspended thread states to the detached state and wakes them. Threads can then attach and continue.

The suspended state is different from the detached state:

- A detached thread can normally attach itself.
- A suspended thread cannot resume itself while the pause remains active.

This distinction lets the requesting thread know that another affected thread cannot return to Python execution during the stopped region.

Suspending a detached thread state does not stop its native thread from running code that does not require attachment. The pause does not exclude that code's accesses to independently shared C state.

## A pause provides a global exclusion point

A mutex works only when all competing accesses use that mutex. This can be too expensive for state read on many hot paths.

For example, `Py_TYPE(obj)` is used throughout CPython. Taking a lock on every type read would add cost to many operations. Changing an object's type is rare. CPython can instead stop the interpreter while it performs the rare change. Readers remain simple because no reader can run at the same time as the write.

This pattern is useful when all of these conditions hold:

- the state is visible across a whole interpreter or runtime;
- reads are very frequent;
- writes are rare;
- readers do not already take one common lock; and
- the write can finish in a short, bounded time.

A pause does not make all data permanently safe. It only excludes affected thread execution while the world remains stopped. Code before the stop or after the restart needs its normal synchronization rule.

## Prepare before stopping, but read changing state afterward

Do work that cannot change concurrently before requesting the pause. This reduces pause time. Examples include allocating private temporary storage or checking fixed argument types.

However, requesting a stop can itself wait. A CPython critical section held by the requester may be suspended while it waits. Other threads can also change shared state before they stop.

Do not compute a new value from mutable shared state and then assume that value is still current after the stop operation returns:

```c
/* Shared flags may change while this thread waits to stop the world. */
new_flags = type->tp_flags | NEW_FLAG;
_PyEval_StopTheWorld(interp);
type->tp_flags = new_flags;  /* May overwrite an intervening change. */
_PyEval_StartTheWorld(interp);
```

Read the changing state and perform the dependent update after the world has stopped:

```c
_PyEval_StopTheWorld(interp);
type->tp_flags |= NEW_FLAG;
_PyEval_StartTheWorld(interp);
```

A useful structure is:

1. Prepare private data that does not depend on a changing shared value.
2. Stop the world.
3. Read or validate shared state again.
4. Perform the small global change.
5. Start the world on every path.
6. Run cleanup and report errors after threads can run again.

## Do not wait for locks while threads are suspended

Do not block on a plain `PyMutex` or another lock that a suspended thread may own. Suspension does not automatically release these locks. The suspended thread cannot run to unlock them until the world starts again.

The requesting thread will deadlock if it tries to acquire such a lock during the stopped region:

```text
Requester stopped the world and waits for mutex A.
A suspended thread owns mutex A and waits for the world to start.
```

CPython critical sections have special handling. A thread releases its critical-section locks when it detaches or suspends. However, a fair mutex unlock can hand ownership to a detached waiter that is then suspended. That waiter cannot finish acquiring and releasing the lock until the world restarts.

Under a per-interpreter pause, the critical-section slow paths check `tstate->interp->stoptheworld.world_stopped` and skip contended locking. The fast paths can still acquire an unlocked mutex.

A critical section is therefore permitted for object state whose competing accesses are all excluded by this pause, but its locking is redundant. CPython's `__class__` assignment uses a dictionary critical section this way.

This check does not examine the runtime's `stoptheworld.world_stopped`. A runtime-wide pause alone does not enable it. Under `_PyEval_StopTheWorldAll`, a critical section may still wait for a lock and deadlock on the handoff described above. A plain `PyMutex_Lock` has no stop-the-world bypass under either scope.

Prefer direct field access or a helper whose contract says that the world is stopped. If some competitor is outside the pause's scope, then the pause is not enough. Redesign the synchronization rather than adding an unexamined lock inside the stopped region.

## Do not run arbitrary Python code while stopped

Do not run Python code or finalizers in the stopped region. Do not block on a lock that a stopped thread may own. Do not call a helper that could request another stop-the-world pause, including through garbage collection.

Arbitrary Python code can block, acquire locks, or require another suspended thread to make progress. It can also reenter runtime code whose stop-the-world assumptions differ.

Even operations that look like cleanup can execute Python code. `Py_DECREF()` may release the last reference and run a finalizer. Error reporting may normalize an exception or invoke other runtime paths.

Allocation and setting an exception are not categorically forbidden. They require an audited path that meets the constraints above. For example, CPython's stopped `__class__` assignment can materialize a managed dictionary and call `PyErr_Format` with a constant message. This does not make arbitrary allocation or error-reporting helpers safe.

Prefer to keep owned references until after the world starts again. If the stopped operation finds an error, a simple pattern is to record enough information to report it later. This illustrative fragment uses placeholder helpers with explicit contracts:

```c
int failed = 0;
PyObject *old = NULL;

_PyEval_StopTheWorld(interp);
/* Helpers must not run Python, wait for locks, or request another pause. */
if (!can_apply_update()) {
    failed = 1;
}
else {
    old = replace_global_state();  /* Transfers an owned reference to old. */
}
_PyEval_StartTheWorld(interp);

Py_XDECREF(old);
if (failed) {
    return report_error();
}
```

The exact safe operations depend on the subsystem. The stopped region should have a small and explicit contract.

## Garbage-collection state is not proof of a pause

The garbage collector uses stop-the-world, but the two ideas are not identical.

A GC flag may be set before all threads have stopped. The collector can also restart threads before it runs finalizers or other later work. Therefore, a flag such as `gc.collecting` does not prove that the world is currently stopped.

Code that requires a pause should run directly between the matching stop and start calls. Internal diagnostic code that checks the state must use the stop-the-world state itself and must also account for the requester and scope.

A pause also does not make every global list safe in every context. For example, signal and fatal-error paths can have extra restrictions. They may be unable to acquire the lock that protects the thread-state list. Stop-the-world does not remove those separate access rules.

## Stop-the-world has a broad performance cost

A mutex delays threads that need one protected object. A stop-the-world pause delays all affected threads, including threads doing unrelated work.

The cost includes:

- asking attached threads to reach safe points;
- waiting for delayed threads;
- moving thread states to and from suspended state;
- lost parallel work during the stopped interval; and
- disturbed CPU caches when threads resume.

A thread in a long-running C operation may take time to reach a point where it detaches or checks the request. The pause latency is therefore not only the time spent in the stopped region.

Before requesting a pause, do not hold a lock that another affected attached thread might wait for without detaching. The requester waits for those threads without detaching and has no overall timeout. If an attached thread is blocked on the requester's lock, neither can make progress.

This can happen with a `PyThread_type_lock` acquired without detaching or an internal `PyMutex` wait using `_Py_LOCK_DONT_DETACH`. Ordinary `PyMutex_Lock` waiters detach, so they do not prevent the pause from completing. They can still cause the lock-handoff hazard inside the stopped region described above.

Avoid stop-the-world on frequent paths. Do not use it only because choosing an owner and a mutex seems harder. Also avoid it in fatal-error paths when a deadlock could hide the original error.

## Choose a narrower mechanism when possible

Use an object critical section for mutable state owned by one Python object. Use a separate `PyMutex` for narrowly owned module, interpreter, or subsystem state. Consider atomics for a suitable independent scalar protocol when measured performance justifies the extra complexity.

Stop-the-world can be the right choice for the opposite access pattern: a rare global writer and many hot readers that cannot take a common lock cheaply.

The safety requirements are:

1. Match the pause's scope to the protected invariant and the competing accesses it actually excludes.
2. Re-read mutable shared state after the stop operation returns.
3. Audit stopped-region operations for waiting on locks, running Python, or requesting nested pauses.
4. Restart the matching scope on every exit path.

Stop-the-world supplies global exclusion. It does not solve the different problem of allowing old lock-free readers to finish after storage has been replaced. CPython uses QSBR for that purpose.

---

Next: [QSBR in CPython](13-qsbr-in-cpython.md)
