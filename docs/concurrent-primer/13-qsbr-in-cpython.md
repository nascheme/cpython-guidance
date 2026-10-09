# QSBR in CPython

CPython uses quiescent-state based reclamation, or **QSBR**, in the free-threaded build (`Py_GIL_DISABLED` defined). QSBR delays freeing storage or releasing a strong reference until old lock-free readers have finished.

The [safe-memory-reclamation chapter](08-safe-memory-reclamation.md) introduced the general problem. CPython applies it to internal storage and object pointer fields that can be replaced while readers still hold the old pointer.

The central rule is:

> Remove or replace the shared pointer first. Free the old storage, or release its strong reference, only after every relevant thread has passed a quiescent state.

QSBR is an internal runtime mechanism. It is not a general public C API for extension modules.

## QSBR complements reference counting

CPython still uses reference counting and cyclic garbage collection to manage Python objects. QSBR does not replace either mechanism. It can delay either a raw free or the release of one strong reference. A delayed reference release keeps the old object alive until covered readers finish.

QSBR also protects internal allocations whose lifetime can be shorter than the lifetime of their containing object. A list is a clear example. The `PyListObject` can remain alive while a resize replaces its backing array.

A reader may follow this simplified sequence:

```text
load the list's array pointer
load an item from the array
finish using the array pointer
```

At the same time, a writer can enter a critical section on the list, allocate a larger array, and publish the new pointer. The list's object lock serializes writers changing its array pointer, size, and capacity. Unlocked readers need atomic pointer access and validation as well as QSBR. New readers use the new array. An old reader may still be loading from the old array.

The writer has logically removed the old array, but it cannot free it at once. QSBR delays that free until no old reader can still use the array.

CPython uses delayed reclamation for storage such as:

- old list backing arrays;
- old dictionary keys and values storage;
- old set entry tables;
- selected code and cache data; and
- allocator pages that cannot yet be reused for a different purpose.

It also delays decrefs of objects replaced during type attribute updates, `__dict__` assignment, generator name updates, and some dictionary operations. These keep a strong reference for readers that may still hold the old object pointer.

The exact users can change as CPython develops. Each user still needs its own access and ordering proof.

## A quiescent state is a promise from one thread

A thread reaches a **quiescent state** when it no longer holds any pointer to QSBR-protected shared data from earlier work.

This is stronger than being paused between two arbitrary instructions. The thread must not carry an old protected pointer across the report and use it later.

CPython reports quiescent states at evaluation-loop periodic checks. These include checks associated with function entry, backward jumps, and the end of calls. The report runs before the check for pending eval-breaker events. It does not require a pending event. Processing delayed work is a separate step in the eval-breaker handler.

Detachment is also important. A detached thread cannot execute Python code or use APIs that require an attached thread state. CPython marks its QSBR state as offline. An offline thread does not hold the kind of internal pointer covered by this protocol and does not delay reclamation.

Do not rely on QSBR alone to keep a pointer valid across a call that can:

- run Python code, such as rich comparison, attribute lookup, or a `Py_DECREF` that invokes `__del__`;
- block while acquiring a `PyMutex` or a critical-section lock, since waiting can detach the thread state; or
- explicitly detach, as with `Py_BEGIN_ALLOW_THREADS`.

Such a call can report a quiescent state or mark the thread offline. Staying within one C function is not enough. Helpers that process delayed decrefs can also run Python code.

Before such a call, acquire a strong reference to any Python object you need, using the data structure's safe reference-acquisition protocol. Keeping the containing object alive does not keep its old backing storage alive. After the call, reload and validate the container's storage pointer before accessing an entry again. Retry if the storage changed.

For example, `compare_generic_threadsafe()` in dictionary lookup acquires a strong reference to the candidate key before calling `PyObject_RichCompareBool()`. Comparison or the following decref can run Python code. The lookup then reloads `mp->ma_keys`. It accesses the cached entry only if that pointer still matches the saved keys pointer. Otherwise it restarts the lookup.

These are contracts, not automatic checks. Code breaks QSBR if it retains or passes an unprotected pointer to another thread and later dereferences it after a quiescent report.

## CPython tracks one write sequence per interpreter

CPython's implementation uses sequence numbers. The main values are:

- `wr_seq`: the interpreter's current write sequence;
- one `seq` value for each participating thread state; and
- `rd_seq`: the minimum sequence reported by attached threads.

Valid write sequence values are odd. The sequence starts at 1 and advances by 2. A per-thread sequence of 0 means that the thread is offline, normally because its thread state is detached.

When a thread reports a quiescent state, it copies the current `wr_seq` into its own sequence field. The report means:

> This thread no longer uses protected pointers that were retired before this sequence.

A polling operation scans the per-thread values. It ignores offline threads and finds the oldest sequence still reported by an attached thread. It then advances `rd_seq` when possible.

