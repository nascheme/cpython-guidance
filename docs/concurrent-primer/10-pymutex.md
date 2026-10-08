# `PyMutex`

`PyMutex` is CPython's basic lightweight mutex. Use it to protect independently owned shared C state, such as module state, a cache, or an interpreter-wide table. Prefer CPython critical sections for a Python object's mutable fields. Use a separate, directly acquired `PyMutex` when those fields need a lock that stays held for the whole operation.

It provides ordinary mutual exclusion: one thread locks the mutex, accesses the protected state, and unlocks it. A later successful acquisition observes work published before the earlier unlock.

`PyMutex`, `PyMutex_Lock()`, and `PyMutex_Unlock()` became public in Python 3.13. `PyMutex_IsLocked()` became public in 3.14. These names are not part of the limited API or Stable ABI.

Direct `PyMutex` locking works in both the default GIL-enabled build, where `Py_GIL_DISABLED` is not defined, and the free-threaded build.

## Store the mutex beside the state it protects

A mutex rule should name the exact fields it protects:

```c
typedef struct {
    PyObject_HEAD
    PyMutex mutex;       /* Protects value and update_count. */
    PyObject *value;
    uint64_t update_count;
} CacheObject;
```

Initialize a `PyMutex` to zero before any thread can use it:

```c
CacheObject *cache = ...;
cache->mutex = (PyMutex){0};
```

Static and zero-filled allocations already have the required initial representation:

```c
static PyMutex registry_mutex;
```

Then hold that same mutex for every conflicting access to the protected fields:

```c
PyMutex_Lock(&cache->mutex);
PyObject *value = Py_XNewRef(cache->value);
uint64_t count = cache->update_count;
PyMutex_Unlock(&cache->mutex);
```

The caller must keep `cache` alive throughout the operation and have an attached thread state for `Py_XNewRef()`. The strong reference lets the caller continue using `value` after unlocking. The mutex-protected pointer load alone would not keep the object alive.

## A `PyMutex` has a stable address

Do not copy or move an initialized `PyMutex`. Both its contents and its address are meaningful to the implementation. A contended mutex can have waiters associated with its address.

This rules out operations such as copying a containing structure by value:

```c
struct state copy = *shared_state;  /* Wrong if state contains a PyMutex. */
```

Allocate the containing object at its final address before the mutex can be used. Do not resize it by moving its bytes while another thread could access the mutex.

A `PyMutex` currently occupies one byte, but its size and representation are not stable API guarantees. Use `sizeof(PyMutex)` rather than assuming one byte. Do not inspect or modify its private bits.

## Lock and unlock delimit the invariant

The basic API is small:

```c
PyMutex_Lock(&state->mutex);
/* Read or update fields protected by state->mutex. */
PyMutex_Unlock(&state->mutex);
```

Locking supplies acquire ordering. Unlocking supplies release ordering. If one thread updates protected fields and unlocks the mutex, a later thread that locks the same mutex can observe those updates.

The mutex protects only code that follows this rule. An unlocked read of a protected field can still race with a locked writer:

```c
uint64_t count = cache->update_count;  /* Unsafe if another thread can write. */
```

Do not add atomics to selected reads merely to avoid taking the mutex unless the resulting mixed protocol has a complete proof. The mutex may protect a relationship between `update_count`, `value`, and object ownership that an independent atomic load cannot preserve.

## Keep complete state transitions under one acquisition

Keep related changes under one acquisition. For example, replacing `cache->value` and incrementing `cache->update_count` form one transition. Readers using `cache->mutex` must see the new value with the new count, not the new value with the old count:

```c
PyObject *old;

PyMutex_Lock(&cache->mutex);
old = cache->value;
cache->value = Py_NewRef(new_value);
cache->update_count++;
PyMutex_Unlock(&cache->mutex);

Py_XDECREF(old);
```

Moving the decrement after the unlock can be useful because `Py_DECREF()` may run arbitrary deallocation code. The old owned reference remains valid after removal, so its destruction need not occur while the cache mutex is held.

That transformation is not always possible. If destruction is itself part of the protected invariant, the design needs a more careful protocol. Do not move work outside the lock without checking ownership and observable state.

## Waiting temporarily detaches the thread state

`PyMutex_Lock()` first attempts a fast acquisition. The fast path and any brief retry phase do not detach the caller. If the thread must park to wait, CPython detaches its thread state only if it was attached. CPython reattaches that state before returning.

`PyMutex_Lock()` can also be called without a thread state, even before interpreter initialization. It does not create or attach one for such a caller. Acquiring the mutex alone does not permit calls to APIs that require an attached thread state.

If the caller holds the GIL, detachment releases it while the thread is parked. This applies in the default build and in a free-threaded build with the GIL re-enabled at runtime. It prevents a waiting thread from retaining the GIL and blocking the thread that needs to release the mutex. In a free-threaded build, detachment also allows stop-the-world operations to proceed while the thread sleeps.

In the free-threaded build, detaching suspends active CPython critical sections and temporarily releases their locks. A contended `PyMutex_Lock()` inside `Py_BEGIN_CRITICAL_SECTION(obj)` can therefore let another thread lock `obj` and modify its protected fields before the call returns. Revalidate any earlier observations of those fields. [Chapter 11](11-cpython-critical-sections.md) explains suspension and resumption. In the default build, the critical-section macros are no-ops.

## The implementation has fast and parked paths

On the uncontended path, `PyMutex_Lock()` uses an atomic compare-exchange on the compact mutex state. Unlocking without waiters similarly uses a small atomic transition.

When acquisition fails in a free-threaded build, the implementation may retry a bounded number of times, yielding the CPU between attempts. It skips this phase if the mutex already records parked waiters. This behavior depends on the build configuration, not on whether the GIL is enabled at runtime.

