# Atomic operations

Prefer a critical section for mutable per-object state, or a `PyMutex` for independently owned shared state. Atomics are an alternative for independent scalar state when measured performance justifies the extra complexity.

Atomic operations let threads access one object without creating a C data race. Each atomic operation is indivisible as defined by the C memory model. A thread cannot observe half of an atomic store or half of an atomic read-modify-write operation.

Atomicity solves only part of a synchronization problem. The operation's **memory order** determines how it relates to accesses to other objects.

The central distinction is:

> Atomicity controls one operation on one object. Ordering controls how that operation publishes or observes other memory.

## Atomic objects require atomic access

The examples below use C11 names to explain the operations and memory orders. For CPython interpreter code, use the `_Py_atomic_*` helpers or the existing `FT_ATOMIC_*` wrappers, not new `_Atomic` declarations. The [CPython API section](#use-cpythons-atomic-api-in-interpreter-code) maps the concepts to those interfaces.

C provides atomic types through `<stdatomic.h>`. For example:

```c
#include <stdbool.h>
#include <stdatomic.h>

static atomic_int requests = 0;
static atomic_bool stopped = false;
```

Operations on these objects can use the default sequentially consistent ordering:

```c
atomic_store(&stopped, true);
bool value = atomic_load(&stopped);
```

They can also state the memory order explicitly:

```c
atomic_store_explicit(&stopped, true, memory_order_release);
bool value = atomic_load_explicit(&stopped, memory_order_acquire);
```

Use atomic operations consistently for an atomic object's concurrent accesses. Do not access the same storage concurrently through an ordinary, non-atomic lvalue. Mixing atomic and non-atomic accesses does not preserve the atomic guarantees and can create a data race.

Plain-looking expressions on C11 atomic types are still atomic and sequentially consistent. For example, `stopped = true` is an atomic store, and `requests++` is an atomic read-modify-write. This rule does not apply to CPython's ordinary fields merely because some accesses use atomic helpers.

An atomic type does not guarantee a lock-free machine instruction. C implementations may use an internal lock for some types or on some platforms. Code can query this property when it genuinely needs to know, but correctness must not depend on an assumption that every atomic type is lock-free.

## Loads and stores transfer individual values

An atomic load reads one value of an atomic object. An atomic store writes one value. These operations prevent torn access to that object. Stores are added to the object's modification order. Loads read a value from that order, subject to the memory model's coherence rules.

For example, a statistics counter may only need a race-free snapshot:

```c
static atomic_int active_requests = 0;

int
get_active_requests(void)
{
    return atomic_load_explicit(
        &active_requests, memory_order_relaxed);
}
```

The load is safe even while another thread changes the counter atomically. It does not promise that the returned value remains current after the load. Another thread may change the counter immediately.

This is a general property of concurrent observations. An atomic load returns one value from the object's initialization or a modification. It need not return the latest stored value. The memory model has no single global instant, and the load does not freeze the surrounding state.

## Read-modify-write is one indivisible operation

Protect a complete update with the object's critical section or the `PyMutex` assigned to that shared state. Every reader and writer of the protected fields must follow the same locking rule. An atomic read-modify-write is an alternative for an independent scalar when performance justifies it.

A **read-modify-write** operation reads an atomic object's old value and writes a new value as one atomic operation. Examples include exchange, fetch-add, fetch-subtract, and compare-exchange.

Suppose several threads increment a counter. This code is incorrect:

```c
int old = atomic_load_explicit(&requests, memory_order_relaxed);
atomic_store_explicit(&requests, old + 1, memory_order_relaxed);
```

Each individual access is atomic, so there is no C data race on `requests`. However, the complete increment is not atomic. Two threads can load the same value and both store the same incremented value. One increment is lost.

If `requests` is an independent atomic counter, use one atomic read-modify-write operation instead:

```c
atomic_fetch_add_explicit(&requests, 1, memory_order_relaxed);
```

The load and update now form one operation in the modification order of `requests`.

A mutex is often the clearer solution when an update includes several fields, checks, failure cases, or object-lifetime changes. Making each field atomic does not make the complete state transition atomic.

## Exchange replaces a value

An atomic exchange stores a new value and returns the previous value:

```c
bool was_stopped = atomic_exchange_explicit(
    &stopped, true, memory_order_acq_rel);
```

Unlike a separate load followed by a store, exchange is one read-modify-write operation. This is useful when only one thread should observe that it changed a state from one value to another.

The required memory order depends on what the state means. If `stopped` is only an independent Boolean value, relaxed ordering may be enough. If changing it publishes or consumes other memory, it may need release, acquire, or acquire-release ordering.

## Compare-exchange updates conditionally

Compare-exchange, often called **compare-and-swap** or **CAS**, updates an atomic object only when it contains an expected value. Conceptually, it performs this operation atomically:

```c
if (current == expected) {
    current = desired;
    return true;
}
expected = current;
return false;
```

The actual C interface updates the caller's `expected` variable on failure. Here is a loop for an independent integer state. `can_advance()` and `next_state()` depend only on the integer argument. They do not read related shared data or perform side effects. No other memory is published, so all orders are relaxed:

```c
static atomic_int state = 0;

bool
advance_state(void)
{
    int expected = atomic_load_explicit(&state, memory_order_relaxed);

    do {
        if (!can_advance(expected)) {
            return false;
        }
    } while (!atomic_compare_exchange_weak_explicit(
        &state,
        &expected,
        next_state(expected),
        memory_order_relaxed,
        memory_order_relaxed));

    return true;
}
```

If another thread changes `state`, the compare-exchange fails and writes the newly observed value into `expected`. The loop checks that value and tries again. The check and state calculation may run several times. Keep effects that must occur only once out of this retry loop.

A weak compare-exchange may also fail even when the values compare equal. This is called a **spurious failure**. It is suitable for loops that retry. A strong compare-exchange does not fail spuriously and is useful when the operation will not normally be retried.

Compare-exchange accepts separate memory orders for success and failure. Success performs a read-modify-write and can both acquire and release. Failure performs only a load, so its order cannot include release semantics. In C11/C17, the failure order must also be no stronger than the success order.

CAS makes the update of the atomic object conditional and indivisible. It does not automatically protect objects reached through a stored pointer. A successful CAS that removes a pointer from a data structure does not prove that no reader still holds the old pointer.

## Relaxed ordering provides atomicity only

`memory_order_relaxed` provides atomic access and respects the atomic object's modification order. A relaxed operation by itself does not create a synchronizes-with relationship or order accesses to other objects.

Relaxed operations can participate in synchronization when combined with suitable fences. A relaxed read-modify-write can also extend a release sequence, as described below.

Relaxed ordering is appropriate when only the atomic value matters. Approximate statistics and independent counters are common examples:

```c
atomic_fetch_add_explicit(&requests, 1, memory_order_relaxed);
```

It is not sufficient merely because every shared field is atomic. If several values represent one invariant, other threads may observe them at different stages of an update.

Relaxed ordering is also insufficient for the [publication example in chapter 3](03-the-c-memory-model.md#publishing-data-with-release-and-acquire). Making its `ready` accesses relaxed would leave the ordinary accesses to `result` unordered, even though the flag itself remained race-free.

## Release publishes earlier work

Write the data to be published before the release operation. A release can order those earlier accesses before accesses in another thread that performs a matching acquire.

```c
result = 42;
atomic_store_explicit(&ready, 1, memory_order_release);
```

A release operation alone is not enough. Another thread must perform a corresponding acquire operation and read the release store's value, or a value from its **release sequence**.

For example, later read-modify-write operations on `ready` can extend that release sequence. They must follow the release store in modification order without an intervening store by another thread. Even a relaxed read-modify-write can carry the publication forward this way.

Release ordering is available for stores and read-modify-write operations. A plain load cannot have release ordering.

## Acquire observes published work

An acquire operation can observe work published by a release operation:

```c
if (atomic_load_explicit(&ready, memory_order_acquire) == 1) {
    use_result(result);
}
```

When this acquire load reads the value from the release store, the release synchronizes-with the acquire. The write to `result` then happens-before the read of `result`. An acquire that reads from the release sequence also synchronizes with the release that heads it.

The one-time publication and no-reuse constraints from chapter 3 still apply.

Acquire ordering constrains operations that follow it. It does not publish earlier work from the acquiring thread.

Acquire ordering is available for loads and read-modify-write operations. A plain store cannot have acquire ordering.

## Acquire-release combines both directions

Use `memory_order_acq_rel` for a read-modify-write that needs both directions of ordering. Its acquire half can observe work published by a release whose value it reads, including through a release sequence. Its release half can publish writes this thread made before the operation.

For example, a state-machine transition may need to acquire initialization associated with the old state and release data associated with the new state. Write any data to be published before the read-modify-write. Writes made afterward are not published by its release half.

Do not choose acquire-release merely because it sounds safer. First identify what memory the operation must acquire, what memory it must release, and which atomic value carries the synchronization.

## Sequential consistency provides a stronger default

`memory_order_seq_cst` provides acquire or release effects as appropriate for the operation. It also places sequentially consistent operations in one total order that all threads must respect.

This stronger model often makes code easier to reason about. It is the default for C atomic operations when no explicit memory order is given:

```c
atomic_fetch_add(&requests, 1);
```

Sequential consistency does not turn several operations into one transaction. Another thread can still run between two sequentially consistent operations. It also does not protect ordinary data unless the required happens-before relationship exists.

Use the weakest order only when its correctness argument is clear and the choice is justified. Stronger ordering may constrain the compiler or require different instructions on some architectures, but contention on the cache line can dominate the cost. Measure before replacing a clear design with a subtle one.

## Use CPython's atomic API in interpreter code

CPython's portable layer is documented in [`Include/cpython/pyatomic.h`](https://github.com/python/cpython/blob/main/Include/cpython/pyatomic.h). Include `Python.h`, not that header directly. The implementation selects compiler builtins, C11 atomics, or MSVC intrinsics. Do not assume every supported compiler provides usable C11 atomics.

The helpers take addresses of ordinary fields, such as `int` or `PyObject *`. The declaration does not enforce atomic access. Use helpers for every access that can conflict concurrently with an atomic access. An ordinary read racing with an atomic store is still unsafe. Plain accesses during unpublished construction, or after all concurrent users have finished, do not have that conflict.

These examples map the C11 concepts to CPython's interfaces:

| Operation | CPython helper | Ordering and result |
| --- | --- | --- |
| Load a pointer | `_Py_atomic_load_ptr_acquire(&current)` | Acquire; returns the pointer |
| Store a pointer | `_Py_atomic_store_ptr_release(&current, obj)` | Release |
| Add to a counter | `_Py_atomic_add_ssize(&requests, 1)` | Sequentially consistent; returns the old value |
| Replace an integer | `_Py_atomic_exchange_int(&state, desired)` | Sequentially consistent; returns the old value |
| Conditional update | `_Py_atomic_compare_exchange_int(&state, &expected, desired)` | Strong, sequentially consistent CAS; reports success and updates `expected` on failure |

In this table, `requests` is an ordinary `Py_ssize_t`, and `state` and `expected` are ordinary `int` variables. The CAS helper has no memory-order arguments. Unsuffixed `_Py_atomic_*` operations are sequentially consistent. Suffixes such as `_relaxed`, `_acquire`, and `_release` select other orders where the API provides them.

Interpreter code also uses [`FT_ATOMIC_*` wrappers](https://github.com/python/cpython/blob/main/Include/internal/pycore_pyatomic_ft_wrappers.h). For example, `FT_ATOMIC_LOAD_PTR_ACQUIRE(current)` takes the field itself, rather than its address. These wrappers use atomic helpers when `Py_GIL_DISABLED` is defined. In the default GIL-enabled build, where it is not defined, they expand to ordinary accesses. Those accesses need another safety rule, such as holding the GIL.

This is a compile-time distinction. Re-enabling the GIL at runtime in a free-threaded build does not change the wrappers' expansion. Use a wrapper only when ordinary access is safe in the default build. Use unconditional `_Py_atomic_*` helpers when atomic access is required in both builds.

## Fences order without carrying the value operation

An atomic fence imposes ordering constraints without itself loading or storing the shared value:

```c
atomic_thread_fence(memory_order_acquire);
```

A release fence followed by a relaxed store can synchronize with an acquire fence after a relaxed load that reads that store's value. The atomic store and load carry the communication; fences alone are not enough.

Fences are useful in some low-level algorithms, but their synchronization rules are less direct than placing acquire or release ordering on the atomic operation that carries the communication.

Prefer an acquire load, release store, or suitable read-modify-write operation when it expresses the protocol. Use a fence only when the algorithm has a specific fence-based proof.

## Atomics do not solve object lifetime

An acquire load of a pointer can observe initialized contents, but it does not keep the target alive. The lifetime problem introduced in chapter 1 still needs a separate solution: [reference acquisition under a mutex](05-synchronization.md#locks-do-not-preserve-facts-after-unlock), or a [safe reclamation protocol](08-safe-memory-reclamation.md) for unlocked readers.

## Choose atomics for a complete, explainable protocol

Before using an atomic operation, answer these questions:

- Which object is atomic?
- Is the operation a load, store, or indivisible read-modify-write?
- Does the value stand alone, or does it publish other memory?
- Which release operation synchronizes with which acquire operation?
- What happens if a compare-exchange fails and retries?
- What protects related invariants across several fields?
- What keeps any pointed-to object alive?

If the answers require a long proof, a mutex may be the safer design. The [next chapter](05-synchronization.md) explains synchronization primitives that protect complete operations and invariants directly.

---

Next: [Synchronization](05-synchronization.md)