A retired allocation has a **goal** sequence. The allocation is safe to reclaim when its goal is no later than `rd_seq`.

## Retirement follows a fixed sequence

At a conceptual level, a writer does this:

1. Lock or otherwise serialize the update.
2. Publish the replacement pointer, removing the old pointer from the shared structure.
3. Assign the retired storage or reference a future QSBR goal.
4. Put it on a delayed-work list.
5. Unlock and continue without waiting for all readers.

Later, polling does this:

1. Scan the QSBR sequence of each participating thread state.
2. Find how far every attached thread has progressed.
3. Compare each retired item's goal with that progress.
4. Free storage or release references whose goals have been reached.
5. Keep the remaining items for a later poll.

The writer normally does not wait for a grace period. Logical updates can continue while old memory waits on the deferred list. This gives readers a cheap path, but it can temporarily use more memory.

## Delayed frees and decrefs connect lifetime to QSBR

Internal code commonly retires an allocation with `_PyMem_FreeDelayed(ptr, size)` instead of freeing it directly. The work item records the pointer and a QSBR goal. The size feeds the sequence-advance heuristic, but is not stored in the item.

For Python objects, `_PyObject_XDecRefDelayed(obj)` queues the release of an existing strong reference on the same work list. It does not acquire another reference. Once the goal is reached, normal processing through `_PyMem_ProcessDelayed()` runs `Py_DECREF`, which can invoke destructors and Python code. Callers that trigger processing must therefore allow reentrancy. The next section explains when processing runs and how stop-the-world processing defers deallocation.

`_PyObject_XSetRefDelayed(&field, new_value)` combines replacement with delayed release. In the free-threaded build, it publishes the new pointer with a release store and queues a decref of the old non-immortal value. Like `Py_XSETREF`, it takes ownership of the new reference. It does not serialize competing writers.

For example, a generator name setter enters a critical section on the generator. The generator's object lock serializes updates to `gi_name` and `gi_qualname`. The setter passes a new strong reference to `_PyObject_XSetRefDelayed`.

An unlocked getter uses an acquire load and acquires its own strong reference before any quiescent point. The delayed decref keeps the old name alive during that interval.

Using these helpers only on the writer is not enough. The reader must obey the QSBR pointer-access and quiescent-state rules. Every removal path must follow the same lifetime rule. Another path must not call ordinary `PyMem_Free()` or drop the last strong reference while a covered reader can still use the pointer.

In the default GIL-enabled build (`Py_GIL_DISABLED` not defined), `_PyMem_FreeDelayed` frees immediately and `_PyObject_XDecRefDelayed` performs `Py_XDECREF` immediately. `_PyObject_XSetRefDelayed` uses `Py_XSETREF`. These are compile-time distinctions, not the runtime GIL state of a free-threaded build with the GIL re-enabled.

In the free-threaded build, delayed frees and decrefs are immediate during interpreter finalization. Raw frees are also immediate while the world is stopped. If a work chunk cannot be allocated, the runtime stops the world to free storage or merge the queued reference decrement safely. Any resulting object deallocation runs after threads resume.

Objects or storage known to be private do not need a grace period. For example, CPython can free some list or dictionary storage immediately while the containing object is not shared. The implementation must have reliable proof of that private status.

## Sequence advancement can be deferred

Advancing the shared write sequence for every small free would make many threads write one contended cache line. CPython can instead assign work the next possible sequence as its goal without advancing `wr_seq` immediately.

The runtime advances the sequence after enough items or bytes have accumulated. A large retired allocation can also cause an earlier advance. This batches shared sequence updates.

Crossing a threshold sets a per-thread `should_process` flag. It does not set an eval-breaker event bit. The eval-breaker handler processes delayed work when it runs for another pending event. A future goal may therefore wait for both a later sequence advance and an opportunity to process the queue.

Processing also runs when a work chunk fills. At thread exit, remaining work is transferred to the interpreter's queue and eligible items are processed.

During free-threaded garbage collection, a stop-the-world pass advances the sequence, reports the collector's quiescent state, and merges the threads' delayed-work queues. Other threads are offline, so this pass can drain pending work. It merges delayed decrefs without running arbitrary destructors during the pause.

This batching changes when memory is returned. It does not change the safety rule. Raw storage is not freed, and a queued strong reference is not released, until covered readers can no longer use it.

## Attached and detached states affect grace periods

Each Python thread state is registered with the interpreter's QSBR state. Attachment marks its QSBR entry online at the current sequence. Detachment marks it offline with sequence 0.

These transitions implement the pointer-use contract described above: offline threads are excluded from the minimum, and returning threads become current before covered accesses resume.

Thread-state destruction must unregister the QSBR entry. CPython also repairs the registration state after `fork()`, because only the calling thread survives in the child process.

