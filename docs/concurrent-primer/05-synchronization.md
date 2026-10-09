# Synchronization

Synchronization coordinates operations that occur in different threads. It has two related jobs:

- control which threads may act on shared state at the same time; and
- establish the happens-before relationships required by the C memory model.

Atomic operations can build synchronization protocols. Higher-level primitives such as mutexes and condition variables package common protocols into interfaces that are usually easier to use correctly.

The default rule for shared state should be:

> Protect the complete state transition with one clearly identified lock unless there is a demonstrated reason to use a more specialized design.

In CPython, prefer a [critical section](11-cpython-critical-sections.md) for per-object state or a [`PyMutex`](10-pymutex.md) for independently owned shared state. Later chapters explain their contracts. The generic lock and wait functions below are illustrative, not CPython APIs.

## A mutex provides mutual exclusion and ordering

A **mutex** allows one thread at a time to hold a lock. A thread locks the mutex before accessing protected state and unlocks it afterward:

```c
lock_mutex(&queue_lock);
queue_push(&queue, item);
queue_size++;
unlock_mutex(&queue_lock);
```

Mutual exclusion prevents another thread following the same rule from entering the protected operation at the same time.

The mutex also provides memory ordering. Unlocking a mutex has release semantics. A later successful lock of that mutex has acquire semantics and synchronizes with the unlock. Operations before the unlock therefore happen-before operations after the later lock.

This ordering allows the protected fields to be ordinary, non-atomic objects. Every conflicting access must follow the locking rule, including reads:

```c
size_t
get_queue_size(void)
{
    size_t size;

    lock_mutex(&queue_lock);
    size = queue_size;
    unlock_mutex(&queue_lock);
    return size;
}
```

A field is not safe to read without the mutex merely because the reader does not change it. A read conflicts with a concurrent write.

## Name the state protected by each mutex

A mutex is useful only when code follows a consistent rule. Document the state it protects:

```c
struct work_queue {
    mutex_t mutex;       /* Protects head, tail, size, and closed. */
    struct item *head;
    struct item *tail;
    size_t size;
    bool closed;
};
```

Then use that mutex for every access that can conflict:

```c
lock_mutex(&queue->mutex);
if (!queue->closed) {
    append_item(queue, item);
    queue->size++;
}
unlock_mutex(&queue->mutex);
```

Saying that a function is "thread-safe" is less useful than stating the rule precisely. Identify:

- which mutex must be held;
- which fields it protects;
- whether callers or the function acquire it; and
- whether the function may release it indirectly by blocking or calling other code.

A mutex associated with one object does not automatically protect another object. When an invariant spans several objects, the design must identify the lock or locks that protect the complete relationship.

## Protect invariants, not individual accesses

An **invariant** is a relationship that must hold whenever other threads may observe the state. In a queue, for example:

- `head == NULL` exactly when `tail == NULL`;
- `size` matches the number of linked items; and
- no new item may be added after `closed` becomes true.

Updating each field under a separate lock acquisition is not enough. In this incorrect example, assume the queue is open and non-empty. The caller exclusively owns the new, unlinked `item`:

```c
item->next = NULL;
lock_mutex(&queue->mutex);
queue->tail->next = item;
unlock_mutex(&queue->mutex);

lock_mutex(&queue->mutex);
queue->tail = item;
queue->size++;
unlock_mutex(&queue->mutex);
```

Another thread can acquire the mutex between the two regions and observe a partially updated queue. Keep the complete state transition under one acquisition of `queue->mutex`. Check `closed` and handle an empty queue under that same lock:

```c
lock_mutex(&queue->mutex);
if (!queue->closed) {
    item->next = NULL;
    if (queue->tail == NULL) {
        queue->head = item;
    }
    else {
        queue->tail->next = item;
    }
    queue->tail = item;
    queue->size++;
}
unlock_mutex(&queue->mutex);
```

