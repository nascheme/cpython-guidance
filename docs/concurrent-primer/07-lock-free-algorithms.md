# Lock-free algorithms

Consider a lock-free alternative only when measurements justify the extra complexity over a locked design.

A lock-free algorithm coordinates threads without requiring a thread to hold a mutex around the complete operation. It usually uses atomic read-modify-write operations, especially compare-exchange, to publish a change only if shared state still has an expected value.

"Lock-free" is a progress guarantee, not a synonym for fast, simple, or free of waiting.

A lock-free design must still answer the same correctness questions as a locked design:

- Which memory accesses are atomic?
- What establishes happens-before?
- Which fields form one logical state?
- What happens when another thread intervenes?
- What keeps every accessed object alive?

The proofs are often harder because there is no mutex-delimited interval in which the shared state remains unchanged.

## Lock-free describes system-wide progress

An algorithm is **lock-free** when the system as a whole is guaranteed to make progress: after a finite number of steps, some competing operation completes. One particular thread may repeatedly lose and starve.

This differs from related progress guarantees:

- **Wait-free** means every operation completes in a finite number of its own steps, regardless of other threads. A fixed bound gives the stronger **bounded wait-free** guarantee.
- **Lock-free** means some operation completes, but an individual operation may retry without a fixed bound.
- **Obstruction-free** means an operation completes if it eventually runs without interference from other threads.

These definitions assume that threads continue taking steps and that the underlying atomic operations provide the required progress properties.

A program is not lock-free merely because its source code contains no explicit mutex. A C atomic type may use an internal lock when it is not lock-free on the platform. Memory allocation, reference counting, callbacks, and other functions called by the operation may also acquire locks.

State the scope of a progress claim. A data-structure update can be lock-free even when the larger operation containing it is not.

## CAS commits a conditional change

Compare-exchange lets an operation say: replace this value only if it currently matches the expected value. It does not prove that the value stayed unchanged since an earlier load.

For a saturating increment, first consider protecting the limit check and increment together under the counter's assigned mutex. If an independent atomic counter is justified, a CAS loop can perform both as one conditional update. An atomic load followed by an atomic store would still be two operations.

