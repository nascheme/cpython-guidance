# Safe memory reclamation

A concurrent data structure can stop making an object reachable before it is safe to free the object's memory. Another thread may already hold a pointer obtained before the removal.

This creates two separate events:

1. **Logical removal:** new operations can no longer find the object through the shared data structure.
2. **Physical reclamation:** the object's storage is destroyed, reused, or returned to the allocator.

A mutex can make these events easy to coordinate. Lock-free readers need a separate **safe memory reclamation** protocol.

The usual rule is:

> Do not reclaim removed storage until every reader that could have observed it has finished using it.

A specialized alternative permits limited reuse within protected backing storage. It preserves the layout needed for speculative accesses and requires readers to validate the result. CPython uses this approach for some allocator pages, as described below.

## An atomic pointer does not protect its target

The examples use C11 atomics to show memory orders. CPython interpreter code uses the [atomic helpers described earlier](04-atomic-operations.md#use-cpythons-atomic-api-in-interpreter-code).

Consider a shared atomic pointer:

```c
struct node {
    struct node *next;
    PyObject *value;
};

static _Atomic(struct node *) head;
```

Assume the node's fields are initialized before publication and never change afterward. The node owns a strong reference to `value` until destruction. Even with those assumptions, this reader is unsafe:

```c
struct node *node = atomic_load_explicit(
    &head, memory_order_acquire);
if (node != NULL) {
    use_value(node->value);
}
```

A writer can remove the node with compare-exchange. The update to `head` may be completely correct while the reader still holds the old pointer.

If the writer immediately calls `free(node)`, the reader may access freed memory. Reuse of the address does not restore the old object's lifetime. It can also create an ABA problem. Ordinary C code cannot safely inspect a freed node and then validate the result.

Acquire ordering on the load does not solve this problem. Acquire can make initialization visible. It does not announce that a reader is still using the object.

## Grace periods separate removal from reclamation

Many reclamation schemes use the idea of a **grace period**. A grace period after removal ends when all readers that could have observed the removed object have passed a point where they can no longer retain it.

The writer can then reclaim the object:

```text
publish removal
       |
       v
wait for a grace period
       |
       v
run destruction and free storage
```

The exact meaning of a grace period depends on the scheme. It may require every old reader to leave a read-side region, every participating thread to advance to a later epoch, or every hazard-pointer slot to stop naming the object.

A grace period protects only readers covered by its protocol. One unregistered reader can invalidate the proof.

## Reclamation needs a defined reader scope

A safe scheme identifies where a reader can first obtain a protected pointer and where it definitely stops using that pointer.

Conceptually, a read-side region looks like this:

```c
enter_read_side();
struct node *node = load_shared_node();
use_node(node);
leave_read_side();
```

The contract must answer:

- Can the reader block inside the region?
- Can it retain the pointer after leaving?
- Can it pass the pointer to another thread?
- Which memory accesses establish ordering with the reclaimer?
- What happens when a participating thread exits?
- What happens when a thread remains in a region indefinitely?

Do not hide the scope in an informal comment such as "the pointer should still be valid." Make entry, exit, or protection visible in the API.

## Hazard pointers protect named objects

A **hazard-pointer** scheme gives each participating thread one or more shared slots. A reader publishes the exact object it intends to access. A reclaimer scans the slots and does not free any object currently named by a hazard pointer.

Publishing a hazard pointer requires validation and store-load ordering. A reader cannot safely load a pointer and then publish it without checking whether removal occurred in between.

This sketch uses sequentially consistent operations for publication and validation:

```c
struct node *node;

do {
    node = atomic_load_explicit(&head, memory_order_acquire);
    atomic_store_explicit(&my_hazard, node, memory_order_seq_cst);
} while (node != atomic_load_explicit(
                    &head, memory_order_seq_cst));

if (node != NULL) {
    use_node(node);
}

atomic_store_explicit(&my_hazard, NULL, memory_order_release);
```

The reclaimer needs matching ordering. For this simple version, every update to `head` and every scan load of a hazard slot must also be `memory_order_seq_cst`. This orders hazard publication before validation, and unlinking before scanning. An acquire reload alone does not supply this store-load ordering in C. Weaker variants need a proven fence protocol.

With both sides following the protocol, either validation detects removal or the hazard prevents reclamation until the reader finishes its protected access. The reader discards a failed candidate without dereferencing it and retries.

This is a protocol sketch, not a complete portable allocation implementation. Hazard-slot ownership, scanning rules, and protection when following nested pointers still need a proof. The implementation also needs explicit pointer-lifetime assumptions: in strict C, a saved pointer becomes indeterminate when its target's lifetime ends. Even publishing or comparing such a pointer needs justification. See [C11 §6.2.4p2 and §7.17.3](https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf).

Writers normally place removed objects on a retired list. After enough objects accumulate, they scan all hazard slots and reclaim retired objects that are absent.

Hazard pointers can reclaim promptly and tolerate a stalled reader without retaining every retired object. Their costs include strong store-load ordering on read paths, global scanning, and a limited number of protected pointers per thread. Following a chain of objects needs careful protection at each step.

The store-load ordering may require a CPU fence or a strongly ordered read-modify-write instruction. It is not merely the cost of an atomic store. The generated instructions and their cost depend on the implementation and architecture.

## Epoch-based reclamation groups readers

**Epoch-based reclamation** divides executions into generations. A reader announces that it is active in the current epoch before accessing protected data. A removed object is tagged with an epoch and retired.

The object can be reclaimed after every reader that might have observed it has either:

- left its read-side region; or
- announced participation in a sufficiently new epoch.

Readers do not need to publish each pointer. This can make their fast path cheaper than hazard pointers. The tradeoff is coarser reclamation: one delayed reader can prevent reclamation of many unrelated objects retired after it entered.

Epoch wraparound and thread registration are part of the correctness proof. Comparing bounded counters as ordinary integers is not enough when they can wrap.

## RCU makes read-side work cheap

**Read-copy-update**, or **RCU**, is a family of techniques for read-mostly structures. Writers create a new version, publish it, and wait for old readers to finish before reclaiming the replaced version.

A common pattern is:

1. Readers enter a lightweight read-side region.
2. A writer builds replacement state without modifying the visible snapshot.
3. The writer atomically publishes the replacement.
4. The writer waits for a grace period.
5. The old state is reclaimed.

RCU is not one universal C API. Kernel RCU, userspace RCU, and application-specific schemes have different rules for preemption, blocking, pointer access, and barriers.

The name does not prove that arbitrary ordinary loads and stores are valid. The implementation must still express the required C memory ordering and prevent conflicting non-atomic access.

## QSBR reports points with no old references

**Quiescent-state based reclamation**, or **QSBR**, is an epoch-like scheme in which each participating thread periodically reports a **quiescent state**. At that point, the thread promises that it holds no protected pointer obtained before the report.

A reclaimer tags removed storage with a target sequence or epoch. Once every relevant thread has reported a quiescent state at or beyond that target, no old reader can still use the storage, and reclamation is safe.

QSBR can have very low read-side overhead when an application already has natural quiescent points. It also depends strongly on timely cooperation. One active thread that stops reporting can block reclamation of every item retired since its last report in the same QSBR instance. This can include unrelated data structures.

A detached or inactive thread may be treated as quiescent, but only if the implementation guarantees that it cannot retain and dereference protected pointers while in that state.

The later chapter on [QSBR in CPython](13-qsbr-in-cpython.md) explains how evaluation-loop checkpoints and thread-state transitions supply these quiescent points.

## Stalled threads trade safety for memory retention

Safe reclamation must remain safe when a thread is delayed at the worst possible point. A reader may be descheduled after obtaining a pointer and before releasing its protection.

A correct scheme does not free the object merely because the reader has taken a long time. It delays reclamation instead. This can increase memory use without blocking logical updates.

Different schemes localize the delay differently:

- A hazard pointer held by a stalled reader normally protects the named objects.
- An old epoch held by a stalled reader may retain every object retired in later relevant epochs.
- QSBR may be unable to complete a grace period until the thread reports a quiescent state.

Operational limits do not replace correctness. Timing out and freeing anyway creates a use-after-free unless the protocol can prove that the stalled thread can no longer run or access the pointer.

## Thread exit and detachment require cleanup

Reclamation metadata is often stored per thread. A thread must register before participating and correctly unregister when it exits.

The implementation must not leave an exited thread permanently blocking an epoch. It must also not discard the thread's protection while the thread can still execute a read-side operation.

Cancellation, interpreter shutdown, process forking, and abnormal extension behavior make this lifecycle more difficult. Thread metadata should have explicit ownership and state transitions rather than relying only on thread-local destructors.

## Reclamation and destruction are different concerns

A grace period proves that covered readers no longer access the retired storage. The program must still destroy it correctly.

Destruction may:

- decrement references to other objects;
- invoke user-defined finalizers;
- acquire locks;
- allocate memory;
- enqueue more deferred work; or
- reenter the data structure.

A polling path that discovers an object is reclaimable may not be a safe place to run arbitrary destruction. Some systems separate the cheap decision that an item is safe from the later execution of its destructor in an appropriate thread or state.

For a Python object, memory lifetime also interacts with reference counting and cyclic garbage collection. QSBR is not a replacement for those mechanisms. Chapter 13 explains [delayed decrefs](13-qsbr-in-cpython.md#delayed-frees-and-decrefs-connect-lifetime-to-qsbr) and when their destructors can run.

## Type-stable storage allows limited reuse

Some schemes preserve backing storage without keeping each removed object alive. This is often called **type-stable memory**. An allocation can be reused during the grace period, but the layout of fields that readers may inspect must remain suitable for those accesses. Readers must validate before using the result as an owned object.

Type-stable storage does not preserve the removed object's identity or permit arbitrary access to its former fields. Validation alone also does not make freed-pointer use portable C. Such a design needs explicit implementation guarantees for every speculative access.

Chapter 13 develops [CPython's allocator-page retention and reference-acquisition protocol](13-qsbr-in-cpython.md#allocator-reuse-is-part-of-the-lifetime-problem) as a specialized example.

## Ordering and lifetime remain separate proofs

A reclamation protocol answers whether an address remains valid. It does not necessarily answer whether the reader sees initialized or mutually consistent contents.

A complete lock-free publication needs both:

1. **Ordering:** for example, a release store publishes initialization to an acquire load.
2. **Lifetime:** for example, a hazard pointer or QSBR grace period prevents reclamation while the reader uses the result.

Conversely, an object can remain allocated while concurrent ordinary accesses to its mutable fields still form a C data race.

Keep these questions separate in code review:

- May this thread legally read the pointer and fields?
- Does it observe the required version of their contents?
- What prevents the storage from being destroyed or reused?

## Choose reclamation from the reader contract

Before selecting a reclamation scheme, determine:

- how frequently reads and removals occur;
- whether readers can explicitly enter and leave regions;
- whether natural quiescent points exist;
- whether readers may block or retain pointers for a long time;
- how many pointers one reader needs simultaneously;
- how promptly memory must be returned;
- how threads register, detach, and exit; and
- where destructors may safely run.

Prefer a critical section for per-object state, or a `PyMutex` for independently owned shared state. For the node example, assign one mutex to `head` and its reachable nodes. Every reader must hold it while loading `head` and using the node. Every writer must hold it while updating `head` or linking or unlinking nodes. Once unlinking completes under that rule, no reader can still use the removed node. A pointer must not escape the lock unless the reader first acquires separate lifetime protection.

Safe memory reclamation is justified when measurements show that unlocked readers matter enough to carry the additional protocol and delayed-memory costs.

The [next chapter](09-cpython-concurrency-model.md) turns to CPython's overall concurrency model. It explains which assumptions the GIL once supplied and which mechanisms the free-threaded build uses instead.

---

Next: [CPython's concurrency model](09-cpython-concurrency-model.md)