The protected region should include dependent checks and uses. The `take_one()` example in [the first chapter](01-shared-mutable-memory.md#data-races-and-race-conditions-are-different) must check and decrement `remaining` while holding one lock acquisition. Otherwise another thread can invalidate the check before the use.

## Locks do not preserve facts after unlock

A value can become stale as soon as its mutex is released:

```c
lock_mutex(&queue->mutex);
bool has_item = (queue->head != NULL);
unlock_mutex(&queue->mutex);

if (has_item) {
    remove_first_item(queue);  /* The earlier fact may no longer hold. */
}
```

Another thread may empty the queue between the check and removal. The check and action belong to one logical operation and must remain under the same lock acquisition.

Copying a pointer under a mutex has the same limitation:

```c
lock_mutex(&state->mutex);
PyObject *obj = state->current;
unlock_mutex(&state->mutex);

use_object(obj);
```

The pointer load is protected, but another thread may remove and destroy the object after the unlock. The code must acquire an owned reference while holding the mutex, keep the mutex held during use, or use another explicit lifetime mechanism.

## Locking has ownership rules

A mutex is itself shared state. Its interface defines which thread may unlock it, whether recursive acquisition is allowed, and what happens on errors.

Do not lock a non-recursive mutex again in the thread that holds it. This is an error, not just a risk of deadlock. The outcome depends on the interface:

- For C11 `mtx_plain`, the behavior is undefined.
- POSIX `PTHREAD_MUTEX_NORMAL` deadlocks.
- POSIX `PTHREAD_MUTEX_ERRORCHECK` returns `EDEADLK`.
- POSIX default mutexes may follow another standard mutex type or leave this case undefined. Do not rely on their behavior.

A `PyMutex` does not track its owner. Acquiring it again while holding it deadlocks:

```c
PyMutex_Lock(&state->mutex);
helper(state);  /* helper() also tries to lock state->mutex. */
PyMutex_Unlock(&state->mutex);
```

A useful interface convention is to distinguish functions that acquire a lock from functions that require it already:

```c
static void
append_locked(struct work_queue *queue, struct item *item)
{
    /* queue->mutex must be held by the caller. */
    ...
}
```

The public operation can acquire the lock once and call the locked helper. Assertions that verify lock ownership are valuable when the mutex implementation supports them.

Always release a mutex on every exit path. In C, cleanup labels are often clearer than duplicating unlock calls through a complex function:

```c
int result = -1;
lock_mutex(&state->mutex);

if (!validate(state)) {
    goto done;
}
apply_update(state);
result = 0;

done:
unlock_mutex(&state->mutex);
return result;
```

## Multiple mutexes require a lock order

A thread may sometimes need two independently protected objects at once. If threads acquire the same locks in different orders, they can deadlock:

```text
Thread 1 holds A and waits for B.
Thread 2 holds B and waits for A.
```

Define a stable order and use it everywhere. For example, locks might be ordered by an immutable object identifier, or an operation might use a dedicated two-object locking helper.

Do not use `<` or `>` to order pointers to unrelated objects. C gives those comparisons undefined behavior. CPython's two-object critical sections instead compare mutex pointers converted to `uintptr_t`, for example `(uintptr_t)m2 < (uintptr_t)m1`. Pointer-to-integer conversion is implementation-defined, so this relies on the platforms CPython supports. Keep both objects alive at stable addresses. Every competing path must choose the same order.

Avoid calling unknown or reentrant code while holding a mutex. A callback can acquire another lock, invoke the current component again, or block for an unbounded time. If the callback must run outside the mutex, first arrange the state and lifetime so that releasing the lock is safe.

CPython critical sections add special behavior to reduce deadlocks when a thread would block. A later section explains why their locking rules differ from an ordinary lexical mutex region.

## Condition variables wait for state changes

A mutex protects state, but a thread may need to wait until that state satisfies a condition. Repeatedly locking and checking wastes CPU time. A **condition variable** lets a thread sleep until another thread reports that the state may have changed.

The predicate belongs to the protected state, not to the condition variable. A consumer waits while holding the associated mutex:

```c
lock_mutex(&queue->mutex);
while (queue->head == NULL && !queue->closed) {
    wait_condition(&queue->changed, &queue->mutex);
}

if (queue->head != NULL) {
    item = remove_first_locked(queue);
}
unlock_mutex(&queue->mutex);
```

The wait operation atomically releases the mutex and begins waiting. Before it returns, it reacquires the mutex. This prevents a notification from being lost in the gap between an ordinary unlock and a separate wait operation.

Always test the predicate in a loop. A wait may return spuriously. Another consumer may also acquire the mutex first and consume the item that caused the notification. A notification means "the state may now satisfy the predicate," not "this thread owns an item."

A producer changes the predicate while holding the same mutex, then notifies a waiter:

```c
lock_mutex(&queue->mutex);
if (!queue->closed) {
    append_locked(queue, item);
    signal_condition(&queue->changed);
}
unlock_mutex(&queue->mutex);
```

Changing and testing the predicate under the same mutex supplies both mutual exclusion and memory ordering. Whether notification occurs just before or just after unlocking can depend on the interface and performance needs. The state change itself must follow the predicate's locking rule. POSIX also requires holding the associated mutex when predictable scheduling behavior is required.

If a waiter can destroy `queue->changed` after observing the new state, notify before unlocking `queue->mutex`. Otherwise a waiter could proceed after the unlock, perhaps because of a spurious wakeup, and free the queue before the producer signals. The queue must also remain alive until every thread has finished accessing its mutex and condition variable.

A signal wakes at least one eligible waiter in common condition-variable interfaces. A broadcast wakes all waiters. Use broadcast when one state change can enable several waiters or when all waiters must recheck a terminal state such as `closed`.

## Events represent persistent notification state

An **event** usually represents a Boolean condition such as "shutdown requested" or "initialization complete." Unlike a condition-variable signal, a set event commonly remains set until code explicitly clears it. A thread that starts waiting after the event is set can therefore return immediately.

The exact guarantees depend on the event implementation. Some events only wake waiters. Others also establish release/acquire ordering for data published before the event is set.

Do not infer memory ordering from the name of a primitive. Read its contract. If an event is built from a mutex and condition variable, its Boolean state should be tested under the mutex. If it is built from an atomic flag, the flag needs suitable release and acquire operations when it publishes other memory.

## Spin locks trade sleeping for repeated polling

A **spin lock** repeatedly checks until it acquires a lock instead of putting the thread to sleep. It can avoid scheduler overhead when hold times are extremely short and the owning thread is able to run.

Spinning can also waste a complete CPU core while making no progress. It performs repeated operations on a contended cache line and behaves badly when the owner is descheduled, blocks, or holds the lock longer than expected.

Spin locks are low-level implementation tools, not a default alternative to mutexes. Many mutex implementations already spin briefly before sleeping and can make that choice using platform-specific information.

Code holding a spin lock must not perform work that can block. It should also avoid callbacks, allocation, and other operations with unpredictable latency unless the primitive's design explicitly allows them.

## Synchronization does not imply fairness

A correct mutex ensures mutual exclusion, but it may not guarantee that waiting threads acquire it in arrival order. A condition variable may repeatedly wake one thread before another. Atomic CAS loops can let one thread lose many retries.

This can cause **starvation** even when the program as a whole continues to make progress. If fairness or bounded waiting is required, it must be part of the primitive's contract or enforced by a higher-level protocol.

Scheduling also affects performance. A synchronization design should not assume that a thread runs continuously between two source statements.

## Prefer locks for related state

Locks are normally preferable when:

- several fields form one invariant;
- an operation checks state and then acts on it;
- the operation changes object ownership or lifetime;
- failure cleanup must restore a consistent state; or
- the atomic alternative needs a complex ordering proof.

An atomic scalar can be appropriate when measured performance justifies it, the value is independent, and the complete operation is one load, store, exchange, or read-modify-write. An atomic load followed by an atomic store is still two operations. CAS and optimistic algorithms may be justified on measured hot paths, but they add retry behavior and lifetime problems.

The choice is not simply "mutexes are slow, atomics are fast." A contended atomic read-modify-write moves ownership of a cache line between CPU cores and can scale poorly. An uncontended lightweight mutex can be inexpensive. Algorithm structure, contention, critical-section length, architecture, and scheduler behavior all matter.

## Review a synchronization rule as a whole

Shared mutable state does not need locking when it is still unpublished, is immutable after safe publication, is local to one thread, or is accessed under a lock already required from the caller. State which exception applies rather than leaving the missing lock unexplained.

Mutexes make concurrent programs valid and understandable, but they do not make them fast automatically. The next section examines cache coherence, contention, false sharing, and other performance effects of synchronization.

---

Next: [Concurrency and performance](06-concurrency-and-performance.md)