The examples use C11 atomics to show memory orders. CPython interpreter code uses the [atomic helpers described earlier](04-atomic-operations.md#use-cpythons-atomic-api-in-interpreter-code). Here is the CAS loop:

```c
#include <limits.h>
#include <stdbool.h>
#include <stdatomic.h>

bool
increment_unless_max(atomic_uint *value)
{
    unsigned int expected = atomic_load_explicit(
        value, memory_order_relaxed);

    for (;;) {
        if (expected == UINT_MAX) {
            return false;
        }

        if (atomic_compare_exchange_weak_explicit(
                value,
                &expected,
                expected + 1,
                memory_order_relaxed,
                memory_order_relaxed)) {
            return true;
        }
    }
}
```

On success, compare-exchange changes the value as one atomic read-modify-write operation. On failure, it stores the observed value into `expected`. The loop checks that value and tries again.

The weak form may fail **spuriously**, even when the value matches `expected`. Retrying is safe in this loop. Use the strong form when a single failure must mean a value mismatch rather than cause a retry.

A failed CAS is not merely an exceptional case. It normally tells the algorithm about interference, but a weak CAS may also fail spuriously. After failure, recompute every decision that depended on the old state.

The relaxed ordering above is sufficient only because this example operates on one independent integer. A CAS that publishes or consumes other memory needs appropriate acquire, release, or acquire-release ordering.

## The linearization point defines when an operation takes effect

A concurrent operation may execute many instructions while other operations overlap it. A **linearization point** is the single conceptual instant at which the operation takes effect.

For a successful CAS loop, the successful compare-exchange is often the linearization point. Before it succeeds, the proposed change is private. After it succeeds, other threads can observe the new shared state.

Identifying a linearization point helps explain whether a data structure is **linearizable**: each completed operation appears to occur atomically at some point between its call and return, in an order consistent with real-time ordering of non-overlapping operations.

Not every useful concurrent algorithm is linearizable, but an algorithm should state the consistency guarantee it provides. "Uses atomics" is not a consistency guarantee.

A linearization point addresses logical visibility. It does not prove that memory before or after the point has the right ordering, and it does not solve reclamation.

## Optimistic operations read, validate, and retry

An optimistic algorithm proceeds on the assumption that interference is uncommon. A typical operation has three stages:

1. Read a snapshot of shared state.
2. Compute or inspect using that snapshot.
3. Validate that the relevant state has not changed before committing or using the result.

If validation fails, the operation retries.

For example, a version counter can help detect concurrent updates. Matching values alone are not enough. The protocol must also detect updates in progress and order the snapshot reads with both version checks. The next section shows those requirements together.

Validation repairs neither undefined behavior nor use-after-free. The tentative reads themselves must already be permitted by the C memory model.

## Advanced example: optimistic reads need a precise protocol

This example is not lock-free: its writers use a mutex, and a paused writer can prevent readers from completing. It illustrates why optimistic validation needs a separate ordering proof. Readers interested primarily in CAS algorithms can continue to [CAS contention](#cas-can-fail-repeatedly-under-contention).

A common versioning protocol uses odd and even values. A writer changes an even version to odd before updating data, then publishes the next even version afterward. A reader accepts a snapshot only if it reads the same even version before and after copying the data.

Here is a C11 example with two integer fields. Initialize all fields with `version` set to zero, and publish the initial state safely. Keep the state alive throughout every call. Assign one writer mutex to this state. Every writer must hold it for the entire `write_snapshot()` call. Readers do not take that mutex, so every concurrent access to `version`, `x`, and `y` is atomic.

```c
#include <stdatomic.h>

struct versioned_state {
    atomic_uint version;
    atomic_int x;
    atomic_int y;
};

struct snapshot {
    int x;
    int y;
};

/* Caller holds the mutex that serializes all writers to state. */
void
write_snapshot(struct versioned_state *state, int x, int y)
{
    unsigned int version = atomic_load_explicit(
        &state->version, memory_order_relaxed);

    atomic_store_explicit(&state->version, version + 1,
                          memory_order_relaxed);  /* Odd. */
    atomic_thread_fence(memory_order_release);
    atomic_store_explicit(&state->x, x, memory_order_relaxed);
    atomic_store_explicit(&state->y, y, memory_order_relaxed);
    atomic_store_explicit(&state->version, version + 2,
                          memory_order_release);  /* Even. */
}

struct snapshot
read_snapshot(struct versioned_state *state)
{
    for (;;) {
        unsigned int before = atomic_load_explicit(
            &state->version, memory_order_acquire);
        if (before & 1u) {
            continue;
        }

        struct snapshot result = {
            atomic_load_explicit(&state->x, memory_order_relaxed),
            atomic_load_explicit(&state->y, memory_order_relaxed)
        };
        atomic_thread_fence(memory_order_acquire);
        unsigned int after = atomic_load_explicit(
            &state->version, memory_order_relaxed);
        if (before == after) {
            return result;
        }
    }
}
```

When the first acquire load reads an even release store, it observes the data published by that store. The fences handle a different case: a snapshot load that observes a later writer's data store. That store connects the writer's release fence to the reader's acquire fence. The writer's odd version store then happens-before the reader's closing version load. Atomic coherence prevents that closing load from accepting the earlier even version. This uses C11's [fence-to-fence synchronization rule](https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf), §7.17.4p2.

An acquire load for the closing check is not a replacement for the reader's fence. Acquire on that load orders accesses that follow it, not the preceding snapshot reads. Likewise, a release store of the odd version does not replace the writer's fence: release on that store publishes earlier accesses, not the following data stores.

The protocol also needs a wraparound rule. The example is valid only if the version cannot complete a full cycle during one reader attempt. A reader must not accept an equal number from a different generation.

This example does not justify copying ordinary mutable fields while a writer changes them. Validation cannot repair a C data race. Pointer-valued fields would also need a separate lifetime protocol.

Nor is this whole protocol lock-free. A writer paused with an odd version can stop all readers from completing. The writer mutex also limits the progress guarantee. Optimistic reads are not necessarily lock-free reads.

On x86-64, these acquire/release operations and fences commonly need only ordinary loads and stores with compiler ordering constraints. On weaker architectures, they can need ordering instructions. The generated code depends on the compiler and target. Passing tests on x86-64 does not prove the ordering correct.

## CAS can fail repeatedly under contention

When many threads update the same atomic object, only one expected value can win. The others fail CAS, reload or receive the new state, repeat computation, and try again.

This retry loop can generate substantial cache-coherence traffic. It may also starve one thread even while total throughput continues. Exponential backoff or bounded spinning can reduce contention in some workloads, but neither changes the underlying ownership bottleneck.

The algorithm must remain correct after any number of failures. Avoid side effects before the successful CAS unless they can be discarded or undone safely. Allocation performed for a failed attempt needs cleanup. Reference ownership acquired by an attempt needs a clear transfer or release point.

Under sustained contention, a mutex may perform better by putting waiters to sleep or handing ownership over more directly. Measure rather than assuming lock-free code scales better.

## Multi-field state needs one commit mechanism

A CAS normally updates one atomic object. Many invariants span several fields.

Updating each field atomically does not make the combined transition atomic:

```c
atomic_store_explicit(&state->pointer, new_pointer,
                      memory_order_release);
atomic_store_explicit(&state->length, new_length,
                      memory_order_release);
```

A reader can observe a new pointer with an old length or the reverse.

Lock-free designs use several techniques to commit related state:

- pack the fields into one atomic value when size and representation permit;
- publish one pointer to a complete immutable descriptor;
- use a versioned protocol that detects interference; or
- let other threads help finish an operation described by shared metadata.

Each choice adds constraints. Packed state can exhaust available bits. Immutable descriptors require memory reclamation. Versioning must handle wraparound and race-free tentative access. Helping protocols make ownership and failure cleanup more complex.

A critical section remains the normal choice for related fields of one Python object. Use a `PyMutex` assigned to the shared state when ownership is independent of a Python object. All competing readers and writers must follow the same locking rule.

## ABA defeats value-only validation

CAS checks whether the atomic object currently equals the expected value. It does not check whether the value remained unchanged throughout the interval.

Suppose a thread reads a stack head pointer `A` and loads `A`'s atomic `next` pointer, which is `C`. It plans to replace the head `A` with `C`. While it is paused, other threads:

1. remove `A` and put `B` at the head, keeping all these nodes alive;
2. atomically set `A`'s `next` pointer to `B`; and
3. put the same live node `A` back at the head.

The first thread's CAS can now succeed because the head is `A` again. It replaces `A` with its saved pointer `C`, incorrectly skipping `B`. CAS cannot detect the intervening changes. This is the **ABA problem**.

Reusing a freed node's address creates a related danger. In standard C, a saved pointer becomes indeterminate when its target's lifetime ends (§6.2.4p2). Do not treat comparison of that dangling pointer as a portable C technique. The live-node example above demonstrates ABA without relying on such a comparison.

ABA can occur with integers as well as pointers. A version counter that wraps back to an earlier value has the same shape.

Common responses include:

- pair the value with a generation counter and compare both atomically;
- prevent the old object or address from being reused while an observer may retain it;
- use a reclamation scheme whose grace period excludes dangerous reuse; or
- redesign the operation so that an equal current value is genuinely sufficient.

Comparing a pointer and a counter together may require double-width CAS. Platform support varies, and an atomic struct in `<stdatomic.h>` may use a lock. Check `atomic_is_lock_free()` before making a lock-free progress claim. CPython's `_Py_atomic_*` API has no double-width pointer-plus-counter CAS. Packing a tag into one word avoids that requirement only when the representation permits it.

A generation counter prevents ABA only if it cannot wrap during the lifetime of an outstanding observation. A larger counter makes wraparound less likely; it does not make the proof disappear.

## Removal and reclamation are separate operations

Consider a lock-free stack whose head is an atomic pointer. A pop operation might:

1. load the head pointer;
2. read `head->next`; and
3. use CAS to replace the head with `head->next`.

A successful CAS **removes** the node from the stack. It does not prove that the node can be freed.

Another thread may have loaded the same head pointer before the CAS and may still be about to read `head->next`. Freeing the node immediately creates a use-after-free. Reusing its address can also create ABA.

This leads to a fundamental rule:

> Making a pointer update atomic does not make the pointed-to object's lifetime atomic.

A safe algorithm must prevent reclamation while any reader could still hold the old pointer. This requirement often dominates the complexity of lock-free data structures.

## Reference counting alone may be too late

As explained in [chapter 5](05-synchronization.md#locks-do-not-preserve-facts-after-unlock), a reader must acquire its reference while the target is known to be alive. Loading a pointer atomically and then incrementing its reference count leaves a reclamation gap. Without the mutex-based solution, another lifetime protocol must protect that gap.

This distinction is especially important in CPython, where obtaining a pointer and owning a reference to the object are separate facts.

CPython also has specialized optimistic reference-acquisition helpers. Their writer and allocator requirements are explained with [CPython's QSBR implementation](13-qsbr-in-cpython.md#allocator-reuse-is-part-of-the-lifetime-problem); they are not general replacements for ordinary reference acquisition.

## Safe reclamation delays freeing

Lock-free algorithms use several families of memory-reclamation techniques:

- **Hazard pointers:** readers publish the exact objects they may access; reclaimers avoid those objects.
- **Epoch-based reclamation:** readers announce participation in an epoch; removed objects wait until all relevant readers have advanced.
- **RCU:** readers use defined read-side regions, and reclamation waits for a grace period.
- **QSBR:** threads report quiescent states at which they retain no protected references from earlier operations.

These techniques make different tradeoffs in reader cost, memory retention, thread registration, handling of stalled threads, and implementation complexity.

None of them automatically orders unrelated data or makes every access atomic. They solve the lifetime problem only when code follows their read-side and reclamation protocols.

The [next chapter](08-safe-memory-reclamation.md) develops safe memory reclamation before a later chapter describes [CPython's use of QSBR](13-qsbr-in-cpython.md).

## Lock-free code needs a complete proof

A lock-free design needs to explain:

1. Each operation's linearization point, or its stated consistency guarantee.
2. What retries recompute and how failed attempts discard or undo side effects and transfer or release ownership.
3. Why tentative reads are legal under the C memory model.
4. How ABA is prevented or shown to be harmless.
5. How reclamation keeps removed objects alive for existing readers.
6. The scope of the progress guarantee, including called functions.

If any part depends on "the window is very small" or "the address probably will not be reused," the algorithm is not complete. A mutex often provides a shorter correctness argument and better behavior than an unproven lock-free alternative.

---

Next: [Safe memory reclamation](08-safe-memory-reclamation.md)
