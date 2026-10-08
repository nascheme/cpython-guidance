# Choosing a technique

Choose synchronization from the state and the operation that need protection. Do not begin with the question, "Which primitive is fastest?"

Begin by identifying the shared mutable fields, their readers and writers, the checks and updates that must stay together, and the lifetime of every referenced object. The simplest mechanism that answers these questions is usually the best choice.

## A practical decision order

| Question | Starting point | Details |
| --- | --- | --- |
| Can sharing be removed? | Use private, immutable, per-thread, or sharded state. | [Reducing shared writes](06-concurrency-and-performance.md#sharding-reduces-shared-writes) |
| Does one Python object own the invariant? | Use its critical section. Use the two-object form if two object locks must be active together. | [Critical sections](11-cpython-critical-sections.md) |
| Does another clear owner hold related state? | Put a `PyMutex` beside that state. | [`PyMutex`](10-pymutex.md) |
| Is the value one independent scalar? | Consider a simple atomic protocol. Require measured benefit if it adds complexity. | [Atomic operations](04-atomic-operations.md) |
| Is a measured hot path limited by locking? | Consider a proven optimistic or CAS design. | [Lock-free algorithms](07-lock-free-algorithms.md) |
| Must one rare update exclude a whole interpreter or runtime? | Inside CPython's free-threaded build, consider stop-the-world. | [Stop-the-world](12-stop-the-world.md) |
| Must unlocked readers use replaced internal storage? | Inside CPython, consider QSBR. | [QSBR](13-qsbr-in-cpython.md) |

These are starting points, not automatic answers. In particular, the last two mechanisms solve different problems. Stop-the-world excludes affected execution during a change. QSBR lets old readers finish before reclamation.

## Check the qualifications before choosing

### Removing sharing needs an ownership rule

Private state needs no synchronization only while no other thread accesses it. Immutable state must be safely published. A pointer to thread-local state does not make the target private if another thread can follow it.

Sharding reduces write contention, but collecting a total may combine values from different moments. Shards still need synchronization if readers and writers overlap, and lifetime protection if their owners can destroy them.

### A critical section may release its locks

A CPython critical section is not a continuously locked lexical region. Restore the invariant before any call that can suspend the section, and revalidate dependent observations after reacquisition. Nested single-object sections do not reliably hold both locks together.

A direct `PyMutex` stays held until explicitly unlocked. Choose it when continuous ownership is necessary, but account for callback reentrancy and lock ordering. Do not call arbitrary Python while holding it without a complete deadlock argument.

Critical-section macros are no-ops in the default GIL-enabled build. Direct mutex locking works in both builds. The [build-time versus runtime distinction](09-cpython-concurrency-model.md#the-free-threaded-build-can-run-with-the-gil-enabled) matters when native threads or detached code access the state.

### Atomic operations must match the whole operation

An atomic load followed by an atomic store is still two operations. Use an indivisible read-modify-write for an independent scalar update, or a mutex when checks, related fields, and ownership changes must stay together.

State the role and memory order of each atomic operation. Relaxed ordering does not publish ordinary data. Separate atomic fields do not provide one snapshot. CAS loops add retry, ABA, and lifetime obligations; they do not automatically improve performance.

Measure the complete workload. Changing ownership or reducing shared writes can help more than weakening memory order or replacing a mutex with CAS.

### Internal mechanisms have restricted scopes

Stop-the-world and QSBR are CPython implementation details, not general public extension APIs. Extension code should normally use public ownership and locking APIs.

For stop-the-world, identify exactly which accesses the pause excludes. Keep the stopped region short, and never wait for a lock held by a suspended thread or run arbitrary Python there.

For QSBR, identify the exact retired allocation or reference and every reader covered by the protocol. A protected pointer must not survive a quiescent point. Calls that run Python or detach can end that protection, even within one C function. Delayed attached threads can retain substantial memory.

## Keep ordering and lifetime as separate checks

A pointer-based design always needs two explanations:

1. Why is loading or changing the pointer race-free and correctly ordered?
2. Why does the pointed-to object remain alive until the user finishes?

An owned reference keeps a Python object alive, but does not lock its mutable fields. Release/acquire publication makes initialization visible, but does not extend lifetime. QSBR delays reclamation, but does not provide publication ordering.

A mutex can protect both access and reference acquisition when the reader obtains its owned reference before unlocking. Do not treat a protected pointer load alone as lifetime protection.

## Give each mechanism one explicit job

A design can combine mechanisms. For example:

- an object lock serializes writers and protects related fields;
- a release store publishes a replacement pointer to acquire-loading readers;
- validation detects interference with an optimistic read; and
- QSBR delays reclaiming the old storage.

Explain why each part is needed and how every competing path follows the combined protocol. Avoid overlapping rules whose interaction is unclear.

## Review the complete protocol

Before accepting concurrent C code, verify all of the following:

1. Every shared mutable field has an owner and an access rule.
2. Every conflicting ordinary access is ordered by happens-before.
3. Related checks and updates form one protected operation.
4. Every mutex has a defined lock order and is released on every path.
5. Every atomic operation has a stated role and memory order.
6. Every pointer has a separate lifetime rule.
7. Blocking, callbacks, finalizers, and thread detachment are accounted for.
8. Lock-free code handles retries, ABA, and safe reclamation.
9. Stop-the-world code cannot wait for a suspended thread.
10. Performance complexity is supported by measurements.

Correctness comes first. A short mutex-based proof is usually better than a subtle atomic protocol. Optimize only after finding a real bottleneck, and preserve a synchronization rule that future contributors can understand.

---

[Back to contents and topic index](contents.md)