If the mutex remains unavailable, the thread parks through CPython's parking-lot mechanism instead of consuming a CPU core indefinitely. Unlocking a contended mutex wakes one waiter. If that waiter has waited more than 1 ms, the unlocking thread hands ownership directly to it to reduce starvation. Otherwise, the woken thread competes with newly arriving threads.

These are current implementation details, not contracts on which correctness should depend.

The useful design conclusion is that an uncontended `PyMutex` is intended to be cheap. Do not replace clear locking with complex atomics based only on the assumption that every mutex acquisition enters the operating-system kernel.

## `PyMutex` is not recursive

Locking a `PyMutex` again in the thread that holds it deadlocks. It does not track recursive ownership. Use the [locked-helper convention from chapter 5](05-synchronization.md#locking-has-ownership-rules) to avoid a second acquisition.

CPython has specialized internal recursive locks where required. That does not make a plain `PyMutex` recursive.

## `PyMutex_IsLocked()` is only diagnostic

`PyMutex_IsLocked()` reports whether the mutex appears locked at the instant of the check:

```c
assert(PyMutex_IsLocked(&state->mutex));
```

Use it for assertions and debugging. Do not use it to decide whether an access is safe:

```c
if (!PyMutex_IsLocked(&state->mutex)) {
    use_state_without_lock(state);  /* Incorrect. */
}
```

A lock-state observation does not acquire ownership. Another thread can lock the mutex and start writing immediately after the check, so the unlocked access can still race with that writer. The public API does not promise memory ordering for this query.

A nonzero result also does not establish that the current thread owns the mutex. `PyMutex` does not track which thread holds it.

## Unlock exactly once on every path

Calling `PyMutex_Unlock()` on an unlocked mutex causes a fatal error. This check detects only a mutex that is unlocked at the moment of the call. `PyMutex` does not track an owner. If another thread acquires it between your first and second unlock, the second unlock silently releases that thread's lock.

Do not rely on this check to catch every extra unlock or an unlock by the wrong thread. Pair each successful acquisition with exactly one unlock, using the cleanup pattern from chapter 5.

Do not return, propagate an error, or perform a non-local exit that skips the unlock.

A C++ wrapper may use RAII to pair lock and unlock, but it must still obey the `PyMutex` address and lifetime requirements.

## Define a lock order for multiple mutexes

Two threads can deadlock if they acquire two `PyMutex` instances in opposite orders. Choose one stable order for every path that needs both.

For independently allocated Python objects, do not invent a local ordering that conflicts with CPython's object-lock protocol. Use the two-object critical-section API when simultaneously protecting two Python objects.

For extension-private mutexes, an immutable rank or a documented hierarchy is often clearer than pointer order. If ordering mutexes by address, keep their containing objects alive and compare addresses converted to `uintptr_t`, as CPython does. Do not use `<` directly on pointers to unrelated objects: that comparison has undefined behavior in C. The integer conversion is implementation-defined, so this technique relies on the target platform's address representation.

Never solve a lock-order problem by checking `PyMutex_IsLocked()` and skipping an acquisition. That exposes the protected invariant exactly when another thread is changing it.

## Avoid arbitrary Python execution while holding a direct mutex

Python execution can invoke callbacks, descriptors, finalizers, weak-reference callbacks, tracing hooks, and extension code. That code may try to acquire the same mutex or another mutex in an incompatible order.

A direct `PyMutex` remains held until code explicitly unlocks it. CPython's critical-section deadlock avoidance does not automatically release a directly held mutex merely because the holder calls arbitrary code.

Prefer one of these designs:

- finish the protected update, retain any needed owned references, unlock, then invoke Python;
- define and enforce a lock order covering every callback path;
- redesign the state so callbacks operate on a stable snapshot; or
- use the critical-section API when its suspend-and-resume semantics match the operation.

Since Python 3.14, `Py_BEGIN_CRITICAL_SECTION_MUTEX` and `Py_BEGIN_CRITICAL_SECTION2_MUTEX` apply critical-section semantics to explicit `PyMutex` pointers. The corresponding low-level functions are `PyCriticalSection_BeginMutex()` and `PyCriticalSection2_BeginMutex()`.

This option changes the guarantee: a critical-section lock may be temporarily released. Code must tolerate the protected state changing across an operation that suspends the section. These macros are no-ops in the default GIL-enabled build. Use direct locking if native threads or detached code need mutex protection there. In a free-threaded build, the macros retain their locking behavior even with the GIL re-enabled at runtime.

## Do not lock `ob_mutex` directly

An object's `ob_mutex` is reserved for [critical-section machinery](11-cpython-critical-sections.md#use-critical-sections-to-acquire-ob_mutex). Do not acquire it with `PyMutex_Lock()`. Add a separate mutex for independently protected state, or use the public critical-section macros for per-object locking.

## Choose direct locking when the lock must stay held

Use direct locking when continuous ownership is necessary and every reader and writer can follow a controlled mutex protocol. Chapter 11 gives the full [comparison with critical sections](11-cpython-critical-sections.md#choose-between-a-direct-mutex-and-a-critical-section).

Before adding one, record:

1. The fields and invariant it protects.
2. Which functions acquire it and which require it held.
3. Whether protected code can block, detach, or invoke arbitrary Python.
4. Its position in the lock order.
5. How the containing object's lifetime keeps the mutex address valid.

For per-object locking around C API operations that may block or reenter Python, CPython provides critical sections. Mutex-backed variants support independently owned C state too. Their name resembles a conventional locked region, but their suspend-and-resume behavior is different. [Chapter 11](11-cpython-critical-sections.md) covers both forms.

---

Next: [CPython critical sections](11-cpython-critical-sections.md)
