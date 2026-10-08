# Concurrency and performance

Correct synchronization defines which results a concurrent program may produce. Performance depends on how the compiler, CPU, cache hierarchy, operating system, and workload implement that synchronization.

A design with more threads is not automatically faster. Threads may compete for locks, move cache lines between CPU cores, exhaust memory bandwidth, or duplicate work after failed optimistic operations.

Measure the real workload before replacing a clear synchronization rule with a more complicated one.

## CPU cores communicate through a cache-coherence system

Modern CPU cores have private caches. A core usually reads and writes cached copies of memory rather than accessing main memory for every operation.

A hardware **cache-coherence** protocol keeps these copies consistent. At a conceptual level, a core must obtain suitable ownership of a cache line before modifying it. Other cores' copies are then invalidated or updated according to the architecture's protocol.

Coherence and the C memory model solve different problems:

- The C memory model defines which concurrent source programs have valid behavior and what ordering their operations require.
- The cache-coherence protocol helps the hardware implement memory operations between cores.

Coherent hardware does not make a C data race valid. It also does not imply that all operations have one sequentially consistent order.

## Coherence works at cache-line granularity

Caches transfer and track memory in fixed-size **cache lines**. A 64-byte line is common on AMD64 and many ARM64 systems. Some systems, including Apple M-series systems, use 128-byte lines. Check the target platform rather than assuming that 64-byte spacing is enough.

When one core writes any byte in a cache line, the coherence protocol manages ownership of the complete line. This matters even when threads access different C objects within it.

Consider two atomic counters placed next to each other:

```c
struct counters {
    atomic_uint thread_a;
    atomic_uint thread_b;
};
```

Suppose one thread repeatedly updates `thread_a`, while another repeatedly updates `thread_b`. The C objects are distinct, and there is no data race. However, they may occupy the same cache line.

Each write can force the line to move between the two cores. This is **false sharing**: the threads do not logically share the counters, but the hardware treats their storage as one coherence unit.

Padding or aligning frequently written fields onto separate cache lines can help after measurement confirms false sharing. It also increases memory use and can make other cache behavior worse. Do not add platform-specific padding without evidence.

## Contended writes move cache-line ownership

A cache line containing frequently modified shared state can move repeatedly between cores. This movement is sometimes called cache-line bouncing.

Atomic read-modify-write operations are especially important here. An operation such as `atomic_fetch_add()` must obtain exclusive ownership of the line and modify the value in its atomic modification order. With many writers, a single counter can serialize progress around that cache line.

Relaxed memory ordering does not remove this coherence cost. It can reduce ordering constraints on the compiler or CPU, but the operation still atomically modifies shared storage.

On AMD64, a relaxed `atomic_fetch_add()` on a lock-free integer commonly uses the same locked instruction as a sequentially consistent one. Weakening the order does not make that instruction cheaper. On ARM64, the memory order can change the instruction used, but contention for the line remains.

A load-only workload behaves differently. Many cores can usually retain shared read-only copies of one cache line. A later writer must invalidate those copies before modifying the line. This is why read-mostly data structures can benefit from designs that avoid modifying shared metadata on every read.

## Atomic does not mean inexpensive

The cost of an atomic operation depends on:

- whether it is a load, store, or read-modify-write;
- its memory order;
- the target architecture and compiler;
- whether the value is already in the local cache;
- how many cores contend for its cache line; and
- whether the implementation is lock-free for that type.

For lock-free scalar atomics, an acquire load or release store commonly uses an ordinary `MOV` on AMD64. A sequentially consistent load commonly does too. A sequentially consistent store typically uses a locked exchange (`XCHG`) or a store followed by a fence.

ARM64 commonly uses `LDAR` for acquire loads and `STLR` for release stores. These instructions also commonly implement sequentially consistent loads and stores. Some newer targets can use the weaker `LDAPR` for acquire-only loads. The extra instruction cost of stronger ordering therefore depends on the operation and target.

These instruction differences do not tell the complete performance story. An uncontended atomic operation can be cheap, while a relaxed operation on a heavily contended line can be expensive.

Do not claim that acquire or release always executes a CPU fence. Do not claim that changing sequential consistency to relaxed ordering will solve contention. Inspect generated code when useful, but measure the complete workload.

## Mutexes have fast and contended paths

A mutex does not necessarily enter the operating-system kernel on every acquisition. A lightweight mutex commonly has:

- a fast path that acquires an uncontended lock with a small atomic operation; and
- a slow path that spins briefly or asks the operating system to block when the lock is contended.

An uncontended mutex can therefore be inexpensive. It can also protect several related fields with one acquisition, while an atomic design might perform several operations on several cache lines.

Contention changes the result. Threads may repeatedly compete for the mutex, sleep and wake through the scheduler, or wait while the owner performs unrelated work. A long critical section limits parallelism even if acquiring the mutex itself is cheap.

The relevant quantity is not only the acquisition cost. Measure how often the mutex is requested, how long it is held, how often threads wait, and how much useful work can proceed independently.

## Atomics and locks can both serialize execution

Replacing a lock with a CAS loop does not necessarily remove serialization. All successful updates to one atomic object still occur in its modification order. Competing threads may repeatedly fail CAS and retry.