These lifecycle steps are part of correctness. A stale online entry could retain memory forever. Removing a live entry too early could permit a use-after-free.

## A delayed thread can retain much memory

QSBR depends on all attached threads reporting quiescent states. If one thread remains attached in a long-running operation and does not report, `rd_seq` cannot pass its old sequence.

The runtime stays safe by keeping the retired allocations. It does not free them after a timeout. Memory use can therefore grow while a thread delays a grace period.

This is the main progress tradeoff of QSBR:

- readers do little or no QSBR-specific work on each protected load;
- writers can publish replacements without waiting; but
- delayed reclamation depends on timely quiescent reports.

Polling also scans the whole per-thread QSBR array, including unused entries. The array grows but does not shrink during normal operation. The cost therefore follows the peak number of simultaneously registered thread states, not just the current number. CPython pads these entries to separate cache lines and reduce false sharing, but very large thread counts can still make scanning expensive.

## Allocator reuse is part of the lifetime problem

Freeing an old object is not the only danger. Reusing the same address for a different kind of allocation can also confuse an old reader.

CPython's free-threaded allocator uses QSBR for selected mimalloc pages. A page that became empty may still contain an address an old reader could inspect. The allocator delays reusing that page for another size class or another thread until the QSBR goal has been reached.

Individual blocks can still be reused immediately within the same size class and heap. An old address may therefore hold a different object. Page retention preserves the layout needed for specialized reference-count access, not the old object's identity or arbitrary fields. Initialization and copying of those header fields must also be thread-safe.

Optimistic reference acquisition needs validation as well as that layout guarantee. The shared-reference path of `_Py_TryIncrefCompare()` reloads the source pointer after acquiring a reference. If the slot no longer names the candidate, it releases the reference and reports failure. `_Py_XGetRef` retries this protocol, while `_Py_TryXGetRef` can report failure. Writers must set the stored object's maybe-weakref state as required by the protocol, and the allocator must preserve a usable reference-count layout during speculative access.

This is a specialized internal protocol, not permission to call ordinary `Py_INCREF` on an arbitrary stale pointer.

Page retention applies to the object and GC heaps. It does not protect `PyMem_Malloc` storage such as list arrays and dictionary keys. Those need their own delayed frees. Safe reclamation therefore includes rules about reuse, not only calls to `free()`.

## QSBR does not provide publication ordering by itself

A grace period answers one question: can an old address still be used by a covered reader?

The data structure must answer other questions separately:

- Is loading the shared pointer race-free?
- Does a reader see fully initialized replacement storage?
- Can a writer modify fields that a reader accesses?
- Which lock serializes competing writers?
- What keeps the Python objects stored in the allocation alive?

For example, publishing a replacement pointer may require an atomic release store and an acquire load. Writers may need an object lock. Reading a Python object pointer may need an operation that safely obtains a strong reference.

QSBR does not turn ordinary conflicting reads and writes into valid C. It does not make several fields one atomic snapshot. It only delays reclamation for readers that obey its protocol.

## QSBR is useful for read-mostly internal storage

QSBR is a good fit when:

- unlocked reads are frequent and must stay cheap;
- replacement or resizing is less frequent;
- reader use of internal pointers is short;
- the evaluation loop provides regular quiescent points;
- temporary memory retention is acceptable; and
- every access path can follow the internal protocol.

Prefer a critical section for per-object state or a `PyMutex` for independently owned shared state when readers can take the lock cheaply. Readers must acquire separate lifetime protection before carrying a pointer beyond the lock's protected interval. For a normal Python object, a safely acquired strong reference is usually the right way to retain it for an unbounded time.

For a QSBR user inside CPython, the lifetime argument needs to identify:

1. The exact allocation or strong reference being retired.
2. Where readers finish using its pointer and why no unprotected pointer survives a quiescent state. This includes calls that run Python code or detach the thread.
3. How every removal, reclamation, and reuse path follows the applicable lifetime rule. Retired raw storage needs delayed reclamation; specialized allocator page retention restricts page reuse, not every block reuse.
4. Which references keep objects contained in the storage alive.

QSBR is not a general sign that code is thread-safe. It is one part of a complete lock-free read protocol.

The [final chapter](14-choosing-a-technique.md) brings these mechanisms together into a practical decision guide.

For implementation details, see CPython's [QSBR design notes](https://github.com/python/cpython/blob/main/InternalDocs/qsbr.md), [sequence tracking](https://github.com/python/cpython/blob/main/Python/qsbr.c), [delayed-work and allocator implementation](https://github.com/python/cpython/blob/main/Objects/obmalloc.c), and [reference-acquisition helpers](https://github.com/python/cpython/blob/main/Include/internal/pycore_object.h).

---

Next: [Choosing a technique](14-choosing-a-technique.md)
