# The C memory model

The C memory model defines how operations in different threads relate to each other. It answers questions such as:

- When may one thread observe a write from another thread?
- When is it safe to access ordinary shared memory?
- What ordering does a mutex or an atomic operation provide?

The model does not describe one global timeline that contains every operation in a simple order. Instead, it defines several kinds of ordering. The most important result is **happens-before**.

The central rule is:

> Conflicting ordinary memory accesses must be ordered by happens-before.

If they are not ordered, they form a data race and the program has undefined behavior.

## `sequenced-before` orders operations within a thread

Within one thread, C uses the term **sequenced-before**. If operation A is sequenced-before operation B, A comes before B in the abstract machine.

For example:

```c
result = compute_result();
ready = 1;
```

The call and assignment in the first statement are sequenced-before the assignment in the second statement.

`sequenced-before` is a language rule. It does not require the compiler to emit instructions in exactly that order. The compiler may reorder instructions when doing so preserves every behavior that C requires.

It is also only an order within one thread. By itself, it says nothing about what another thread can observe.

## `synchronizes-with` connects threads

Threads need a synchronization operation to establish an ordering between them. C calls one important form of this connection **synchronizes-with**.

Examples include:

- releasing a mutex and then acquiring that mutex in another thread; and
- an atomic release store and an acquire load of the same object that reads the stored value.

A synchronizes-with relationship carries information from one thread to another. Operations before the release can become ordered before operations after the acquire.

Not every atomic operation creates this relationship. Relaxed atomic operations are atomic, but they do not synchronize threads by themselves. With suitable fences, relaxed loads and stores can participate in synchronization. The [atomic-operations chapter](04-atomic-operations.md) introduces fences and the available memory orders.

An acquire can also synchronize with a release by reading a value from its **release sequence**. For example, consider a relaxed read-modify-write immediately after a release store in that object's modification order. That operation extends the release sequence. An acquire that reads the read-modify-write's value still synchronizes with the original release.

## `happens-before` combines the ordering

**Happens-before** combines ordering within a thread with synchronization between threads. The two relationships have different roles:

- `sequenced-before` orders operations within one thread.
- `synchronizes-with` connects an operation in one thread to an operation in another thread.

Happens-before is the resulting order. In simplified terms, A happens-before B when there is a path from A to B made from these ordering relationships. The path may cross between threads, and it may contain several steps.

This explanation excludes C11/C17's dependency-based `memory_order_consume`. With consume excluded, happens-before is transitive: if A happens-before B, and B happens-before C, then A happens-before C. Use acquire for the publication patterns shown here.

Consider a writer and reader that use a mutex. Here, `lock` protects both `shared->result` and `shared->ready`. Every reader and writer of these fields must hold that same mutex:

```c
/* Writer */
lock_mutex(&lock);
shared->result = result;
shared->ready = 1;
unlock_mutex(&lock);
```

```c
/* Reader */
lock_mutex(&lock);
if (shared->ready) {
    use_object(shared->result);
}
unlock_mutex(&lock);
```

The writes are sequenced-before the writer unlocks the mutex. The unlock synchronizes-with a later lock operation that acquires the mutex. That lock is sequenced-before the reader's accesses.

Together, these relationships order the writer's accesses before the reader's accesses. The ordinary, non-atomic fields can be used safely while every conflicting access follows this locking rule.

These snippets assume that `shared` stays alive. If `shared->result` is a pointer, its target must also stay alive through `use_object()`. Ordering accesses to the pointer does not, by itself, keep its target alive.

Happens-before is not a measurement of wall-clock time. It is a guarantee provided by the C model. Two operations can occur at different physical times without having a happens-before relationship.

## Publishing data with release and acquire

A mutex is usually the simpler way to protect mutable state. Atomic operations can also establish happens-before, as this publication example shows.

Here is a one-time publication example. One writer initializes `result`, sets `ready` to `1`, and never changes either value again. Readers access `result` only after an acquire load of `ready` returns `1`:

```c
#include <stdatomic.h>

static int result;
static atomic_int ready = 0;
```

The writer initializes `result` and then publishes it:

```c
result = 42;
atomic_store_explicit(&ready, 1, memory_order_release);
```

The reader uses an acquire load:

```c
if (atomic_load_explicit(&ready, memory_order_acquire) == 1) {
    use_result(result);
}
```

If the acquire load reads the value stored by the release operation, the release synchronizes-with the acquire. The complete ordering is:

1. The write to `result` is sequenced-before the release store.
2. The release store synchronizes-with the acquire load that observes it.
3. The acquire load is sequenced-before the read of `result`.

Therefore, the write to `result` happens-before the read of `result`. The reader that observes `ready == 1` may safely read `42`.

Do not modify `result` after publication unless additional synchronization orders that write with every reader. This applies to writes by the publishing thread and by any other thread. The release store orders earlier writes, not future ones. Resetting `ready` does not make reuse safe: a reader may already have observed `1` and be about to read `result`.