A lock can make waiting explicit. An atomic loop can move the waiting into cache-coherence traffic and repeated computation. Under heavy contention, the latter may perform worse while being harder to reason about.

First identify the fields that must change together and which object's lock or separately owned mutex protects them. Make readers and writers follow the same rule. Performance measurements can then show whether this synchronization point is actually a bottleneck.

## Keep mutex-protected regions focused

A mutex limits concurrency only while it is held. Reduce unnecessary hold time, but do not split one invariant-preserving operation merely to shorten the critical section.

Useful changes include:

- compute thread-local inputs before acquiring the mutex;
- move independent work after releasing it;
- avoid blocking input/output while holding it;
- avoid callbacks whose duration and locking behavior are unknown; and
- acquire object references or copy stable data under the lock, then perform safe independent work outside it.

The last step requires a valid lifetime rule. Copying a borrowed pointer and releasing the mutex is not safe if another thread can destroy the object. Acquire a strong reference under the lock when the pointed-to Python object must remain alive after unlocking.

This discussion assumes an ordinary mutex that stays held until explicitly unlocked. [CPython critical sections](11-cpython-critical-sections.md#detachment-suspends-all-active-sections) can temporarily release their locks; chapter 11 explains the additional constraints.

Over-shortening a locked region can introduce check-then-act races, expose partially updated fields, or require repeated acquisitions. Optimize the complete operation, not the line count between lock and unlock.

## Sharding reduces shared writes

The most effective optimization is often to stop modifying one shared location.

A **sharded** counter gives different threads or groups of threads separate counters. The value in each shard might be represented as:

```c
struct counter_shard {
    atomic_uint value;
};
```

This is not a complete storage layout. A tightly packed array of these structures can put several writers' shards on the same cache line. To avoid false sharing between hot shards, arrange their storage on separate cache lines using target-appropriate alignment and spacing. Sharding alone does not solve false sharing. Measure whether the reduced contention justifies the larger layout.

Updates affect only the writer's shard. A reader computes a total by combining the shards. This trades cheap frequent updates for a more expensive read. The sum may combine values from different moments rather than describe one instant.

State who may read and write each shard. If only its owner accesses it, a non-atomic representation and ordinary operations are sufficient. If another thread reads it concurrently, both the owner's writes and the reader's reads must use atomics or the same lock. Making only the reader's load atomic is not enough.

After initialization, if exactly one thread writes a shard, it can increment the atomic value with a relaxed load followed by a relaxed store. Readers can use relaxed loads when they need only the counter value, not publication of other data. On AMD64 this commonly avoids the locked instruction used by an atomic fetch-add. The load and store are still two operations. They are sufficient here only because no other thread can modify the shard between them. A reader that resets the counter would break this single-writer rule.

Sharding also raises lifetime questions. The program must prevent a shard from disappearing while a reader is collecting values.

## Per-thread state can eliminate synchronization

State that belongs to one thread does not need synchronization while no other thread accesses it. Work can accumulate locally and merge into shared state less often.

Examples include:

- per-thread allocation caches;
- local statistics merged periodically;
- thread-local work queues; and
- batching several updates under one shared lock acquisition.

This technique reduces coherence traffic and lock acquisitions. It may increase memory consumption, delay global visibility, and make shutdown or thread removal more complicated.

A pointer to thread-local state does not make the pointed-to state permanently private. Once another thread can access it, the design needs a synchronization and lifetime rule.

## Read-mostly data benefits from immutable snapshots

When reads greatly outnumber writes, a writer can sometimes build a new immutable representation and publish one pointer to it. Readers then traverse stable data without observing a partial update.

Publication still needs ordering, such as a release store paired with acquire loads. More importantly, replacing the pointer does not make the old representation safe to free. Existing readers may still be using it.

A lock can keep readers and replacement mutually exclusive. Lock-free readers require a safe memory-reclamation mechanism. This tradeoff appears later in the discussion of QSBR.

## Memory allocation and layout affect scaling

Synchronization is not the only shared resource. Allocators maintain metadata, memory accesses consume bandwidth, and compact data structures determine which fields share cache lines.

Adding padding may reduce false sharing but enlarge the working set. Sharding may reduce contention but scatter reads across more cache lines. Copying immutable snapshots may improve reader locality but increase allocation and reclamation work.

Measure throughput, latency, memory use, and scaling across realistic thread counts. A benchmark that exercises one operation in isolation can miss interactions with allocation, reference counting, callbacks, and the scheduler.

## Optimize only after identifying the bottleneck

A useful performance investigation asks:

1. Which shared locations are written frequently?
2. Which locks are contended, and how long are they held?
3. Are unrelated writable fields sharing a cache line?
4. Are atomic read-modify-write operations concentrated on one line?
5. Can ownership become per-thread, per-object, or sharded?
6. Can reads use immutable state?
7. What accuracy, freshness, memory, or lifetime costs would the change add?

Prefer structural changes that reduce sharing over weaker memory ordering applied without a proof. Preserve the simple synchronization rule unless measurements show that it matters.

The next section examines lock-free algorithms. They can improve progress in some workloads, but they do not eliminate cache contention, retries, or the need to protect object lifetime.

---

Next: [Lock-free algorithms](07-lock-free-algorithms.md)