The acquire operation must actually observe the published value. If it reads `0`, this release/acquire pair has not established the relationship, and the reader must not use `result`.

If both operations on `ready` were relaxed, access to `ready` itself would still be atomic. However, the operations would not publish the ordinary `result` object. The write and read of `result` would not be ordered by happens-before and would form a data race.

## Atomicity and ordering are different guarantees

An **atomic** access is indivisible as defined by the C model. Other threads do not observe an atomic object partway through one atomic operation.

Ordering is a separate question. It determines how an operation relates to accesses to other memory.

A relaxed atomic load or store provides atomicity for its own object. It does not, by itself, order nearby ordinary accesses. An acquire or release operation adds ordering in one direction. A matching release/acquire pair can order accesses to other objects. Sequentially consistent operations provide a stronger model.

This distinction is essential:

> Atomic does not automatically mean synchronized.

Atomic operations on the same object do not form a C data race with each other. They can still produce a race condition at the program level. For example, a separate atomic load and atomic store do not make a complete read-modify-write operation indivisible.

Protect the complete update with the object's critical section or the mutex assigned to that state. An atomic read-modify-write primitive is an alternative when performance justifies it.

The next chapter explains how [CPython's atomic helpers](04-atomic-operations.md#use-cpythons-atomic-api-in-interpreter-code) apply these rules to ordinary C fields.

## Each atomic object has a modification order

C gives each atomic object its own **modification order**. This is a total order of all modifications to that atomic object. Stores and successful read-modify-write operations are modifications.

All threads must observe a history that is consistent with this order and the other memory-model rules. An atomic object cannot have one modification ordered before another modification for one thread and the opposite way around for another thread.

The modification order belongs to one atomic object. Relaxed and acquire/release operations do not, by themselves, provide a single total order across different atomic objects. Sequentially consistent operations additionally participate in one total order shared by all threads. That order does not include non-sequentially-consistent operations.

For example, suppose `x` and `y` are separate atomic integers. One thread changes `x`, and another thread changes `y`. The modification order of `x` does not by itself determine where the change to `y` belongs. Extra synchronization is needed when the two values represent one related state.

## Compiler and CPU ordering are different layers

Both the compiler and the CPU affect how memory operations execute.

The compiler translates C operations into instructions. It can reorder or combine work when the C model permits it. Atomic operations and synchronization limit that freedom.

The CPU executes the generated instructions. It may use store buffers, out-of-order execution, and speculative execution. These mechanisms can make memory operations visible to other CPU cores in an order that differs from a simple reading of the instruction stream. Cache coherence keeps cached copies of each memory location consistent. It does not impose one order on accesses to different locations.

Calling a bug a "reordering bug" does not identify which layer is responsible. More importantly, trying to block one compiler transformation or one hardware behavior is not a complete fix. The source code must express the required relationship through the C memory model.

## AMD64 and ARM64 provide different hardware ordering

AMD64 has a relatively strong hardware memory model. Loads and stores preserve many ordering relationships without special fence instructions. However, AMD64 is not fully sequentially consistent. Store buffers allow a later load to proceed before an earlier store has become visible to other cores.

ARM64 has a weaker hardware memory model. Without suitable ordering instructions, it permits more observations in which loads and stores to different locations appear reordered. Code that seems to work on AMD64 can therefore fail more readily on ARM64.

This difference affects how compilers implement C atomics. For example, an acquire load or release store often needs no instruction beyond an ordinary load or store on AMD64. On ARM64, the compiler commonly uses load-acquire and store-release instructions such as `LDAR` and `STLR`. On suitable ARM64 targets, it may use `LDAPR` for an acquire load instead.

Acquire and release operations are not always CPU fences. The [performance chapter](06-concurrency-and-performance.md#atomic-does-not-mean-inexpensive) compares instruction costs and explains why cache contention can matter more than memory order.

These implementation differences should not change the meaning of correct C code. The same release/acquire publication example must work on both AMD64 and ARM64. The compiler is responsible for selecting instructions that implement the C guarantees.

This is the purpose of a language memory model: write the synchronization requirement once, then let each platform implement it correctly.

## Use the model to explain why an access is safe

For each ordinary shared access, identify the chain that orders it with conflicting accesses. A useful explanation has this form:

1. These writes occur while holding a particular mutex, or before a particular release operation.
2. This mutex acquisition or acquire operation synchronizes with the release.
3. These reads occur after the acquisition.
4. Therefore, the writes happen-before the reads.
5. Every other conflicting access follows a synchronization rule too. For example, no unordered write to the published data can occur after publication.

Check every reader and writer, not just one successful publication. If no such chain exists, source order and expected CPU behavior are not substitutes.

The [next chapter](04-atomic-operations.md) describes atomic operations and their memory-order options in more detail.

---

Next: [Atomic operations](04-atomic-operations.md)
