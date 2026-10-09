# Glossary

Terms used in concurrent C programming and free-threaded CPython. Synonyms and
related API names are grouped together; links point to explanations in the
primer. General computing vocabulary and routine C API names are omitted.
Internal CPython mechanisms described here are not general public extension APIs.

## A

### ABA problem

A value changes from A to B and back to A, hiding the intervening changes from
value-only comparison. Address reuse and counter wraparound can cause ABA.
See [ABA and generation counters](07-lock-free-algorithms.md#aba-defeats-value-only-validation).

### Acquire ordering

Ordering that constrains accesses after an acquire operation. An acquire that
reads from a release or its release sequence can synchronize with that release,
ordering the releasing thread's earlier accesses before the acquiring thread's
later accesses. An **acquire load** uses `memory_order_acquire`; successful mutex
acquisition also supplies acquire ordering.
See [acquire](04-atomic-operations.md#acquire-observes-published-work) and
[synchronizes-with](03-the-c-memory-model.md#synchronizes-with-connects-threads).

### Acquire-release ordering

Ordering for an atomic read-modify-write operation that combines acquire and
release effects. In C, it is selected with `memory_order_acq_rel`.
See [acquire-release](04-atomic-operations.md#acquire-release-combines-both-directions).

### Address reuse

Allocating a new object at an address previously occupied by another object.
The address does not preserve the old object's identity or lifetime.
See [ABA](07-lock-free-algorithms.md#aba-defeats-value-only-validation) and
[allocator reuse](13-qsbr-in-cpython.md#allocator-reuse-is-part-of-the-lifetime-problem).

### Allocator page retention

CPython's use of QSBR to delay reuse of selected empty mimalloc pages for another
size class or thread. Blocks can still be reused within the same size class and
heap; retention preserves a required layout, not object identity.
See [allocator reuse](13-qsbr-in-cpython.md#allocator-reuse-is-part-of-the-lifetime-problem).

### As-if rule

The compiler's freedom to transform a C program while preserving the observable
behavior required by the language. Source operations need not become identical
machine operations.
See [compiler transformations](02-the-c-abstract-machine-and-undefined-behavior.md#the-compiler-does-not-execute-the-source-literally).

### Attached thread state

A `PyThreadState` attached to its executing native thread, permitting Python
execution and most C API calls. Attachment requires the GIL when enabled; with
it disabled, attachment does not imply exclusive execution.
See [thread-state contracts](09-cpython-concurrency-model.md#attached-detached-and-suspended-are-distinct-states).

### Atomic coherence

C memory-model constraints on how operations observe one atomic object's
modification order. These constraints do not create a global order for all memory.
See [modification order](03-the-c-memory-model.md#each-atomic-object-has-a-modification-order)
and [versioned snapshot proof](07-lock-free-algorithms.md#advanced-example-optimistic-reads-need-a-precise-protocol).

### Atomic exchange

An atomic read-modify-write operation that replaces a value and returns the old
value.
See [exchange](04-atomic-operations.md#exchange-replaces-a-value).

### Atomic fence

An ordering operation that does not itself load or store the communicated value.
Synchronization through fences still requires suitable atomic accesses. A C
fence need not correspond to a separate **CPU fence** instruction.
See [fences](04-atomic-operations.md#fences-order-without-carrying-the-value-operation).

### Atomic load

An indivisible read of an atomic object's value. It does not guarantee the latest
stored value or that the observed value remains current.
See [loads and stores](04-atomic-operations.md#loads-and-stores-transfer-individual-values).

### Atomic object

An object accessed using atomic operations. C11 atomic types, such as
`atomic_int` and `atomic_uint`, provide atomic semantics even for ordinary-looking
expressions; CPython's atomic helpers instead operate on ordinary C fields that
must consistently follow their access protocol.
See [atomic access requirements](04-atomic-operations.md#atomic-objects-require-atomic-access).

### Atomic operation / atomicity

An operation that is indivisible under the applicable memory-model rules.
Atomicity does not itself order accesses to other objects, combine several
operations into one transaction, guarantee lock-free progress, or protect lifetime.
See [atomicity versus ordering](03-the-c-memory-model.md#atomicity-and-ordering-are-different-guarantees).

### Atomic pointer

A pointer whose value is accessed atomically. Atomic pointer access does not
protect the pointed-to object's contents or lifetime.
See [pointer versus target](08-safe-memory-reclamation.md#an-atomic-pointer-does-not-protect-its-target).

### Atomic read-modify-write (RMW)

One indivisible operation that reads a value and writes an updated value.
Exchange, successful compare-exchange, and **fetch-add / fetch-subtract** are
examples. A separate atomic load and store are not one RMW.
See [read-modify-write](04-atomic-operations.md#read-modify-write-is-one-indivisible-operation).

### Atomic store

An indivisible write to an atomic object. The write participates in that object's
modification order.
See [loads and stores](04-atomic-operations.md#loads-and-stores-transfer-individual-values).

## B

### Backoff

Delaying retries to reduce contention. **Exponential backoff** increases the delay
after repeated failures; **bounded spinning** limits active retries before
changing strategy. Neither establishes a progress guarantee by itself.
See [CAS contention](07-lock-free-algorithms.md#cas-can-fail-repeatedly-under-contention).

### Batching

Combining updates to reduce shared lock acquisitions or shared atomic writes.
It can reduce contention while delaying visibility or reclamation.
See [sharding and batching](06-concurrency-and-performance.md#sharding-reduces-shared-writes)
and [QSBR sequence batching](13-qsbr-in-cpython.md#sequence-advancement-can-be-deferred).

### Biased reference counting

An internal free-threaded CPython mechanism that accounts separately for
references handled by an object's owning thread and other threads. The owner
can often update its local count without atomic read-modify-write operations.
See [concurrency-aware reference counting](09-cpython-concurrency-model.md#reference-counting-is-concurrency-aware).

### Blocking

Waiting for a resource or event instead of continuing execution. A blocking
operation may depend on another thread making progress; CPython mutex waits can
also detach the thread state and suspend active critical sections.
See [mutex waiting](10-pymutex.md#waiting-temporarily-detaches-the-thread-state)
and [progress guarantees](07-lock-free-algorithms.md#lock-free-describes-system-wide-progress).

### Borrowed reference / borrowed pointer

A reference or pointer that does not itself keep its target alive. A Python
borrowed reference gives the caller no owned reference to release. Safe use
requires a race-free lookup and separate lifetime protection throughout use.
See [borrowed references](09-cpython-concurrency-model.md#borrowed-references-need-renewed-scrutiny).

## C

### C abstract machine

The execution model defined by the C standard. Correct concurrent C code must
satisfy this model, not merely behave as expected on one processor.
See [the compiler and the abstract machine](02-the-c-abstract-machine-and-undefined-behavior.md#the-compiler-does-not-execute-the-source-literally).

### C memory model

The C language rules governing memory accesses, atomicity, ordering between
threads, and data races. Compilers and hardware implementations must implement
these guarantees for valid programs.
See [the C memory model](03-the-c-memory-model.md).

### C11 atomics

The atomic types, operations, and memory-order constants provided through
`<stdatomic.h>`, used in the primer's C11/C17 examples. CPython interpreter code
uses its internal atomic helper layer instead.
See [atomic APIs](04-atomic-operations.md#use-cpythons-atomic-api-in-interpreter-code).

### Cache coherence

Hardware coordination that keeps cached copies of memory consistent across
cores. It does not replace C synchronization or impose one order on accesses to
different memory locations.
See [cache coherence](06-concurrency-and-performance.md#cpu-cores-communicate-through-a-cache-coherence-system).

### Cache line

The unit of memory transferred and tracked by processor caches for coherence.
Independent fields on the same line can interfere when threads write them.
See [cache-line granularity](06-concurrency-and-performance.md#coherence-works-at-cache-line-granularity).

### Cache-line bouncing

Repeated movement of writable cache-line ownership between cores. The resulting
**cache-coherence traffic** can limit scaling even for relaxed atomic operations.
See [contended writes](06-concurrency-and-performance.md#contended-writes-move-cache-line-ownership).

### Caller-held lock / locked-helper convention

A function contract requiring the caller to hold the lock protecting its state.
The helper does not acquire that lock again. The contract must also account for
calls that could suspend a CPython critical section.
See [locking ownership](05-synchronization.md#locking-has-ownership-rules) and
[nonrecursive PyMutex](10-pymutex.md#pymutex-is-not-recursive).

### CAS loop

A retry loop that reads a value, computes an update, and attempts compare-exchange.
It must handle interference, retry cleanup, and possibly spurious failure.
See [CAS updates](07-lock-free-algorithms.md#cas-commits-a-conditional-change).

### Check-then-act race

A race condition in which another operation changes state between checking a
condition and acting on it. Individually synchronized accesses do not protect
the combined operation.
See [race conditions](01-shared-mutable-memory.md#data-races-and-race-conditions-are-different).

### Compare-exchange / compare-and-swap (CAS)

An atomic conditional update that stores a desired value only if the current
value equals an expected value. C's compare-exchange interface updates the
expected value on failure. **Weak compare-exchange** may fail spuriously;
**strong compare-exchange** does not.
See [compare-exchange](04-atomic-operations.md#compare-exchange-updates-conditionally).

### Compound operation / logical operation

Related checks and updates that implement one logical action. Synchronization
must cover the complete action when interference between its steps would be
incorrect.
See [shared-state invariants](01-shared-mutable-memory.md#shared-state-is-often-larger-than-one-variable)
and [compound container operations](09-cpython-concurrency-model.md#container-safety-does-not-make-compound-operations-atomic).

### Concurrency

Execution in which operations overlap, even if threads do not execute at the
same instant. **Parallelism** means execution at the same time.
See [shared mutable memory](01-shared-mutable-memory.md#a-simple-shared-variable).

### Condition variable

A synchronization primitive for waiting until protected state changes. Waiting
atomically releases the associated mutex and reacquires it before returning.
The waiter must recheck its predicate in a loop because wakeups do not guarantee
that the condition holds.
See [condition variables](05-synchronization.md#condition-variables-wait-for-state-changes).

### Conflicting accesses

Accesses to the same C memory location where at least one access is a write.
Across threads, conflicting accesses need atomic access or happens-before
ordering to avoid a data race.
See [data races and memory locations](02-the-c-abstract-machine-and-undefined-behavior.md#an-ordinary-c-data-race-is-undefined-behavior).

### Consume ordering

The dependency-based atomic ordering specified by `memory_order_consume` in
C11/C17. It is excluded from the primer's simplified happens-before explanation;
the publication examples use acquire ordering instead.
See [the primer's ordering model](03-the-c-memory-model.md#happens-before-combines-the-ordering).

### Contention

Competition between threads for a lock or shared resource, including a writable
cache line. It can cause waiting, retries, and serialization.
See [contended writes](06-concurrency-and-performance.md#contended-writes-move-cache-line-ownership)
and [mutex paths](06-concurrency-and-performance.md#mutexes-have-fast-and-contended-paths).

### Continuous lock ownership

Holding a lock without releasing it throughout an operation. Direct mutex
locking provides this until explicit unlock; CPython critical sections may
release their locks during suspension.
See [direct mutex versus critical section](11-cpython-critical-sections.md#choose-between-a-direct-mutex-and-a-critical-section).

### CPython critical section

A suspendable locking scope managed by CPython over one or two object locks or
explicit mutexes. It protects state while its locks are held, but detachment can
release them temporarily. These APIs lock in a free-threaded build, even with
the GIL re-enabled, and are no-ops in the default build.
See [critical-section semantics](11-cpython-critical-sections.md) and
[build contract](11-cpython-critical-sections.md#critical-sections-are-no-ops-in-the-default-build).

### Critical section

Conventionally, a region of code protected by exclusive locking from entry to
exit. A CPython critical section differs because it can be suspended.
See [CPython's distinction](11-cpython-critical-sections.md) and
[mutex protection](05-synchronization.md#a-mutex-provides-mutual-exclusion-and-ordering).

### Critical-section stack

Per-thread bookkeeping in `PyThreadState` tracking active and suspended CPython
critical sections. It allows the runtime to release and resume their locks;
lexical nesting does not guarantee all enclosing locks remain held.
See [the per-thread stack](11-cpython-critical-sections.md#each-thread-has-a-stack-of-critical-sections).

### Cyclic garbage collection

Collection of unreachable objects whose references form cycles. Free-threaded
CPython uses stop-the-world coordination for parts of this work; reference
counting and QSBR serve different purposes.
See [reference counting and GC](09-cpython-concurrency-model.md#reference-counting-is-concurrency-aware)
and [GC does not prove a pause](12-stop-the-world.md#garbage-collection-state-is-not-proof-of-a-pause).

## D

### Data race

Conflicting accesses by different threads, with at least one non-atomic access,
that are not ordered by happens-before. A C data race causes undefined behavior,
not merely an unexpected or stale value. It differs from a logical race condition.
See [data race versus race condition](01-shared-mutable-memory.md#data-races-and-race-conditions-are-different)
and [C undefined behavior](02-the-c-abstract-machine-and-undefined-behavior.md#an-ordinary-c-data-race-is-undefined-behavior).

### Deadlock

A situation in which execution cannot proceed because required resources or
progress cannot become available, often due to a cycle of waits. Reacquiring a
nonrecursive mutex in its owning thread can also deadlock.
See [lock ordering](05-synchronization.md#multiple-mutexes-require-a-lock-order)
and [stop-the-world lock hazards](12-stop-the-world.md#do-not-wait-for-locks-while-threads-are-suspended).

### Deferred reference counting

An internal CPython mechanism that accounts for selected references later rather
than updating reference counts on every interpreter-stack operation. It is
not the same as queuing a delayed decref for QSBR.
See [reference-counting mechanisms](09-cpython-concurrency-model.md#reference-counting-is-concurrency-aware).

### Delayed decref

A queued release of an existing strong reference after covered readers are safe.
It does not acquire a new reference. Processing the release can run deallocation
code and must occur in an appropriate execution context.
See [delayed frees and decrefs](13-qsbr-in-cpython.md#delayed-frees-and-decrefs-connect-lifetime-to-qsbr).

### Delayed-work list

CPython's internal queue of retired allocations and owned references awaiting
QSBR goals. Processing eligible work is separate from reporting a quiescent state.
See [retirement sequence](13-qsbr-in-cpython.md#retirement-follows-a-fixed-sequence)
and [delayed-work processing](13-qsbr-in-cpython.md#sequence-advancement-can-be-deferred).

### Detached thread state / detachment

A detached `PyThreadState` does not permit Python execution or most C API calls.
Detachment releases the GIL if held, suspends active CPython critical sections,
and marks the thread's QSBR entry offline. The native thread can still run and
access independently synchronized C state.
See [thread-state contracts](09-cpython-concurrency-model.md#attached-detached-and-suspended-are-distinct-states),
[critical-section detachment](11-cpython-critical-sections.md#detachment-suspends-all-active-sections),
and [QSBR transitions](13-qsbr-in-cpython.md#attached-and-detached-states-affect-grace-periods).

### Direct field access

Reading or writing a C structure field without the synchronization and lifetime
handling supplied by an API function. Some accessor macros also do this and may
be unsafe during concurrent mutation.
See [API synchronization bypass](09-cpython-concurrency-model.md#direct-field-access-bypasses-api-synchronization).

### Direct mutex locking

Explicit acquisition and release, such as `PyMutex_Lock()` and `PyMutex_Unlock()`,
without CPython critical-section management. A directly held lock is not released
by critical-section suspension.
See [choosing direct locking](10-pymutex.md#choose-direct-locking-when-the-lock-must-stay-held).

### Double-width CAS

Compare-exchange that atomically compares and updates a double-width value, such
as a pointer and generation counter together. Platform support and lock-free
behavior vary; CPython's atomic helper family does not provide this operation.
See [ABA defenses](07-lock-free-algorithms.md#aba-defeats-value-only-validation).

## E–F

### Epoch-based reclamation

A lifetime protocol in which readers announce participation in generations
called epochs. Retired objects wait until every reader that could still use
them has left its region or advanced sufficiently.
See [epoch-based reclamation](08-safe-memory-reclamation.md#epoch-based-reclamation-groups-readers).

### Eval-breaker

CPython's mechanism for handling pending runtime events at evaluation-loop
checks. Its handler also processes delayed work, but quiescent-state reporting
does not require a pending event.
See [quiescent reports](13-qsbr-in-cpython.md#a-quiescent-state-is-a-promise-from-one-thread)
and [delayed processing](13-qsbr-in-cpython.md#sequence-advancement-can-be-deferred).

### Event

A notification primitive that commonly retains a Boolean state until explicitly
cleared. Unlike a condition-variable notification, it can record a notification
before a waiter arrives. Ordering guarantees depend on the implementation.
See [events](05-synchronization.md#events-represent-persistent-notification-state).

### Fairness

A guarantee about competing threads' opportunities to proceed, such as bounded
waiting or arrival-order service. Mutual exclusion and lock-free progress do not
by themselves guarantee fairness.
See [fairness and starvation](05-synchronization.md#synchronization-does-not-imply-fairness).

### False sharing

Performance interference between threads accessing distinct data on one cache
line when at least one writes. The data need not be logically shared or have a
data race. **Padding** can separate fields onto different lines at a memory cost.
See [cache-line granularity](06-concurrency-and-performance.md#coherence-works-at-cache-line-granularity).

### Fast path / parked path

A mutex's short uncontended acquisition path versus a contended path that may
spin and put the thread to sleep. `PyMutex` detaches an attached thread state
when parking, not on an uncontended fast-path acquisition.
See [PyMutex implementation paths](10-pymutex.md#the-implementation-has-fast-and-parked-paths).

### Finalizer / destructor

Code run during object cleanup, potentially acquiring locks, invoking Python,
or reentering related code. Reaching a grace period does not by itself provide a
safe context to execute this code.
See [reclamation versus destruction](08-safe-memory-reclamation.md#reclamation-and-destruction-are-different-concerns)
and [callbacks during a pause](12-stop-the-world.md#do-not-run-arbitrary-python-code-while-stopped).

### Free-threaded build

A CPython build configured with `Py_GIL_DISABLED` that supports execution without
the GIL. The GIL can still be enabled at runtime; this does not change compiled
object layouts, critical-section behavior, or build-selected atomic wrappers.
See [build versus runtime GIL](09-cpython-concurrency-model.md#the-free-threaded-build-can-run-with-the-gil-enabled).

## G–H

### GC state

CPython's bookkeeping for cyclic garbage collection, which can change even for
an immutable Python object. The `gc.collecting` flag means collection is in
progress, not that threads are stopped; `world_stopped` describes a completed
pause in a particular scope.
See [mutable object bookkeeping](01-shared-mutable-memory.md) and
[GC versus pause state](12-stop-the-world.md#garbage-collection-state-is-not-proof-of-a-pause).

### Generation counter / version counter

A change marker used to distinguish occurrences of a value or validate a
snapshot. The counter and described state must follow one update protocol;
wraparound must not make an old observation appear current.
See [ABA counters](07-lock-free-algorithms.md#aba-defeats-value-only-validation),
[versioned reads](07-lock-free-algorithms.md#advanced-example-optimistic-reads-need-a-precise-protocol),
and [invariants before suspension](11-cpython-critical-sections.md#restore-invariants-before-any-possible-suspension).

### GIL (global interpreter lock)

The lock that serializes attached Python execution when enabled. It protects
only accesses following its rules, not arbitrary detached or native-thread
accesses. Multiple attached threads can execute with it disabled.
See [traditional GIL behavior](09-cpython-concurrency-model.md#the-gil-serializes-attached-threads-in-the-traditional-build)
and [replacing GIL assumptions](09-cpython-concurrency-model.md#the-gils-old-assumptions-must-be-replaced-individually).

### GIL-enabled build / default build

CPython's conventional build without `Py_GIL_DISABLED`, in which attachment
requires the interpreter's GIL. It differs from a free-threaded build whose GIL
has merely been re-enabled at runtime.
See [build distinctions](09-cpython-concurrency-model.md#the-free-threaded-build-can-run-with-the-gil-enabled)
and [critical-section build contract](11-cpython-critical-sections.md#critical-sections-are-no-ops-in-the-default-build).

### Global exclusion

Preventing competing accesses across a defined interpreter or runtime scope.
A stop-the-world pause excludes affected accesses requiring attachment, not all
native-thread accesses in the process.
See [pause exclusion scope](12-stop-the-world.md#a-pause-provides-a-global-exclusion-point).

### Goal sequence

The QSBR progress marker assigned to a retired allocation or reference.
CPython can reclaim it once the minimum relevant reader sequence reaches the goal.
See [QSBR sequence tracking](13-qsbr-in-cpython.md#cpython-tracks-one-write-sequence-per-interpreter).

### Grace period

The interval after removal until every covered reader that could have observed
the old object has passed a point where it can no longer use it. Its completion
rule depends on the reclamation protocol, not elapsed time alone.
See [grace periods](08-safe-memory-reclamation.md#grace-periods-separate-removal-from-reclamation).

### Happens-before

The C memory-model relation used to order conflicting accesses. In this primer's
model, which excludes dependency-based consume ordering, it is the transitive
combination of sequenced-before and synchronizes-with. It is not wall-clock order.
See [happens-before](03-the-c-memory-model.md#happens-before-combines-the-ordering).

### Hardware atomicity

Indivisibility of a hardware access, such as an aligned load or store supported
by a processor. It does not make an ordinary C access atomic in the language model.
See [hardware versus C atomicity](02-the-c-abstract-machine-and-undefined-behavior.md#hardware-atomicity-is-not-c-atomicity).

### Hardware memory model

An architecture's rules for ordering and observing memory accesses. Compilers
must select instructions implementing C's guarantees on that architecture;
hardware ordering cannot legalize a C data race.
See [compiler and hardware layers](03-the-c-memory-model.md#compiler-and-cpu-ordering-are-different-layers)
and [architecture differences](03-the-c-memory-model.md#amd64-and-arm64-provide-different-hardware-ordering).

### Hash cache

Lazily filled runtime storage of an object's computed hash. It illustrates how
an immutable Python value can still have mutable C bookkeeping requiring atomic
access or other synchronization.
See [shared mutable memory](01-shared-mutable-memory.md).

### Hazard pointer

A shared slot where a reader publishes the particular object it intends to
access. Publication, validation, and reclaimer scanning must follow a protocol
that prevents freeing the object during protected use.
See [hazard pointers](08-safe-memory-reclamation.md#hazard-pointers-protect-named-objects).

### Helping protocol

A protocol allowing other threads to complete an operation described by shared
metadata. Ownership, ordering, and failed-attempt cleanup must be explicit.
See [multi-field commit mechanisms](07-lock-free-algorithms.md#multi-field-state-needs-one-commit-mechanism).

## I–L

### Immortal object

A Python object whose lifetime does not depend on ordinary reference-count
updates. Immortality avoids those updates; it does not make mutable contents
safe to access concurrently.
See [reference-counting mechanisms](09-cpython-concurrency-model.md#reference-counting-is-concurrency-aware).

### Immutable state / immutable snapshot

State that does not change after safe publication. An immutable snapshot or
**immutable descriptor** can represent related fields together, but readers
still need ordering and lifetime protection. A Python value's immutability does
not imply that every byte of its C representation is immutable.
See [snapshots](06-concurrency-and-performance.md#read-mostly-data-benefits-from-immutable-snapshots)
and [multi-field state](07-lock-free-algorithms.md#multi-field-state-needs-one-commit-mechanism).

### Interpreter finalization

Shutdown of an interpreter and its runtime state. Attachment and delayed
reclamation have special finalization behavior; a thread must not assume it can
reattach normally once shutdown begins.
See [attachment lifecycle](09-cpython-concurrency-model.md#attached-detached-and-suspended-are-distinct-states)
and [finalization reclamation](13-qsbr-in-cpython.md#delayed-frees-and-decrefs-connect-lifetime-to-qsbr).

### Interpreter-wide pause

A stop-the-world pause coordinating thread states belonging to one interpreter,
not every native thread in the process.
See [pause scopes](12-stop-the-world.md#a-pause-can-cover-one-interpreter-or-the-runtime).

### Invariant

A condition or relationship that shared state must satisfy whenever competing
operations can observe it. Synchronization must protect the complete update,
and CPython critical sections must restore invariants before possible suspension.
See [protecting invariants](05-synchronization.md#protect-invariants-not-individual-accesses)
and [suspension boundaries](11-cpython-critical-sections.md#restore-invariants-before-any-possible-suspension).

### Linearizability

The guarantee that each completed operation appears to take effect at one instant
between its call and return. The resulting order respects the real-time order
of non-overlapping operations.
See [linearization](07-lock-free-algorithms.md#the-linearization-point-defines-when-an-operation-takes-effect).

### Linearization point

The conceptual instant when a concurrent operation takes effect. A successful
CAS is often that point; identifying it does not alone prove ordering or lifetime
safety.
See [linearization points](07-lock-free-algorithms.md#the-linearization-point-defines-when-an-operation-takes-effect).

### Lock-free

A system-wide progress guarantee: some operation completes after finitely many
steps while threads continue taking steps under the algorithm's assumptions.
An individual operation may starve. Avoiding an explicit mutex is not sufficient,
and atomic implementations can themselves use internal locks; C's
`atomic_is_lock_free()` checks the latter property for an atomic object.
See [progress guarantees](07-lock-free-algorithms.md#lock-free-describes-system-wide-progress).

### Lock order

A consistent rule for acquiring multiple locks to avoid circular waits. Every
competing path, including callbacks, must follow compatible rules.
See [multiple mutexes](05-synchronization.md#multiple-mutexes-require-a-lock-order)
and [PyMutex lock order](10-pymutex.md#define-a-lock-order-for-multiple-mutexes).

### Logical removal / retirement

Making an object or allocation unreachable to new operations while existing
readers may still use it. A **retired allocation** or **retired-list** entry awaits
safe physical reclamation.
See [removal versus reclamation](07-lock-free-algorithms.md#removal-and-reclamation-are-separate-operations)
and [CPython retirement](13-qsbr-in-cpython.md#retirement-follows-a-fixed-sequence).

## M–O

### Memory location

In C, a scalar object or a maximal sequence of adjacent non-zero-width bit-fields.
Adjacent bit-fields can therefore share one location; a zero-width bit-field
separates such sequences. Data-race rules apply to memory locations, not arbitrary
source-level field names.
See [memory locations](02-the-c-abstract-machine-and-undefined-behavior.md#an-ordinary-c-data-race-is-undefined-behavior).

### Memory ordering / memory order

Constraints on how memory accesses are ordered and observed. An atomic operation's
memory order determines its guarantees for other accesses; atomicity and ordering
are separate properties.
See [atomicity and ordering](03-the-c-memory-model.md#atomicity-and-ordering-are-different-guarantees)
and [memory-order choices](04-atomic-operations.md#relaxed-ordering-provides-atomicity-only).

### Memory retention

Keeping retired objects or storage allocated because reclamation is not yet safe.
A stalled reader can increase retention without preventing logical updates.
See [stalled readers](08-safe-memory-reclamation.md#stalled-threads-trade-safety-for-memory-retention)
and [CPython QSBR retention](13-qsbr-in-cpython.md#a-delayed-thread-can-retain-much-memory).

### Modification order

The total order of all modifications to one atomic object. It does not by itself
order changes to different objects or provide a multi-field snapshot.
See [modification order](03-the-c-memory-model.md#each-atomic-object-has-a-modification-order).

### Module state / per-interpreter state

Extension data associated with one module or interpreter. Separating state by
interpreter does not make it private to a thread; threads attached to that
interpreter can still access it concurrently.
See [shared extension state](09-cpython-concurrency-model.md#extension-state-may-now-be-genuinely-shared).

### Mutual exclusion

Preventing competing operations from accessing protected state at the same time.
A lock supplies this only to operations following the same locking protocol.
See [mutex guarantees](05-synchronization.md#a-mutex-provides-mutual-exclusion-and-ordering).

### Mutex

A mutual-exclusion lock held by one thread at a time. Unlock and a subsequent
acquisition of the same mutex also provide ordering for protected accesses.
All conflicting accesses must follow the protection rule.
See [mutex synchronization](05-synchronization.md#a-mutex-provides-mutual-exclusion-and-ordering).

### Mutex-backed critical section

A CPython critical section operating on explicit `PyMutex` pointers rather than
Python object locks. `Py_BEGIN_CRITICAL_SECTION_MUTEX` and
`Py_BEGIN_CRITICAL_SECTION2_MUTEX` retain suspension semantics and are no-ops in
the default build, unlike direct `PyMutex` locking.
See [explicit-mutex variants](11-cpython-critical-sections.md#mutex-backed-critical-sections-support-non-object-state).

### Nonrecursive mutex / recursive mutex

A nonrecursive mutex does not permit repeated acquisition by its owning thread;
the consequence depends on the interface. A recursive mutex permits repeated
acquisition with matching releases. `PyMutex` is nonrecursive, and CPython
critical-section recursive entry is not continuous recursive-mutex ownership.
See [locking ownership](05-synchronization.md#locking-has-ownership-rules),
[PyMutex recursion](10-pymutex.md#pymutex-is-not-recursive), and
[critical-section recursive entry](11-cpython-critical-sections.md#recursive-entry-avoids-deadlock-but-can-release-outer-locks).

### ob_mutex / per-object lock

The internal mutex associated with a free-threaded Python object. Ordinary
extension code must acquire `ob_mutex` through critical sections, not direct
mutex locking. It protects cooperating object operations, not every reachable
object or every lock-free access path.
See [ob_mutex protocol](11-cpython-critical-sections.md#use-critical-sections-to-acquire-ob_mutex)
and [cooperating accesses](11-cpython-critical-sections.md#object-locks-exclude-only-cooperating-operations).

### Object lifetime / lifetime protection

The period during which an object exists and can be validly accessed, and the
protocol keeping it valid throughout use. A safe pointer load or a lock protecting
that load does not automatically keep the target alive after unlocking.
See [pointer and lifetime](01-shared-mutable-memory.md#pointer-access-and-object-lifetime-are-separate-problems)
and [lifetime after unlock](05-synchronization.md#locks-do-not-preserve-facts-after-unlock).

### Obstruction-free

A progress guarantee that an operation completes if it eventually runs without
interference from other threads.
See [progress guarantees](07-lock-free-algorithms.md#lock-free-describes-system-wide-progress).

### Optimistic read / tentative read

A read that collects a tentative result, validates it against concurrent changes,
and retries if needed. Every tentative access must already be legal and
lifetime-safe; later validation cannot repair a C data race or use-after-free.
See [optimistic operations](07-lock-free-algorithms.md#optimistic-operations-read-validate-and-retry)
and [precise snapshot protocol](07-lock-free-algorithms.md#advanced-example-optimistic-reads-need-a-precise-protocol).

### Optimistic reference acquisition

Obtaining a strong reference from a shared pointer without first locking its
container, then validating the pointer. CPython's internal
`_Py_TryIncrefCompare`, `_Py_XGetRef`, and `_Py_TryXGetRef` require specialized
writer, reference-count, and allocator protocols, including **maybe-weakref
state**. They are not permission to increment an arbitrary stale pointer.
See [allocator and reference-acquisition protocol](13-qsbr-in-cpython.md#allocator-reuse-is-part-of-the-lifetime-problem).

### Ordinary memory access

A non-atomic read or write. Conflicting accesses across threads require
happens-before ordering even when the hardware instruction is indivisible.
See [ordinary C data races](02-the-c-abstract-machine-and-undefined-behavior.md#an-ordinary-c-data-race-is-undefined-behavior).

### Owned reference / strong reference

A Python reference that keeps an object alive and whose holder must eventually
release or transfer it. It protects lifetime, not mutable contents. A safely
acquired strong reference can allow use after a protecting lock is released.
See [reference ownership and lookup](09-cpython-concurrency-model.md#borrowed-references-need-renewed-scrutiny)
and [lifetime after unlock](05-synchronization.md#locks-do-not-preserve-facts-after-unlock).

### Ownership rule

A contract defining who controls state or references and how ownership can be
transferred. Single-thread ownership removes synchronization only while other
threads cannot access that state.
See [private-state ownership](14-choosing-a-technique.md#removing-sharing-needs-an-ownership-rule)
and [reference cleanup in optimistic code](07-lock-free-algorithms.md#lock-free-code-needs-a-complete-proof).

## P

### Parking-lot mechanism

CPython's internal mechanism for putting mutex waiters to sleep and waking them.
Waiters are associated with the mutex's address, which must remain stable.
An unlock can hand ownership directly to a waiter rather than let new arrivals
acquire first.
See [fast and parked paths](10-pymutex.md#the-implementation-has-fast-and-parked-paths)
and [stable address](10-pymutex.md#a-pymutex-has-a-stable-address).

### Pause latency

The cost of a stop-the-world pause, including waiting for affected threads to
reach safe points, not just the work performed while stopped.
See [pause performance](12-stop-the-world.md#stop-the-world-has-a-broad-performance-cost).

### Per-thread state / thread-local state

State assigned separately to each thread, often using thread-local storage.
It needs no synchronization only while no other thread accesses it; publishing
a pointer can make it shared.
See [per-thread state](06-concurrency-and-performance.md#per-thread-state-can-eliminate-synchronization).

### Physical reclamation

Destroying an object, reusing its storage, or returning storage to the allocator
once covered readers can no longer use it. Destruction can have execution-context
requirements beyond lifetime safety.
See [removal and reclamation](08-safe-memory-reclamation.md#grace-periods-separate-removal-from-reclamation)
and [destruction concerns](08-safe-memory-reclamation.md#reclamation-and-destruction-are-different-concerns).

### Pointer lifetime

Restrictions on a saved pointer imposed by its target's lifetime. In strict C,
the pointer becomes indeterminate when that lifetime ends; comparing or publishing
it afterward also requires care, not just dereferencing it.
See [hazard-pointer C lifetime constraints](08-safe-memory-reclamation.md#hazard-pointers-protect-named-objects).

### Predicate

A condition computed from protected state that determines whether a waiter may
proceed. Condition-variable waiters recheck it in a loop while holding the mutex.
See [condition-variable predicates](05-synchronization.md#condition-variables-wait-for-state-changes).

### Progress guarantee

A statement about which concurrent operations must complete under specified
execution assumptions. The guarantee applies to the whole operation, including
allocation, reclamation, and called functions, not just its CAS loop.
See [progress categories](07-lock-free-algorithms.md#lock-free-describes-system-wide-progress)
and [complete algorithm proof](07-lock-free-algorithms.md#lock-free-code-needs-a-complete-proof).

### Publication / safe publication

Making initialized state available to other threads with ordering that makes
initialization visible. **Release/acquire publication** establishes this through
a release and an acquire that observes it or its release sequence. Publication
does not protect later mutation or extend lifetime.
See [publication example and reuse constraints](03-the-c-memory-model.md#publishing-data-with-release-and-acquire).

### Py_BEGIN_ALLOW_THREADS / Py_END_ALLOW_THREADS

Public macros delimiting a detached region, commonly around blocking native
work. The region must not use APIs requiring attachment, even in a free-threaded
build. Detachment can suspend critical sections and end QSBR pointer protection.
See [attachment rules](09-cpython-concurrency-model.md#attached-detached-and-suspended-are-distinct-states)
and [QSBR pointer scope](13-qsbr-in-cpython.md#a-quiescent-state-is-a-promise-from-one-thread).

### Py_BEGIN_CRITICAL_SECTION / Py_END_CRITICAL_SECTION

Public macros delimiting a one-object CPython critical section. They create a
lexical C block and must be paired without an early exit skipping the end.
The low-level `PyCriticalSection_Begin` / `PyCriticalSection_End` functions provide
corresponding paired entry and exit.
See [macro scope and cleanup](11-cpython-critical-sections.md#the-macros-form-a-lexical-block).

### Py_GIL_DISABLED

The compile-time macro identifying a free-threaded CPython build. It does not
report whether the GIL is currently enabled at runtime.
See [build versus runtime configuration](09-cpython-concurrency-model.md#the-free-threaded-build-can-run-with-the-gil-enabled).

### Py_mod_gil / Py_MOD_GIL_NOT_USED

The module-initialization slot and value by which a multi-phase extension declares
support for execution without the GIL. Single-phase extensions can use
`PyUnstable_Module_SetGIL`. The declaration does not itself synchronize extension
state.
See [extension support declarations](09-cpython-concurrency-model.md#the-free-threaded-build-can-run-with-the-gil-enabled).

### _Py_atomic_* helpers

CPython's internal portable atomic-operation family, operating on ordinary C
fields. Unsuffixed operations are sequentially consistent; available suffixes
select other orders. All competing accesses must follow the atomic protocol.
See [CPython atomic API](04-atomic-operations.md#use-cpythons-atomic-api-in-interpreter-code).

### _PyEval_StopTheWorld / _PyEval_StopTheWorldAll

Internal operations pausing thread states for one interpreter or all interpreters.
The corresponding `_PyEval_StartTheWorld` / `_PyEval_StartTheWorldAll` restart must
match the stop's scope on every exit path. These operations are no-ops in the
default build.
See [pause scope](12-stop-the-world.md#a-pause-can-cover-one-interpreter-or-the-runtime).

### _PyMem_FreeDelayed / _PyMem_ProcessDelayed

Internal helpers retiring raw storage and processing delayed work. Normal
free-threaded processing waits for QSBR goals; it can also release queued strong
references and thereby invoke arbitrary deallocation code.
See [delayed reclamation helpers](13-qsbr-in-cpython.md#delayed-frees-and-decrefs-connect-lifetime-to-qsbr).

### _PyObject_XDecRefDelayed / _PyObject_XSetRefDelayed

Internal helpers delaying release of an existing reference, or replacing a pointer
and delaying release of its old reference. The replacement helper takes ownership
of the new reference and publishes it, but does not serialize competing writers.
See [delayed reference release](13-qsbr-in-cpython.md#delayed-frees-and-decrefs-connect-lifetime-to-qsbr).

### PyMutex

CPython's public lightweight nonrecursive mutex type. It must be zero-initialized
and must not be copied or moved after initialization. Direct locking works in
both build configurations independently of the GIL.
See [PyMutex](10-pymutex.md) and
[stable address](10-pymutex.md#a-pymutex-has-a-stable-address).

### PyMutex_IsLocked

A diagnostic query reporting whether a mutex appears locked at one instant.
It does not acquire ownership, identify the owner, or promise memory ordering.
See [diagnostic-only query](10-pymutex.md#pymutex_islocked-is-only-diagnostic).

### PyMutex_Lock / PyMutex_Unlock

Public direct acquisition and release functions with acquire and release ordering.
A parked acquisition temporarily detaches an attached thread state and reattaches
before returning. A directly acquired lock must be released exactly once.
See [ordering](10-pymutex.md#lock-and-unlock-delimit-the-invariant),
[waiting](10-pymutex.md#waiting-temporarily-detaches-the-thread-state), and
[unlock discipline](10-pymutex.md#unlock-exactly-once-on-every-path).

### PyThreadState

CPython's execution-state record for a thread in one interpreter. It tracks
Python execution context and, in a free-threaded build, the critical-section
stack and participation in runtime coordination.
See [attachment states and APIs](09-cpython-concurrency-model.md#attached-detached-and-suspended-are-distinct-states).

## Q–R

### QSBR (quiescent-state-based reclamation)

A reclamation scheme in which participating threads report that they retain no
protected pointers from earlier work. Retired storage or references can be
reclaimed once all relevant threads have progressed sufficiently. CPython's
implementation is internal, supplies lifetime protection only for covered
readers, and does not itself provide publication ordering.
See [general QSBR](08-safe-memory-reclamation.md#qsbr-reports-points-with-no-old-references),
[CPython QSBR](13-qsbr-in-cpython.md), and
[ordering limitations](13-qsbr-in-cpython.md#qsbr-does-not-provide-publication-ordering-by-itself).

### Quiescent state / quiescent point

A point where a participating thread promises it no longer retains protected
pointers from earlier work. Those pointers must not be used afterward without
new lifetime protection. Being paused at an arbitrary instruction is insufficient.
See [the quiescent-state contract](13-qsbr-in-cpython.md#a-quiescent-state-is-a-promise-from-one-thread).

### Race condition

A logical bug whose outcome depends on the interleaving of concurrent operations.
It can occur even when every access is atomic or individually locked and no C
data race exists.
See [race-condition distinction](01-shared-mutable-memory.md#data-races-and-race-conditions-are-different).

### Raw storage / backing array

An allocation managed separately from Python object reference counting, such as
a list's item-pointer array. Keeping the containing object alive does not keep
its replaced internal storage alive.
See [QSBR and internal storage](13-qsbr-in-cpython.md#qsbr-complements-reference-counting).

### RCU (read-copy-update)

A family of techniques with defined read-side regions, replacement publication,
and reclamation after a grace period covering old readers. Blocking and ordering
rules vary by implementation.
See [RCU](08-safe-memory-reclamation.md#rcu-makes-read-side-work-cheap).

### rd_seq / wr_seq

CPython's internal QSBR progress values: `wr_seq` is the interpreter's current
write sequence; `rd_seq` tracks the minimum reported sequence of attached threads.
Valid write sequences are odd, and a per-thread sequence of zero marks it offline.
See [sequence tracking](13-qsbr-in-cpython.md#cpython-tracks-one-write-sequence-per-interpreter).

### Read-mostly data

Data read much more frequently than it is updated. Immutable snapshots and
reclamation protocols can avoid shared metadata writes on every read.
See [read-mostly snapshots](06-concurrency-and-performance.md#read-mostly-data-benefits-from-immutable-snapshots)
and [QSBR use cases](13-qsbr-in-cpython.md#qsbr-is-useful-for-read-mostly-internal-storage).

### Read-side region

A defined interval in which a reader may obtain and use protected pointers.
The protocol specifies entry, exit, ordering, blocking restrictions, and whether
pointers may escape that region.
See [reader scopes](08-safe-memory-reclamation.md#reclamation-needs-a-defined-reader-scope).

### Reacquisition

Acquiring a lock again after release or critical-section suspension. It orders
access with intervening lock holders but does not restore the earlier state.
See [reacquisition and stale facts](11-cpython-critical-sections.md#reacquisition-does-not-restore-old-facts).

### Reentrancy / recursive entry

Entering related code before an earlier invocation finishes, often through a
callback or finalizer. Reentrancy can invalidate assumptions even with the GIL.
Recursive CPython critical-section entry avoids self-deadlock but can release
outer locks; it is not ordinary recursive-mutex ownership.
See [callback risks](10-pymutex.md#avoid-arbitrary-python-execution-while-holding-a-direct-mutex)
and [recursive critical-section entry](11-cpython-critical-sections.md#recursive-entry-avoids-deadlock-but-can-release-outer-locks).

### Reference acquisition

Obtaining an owned reference that keeps a Python object alive. The object must
remain valid during acquisition; incrementing its count after an unprotected
pointer load can be too late.
See [reference-acquisition race](07-lock-free-algorithms.md#reference-counting-alone-may-be-too-late)
and [safe borrowed-reference alternatives](09-cpython-concurrency-model.md#borrowed-references-need-renewed-scrutiny).

### Reference counting

Tracking references to manage object lifetime. Free-threaded CPython uses
concurrency-aware internal mechanisms while preserving public reference-ownership
contracts. QSBR and cyclic GC complement rather than replace reference counting.
See [CPython reference counting](09-cpython-concurrency-model.md#reference-counting-is-concurrency-aware).

### Relaxed ordering

Atomic ordering that provides atomicity and the object's modification-order
guarantees without independently synchronizing other accesses. C uses
`memory_order_relaxed`. Suitable fences or release sequences can let relaxed
operations participate in synchronization.
See [relaxed ordering](04-atomic-operations.md#relaxed-ordering-provides-atomicity-only).

### Release ordering

Ordering that can publish accesses preceding a release to accesses following a
matching acquire. A **release store** uses `memory_order_release`; mutex unlock
also supplies release ordering. It does not publish future writes.
See [release](04-atomic-operations.md#release-publishes-earlier-work).

### Release sequence

A sequence in one atomic object's modification order headed by a release
operation. An immediately following relaxed RMW can extend it; an acquire
reading a value from the sequence can synchronize with its head. The exact
sequence definition depends on the C standard version.
See [release sequences](03-the-c-memory-model.md#synchronizes-with-connects-threads).

### Runtime-wide pause

A stop-the-world pause coordinating Python thread states across all interpreters.
It has broader cost than an interpreter-wide pause and does not by itself stop
independent native-thread accesses.
See [pause scopes](12-stop-the-world.md#a-pause-can-cover-one-interpreter-or-the-runtime).

## S

### Safe memory reclamation

A protocol preventing storage from being freed or dangerously reused while
covered readers can still use it. Lifetime safety is separate from pointer
atomicity, publication ordering, and data-race freedom.
See [safe memory reclamation](08-safe-memory-reclamation.md) and
[separate correctness proofs](08-safe-memory-reclamation.md#ordering-and-lifetime-remain-separate-proofs).

### Safe point / evaluation-loop checkpoint

A runtime execution point where a thread can respond to coordination requests,
such as a stop-the-world pause. Selected CPython evaluation-loop checks also
report QSBR quiescent states, which have a separate pointer-use contract.
See [pause safe points](12-stop-the-world.md#attached-threads-stop-at-safe-points)
and [QSBR reports](13-qsbr-in-cpython.md#a-quiescent-state-is-a-promise-from-one-thread).

### Sequenced-before

C's ordering relation between operations within one thread. It constrains the
abstract execution, not necessarily emitted instruction order, and alone does
not synchronize different threads.
See [sequenced-before](03-the-c-memory-model.md#sequenced-before-orders-operations-within-a-thread).

### Sequential consistency

Atomic ordering supplying acquire or release effects as appropriate and one
total order of sequentially consistent operations shared by threads. C uses
`memory_order_seq_cst`. This does not put every program operation in that order
or combine separate atomic operations into a transaction.
See [sequential consistency](04-atomic-operations.md#sequential-consistency-provides-a-stronger-default).

### Serialization

Forcing competing work to proceed in an order rather than simultaneously. Both
mutexes and updates to a single atomic object can serialize progress.
See [atomic and lock serialization](06-concurrency-and-performance.md#atomics-and-locks-can-both-serialize-execution).

### Sharding

Splitting shared state into separately updated parts to reduce contention.
Combining parts costs work and may mix values from different moments; concurrent
access to any one shard still requires an access rule.
See [sharding](06-concurrency-and-performance.md#sharding-reduces-shared-writes).

### Shared state / shared mutable memory

Memory accessible to multiple threads, potentially including related fields
forming one logical state. If threads can modify it, synchronization must cover
all conflicting accesses and preserve its invariants.
See [identifying shared state](01-shared-mutable-memory.md#start-by-identifying-the-shared-state).

### Signal / broadcast

Condition-variable notifications waking one or more eligible waiters, or all
waiters respectively, according to the interface. A notification tells a waiter
to recheck state; it does not transfer ownership of an item or prove the predicate.
See [condition-variable notifications](05-synchronization.md#condition-variables-wait-for-state-changes).

### Snapshot

A view of related values representing one consistent state. Separate atomic
loads do not automatically form an atomic snapshot, and QSBR does not provide one.
See [multi-field commit](07-lock-free-algorithms.md#multi-field-state-needs-one-commit-mechanism)
and [versioned snapshots](07-lock-free-algorithms.md#advanced-example-optimistic-reads-need-a-precise-protocol).

### Spin lock

A lock whose waiting threads repeatedly poll instead of sleeping. Spinning can
waste processor time when the owner cannot run or holds the lock too long.
See [spin locks](05-synchronization.md#spin-locks-trade-sleeping-for-repeated-polling).

### Spurious failure

Failure of weak compare-exchange even when the current and expected values compare
equal. Retry loops must handle it without assuming another thread made progress.
See [weak and strong CAS](04-atomic-operations.md#compare-exchange-updates-conditionally).

### Spurious wakeup

Return from a wait without a notification establishing the desired condition.
A condition-variable waiter must recheck its predicate under the mutex.
See [condition-variable waits](05-synchronization.md#condition-variables-wait-for-state-changes).

### Stalled reader

A reader delayed while it may retain a protected pointer. Safe reclamation keeps
the required storage rather than freeing it merely because a timeout elapsed.
See [stalled-reader retention](08-safe-memory-reclamation.md#stalled-threads-trade-safety-for-memory-retention).

### Starvation

An individual thread or operation repeatedly failing to proceed while others
continue progressing. Mutual exclusion and lock-free algorithms can both allow it.
See [fairness](05-synchronization.md#synchronization-does-not-imply-fairness)
and [lock-free guarantees](07-lock-free-algorithms.md#lock-free-describes-system-wide-progress).

### Stop-the-world / stopped region

CPython runtime coordination suspending affected attached thread states and
preventing detached states from reattaching until restart. The stopped region
runs between completed stop and matching restart. It must not depend on suspended
threads making progress or run arbitrary Python code. A pause is not a general
replacement for safe reclamation after execution resumes.
See [stop-the-world](12-stop-the-world.md),
[lock hazards](12-stop-the-world.md#do-not-wait-for-locks-while-threads-are-suspended), and
[ordering versus lifetime](14-choosing-a-technique.md#keep-ordering-and-lifetime-as-separate-checks).

### Store-load ordering

A protocol's requirement that a later load not take effect before an earlier
store. Hazard-pointer publication and validation need this on reader and
reclaimer paths; acquire and release alone do not automatically supply it.
See [hazard-pointer ordering](08-safe-memory-reclamation.md#hazard-pointers-protect-named-objects).

### Subinterpreter

An interpreter in a process distinct from the main interpreter. Thread attachment
must select the correct interpreter, and per-interpreter state can still be shared
by its threads.
See [foreign-thread attachment](09-cpython-concurrency-model.md#attached-detached-and-suspended-are-distinct-states)
and [extension state](09-cpython-concurrency-model.md#extension-state-may-now-be-genuinely-shared).

### Suspended thread state

A thread state paused by runtime coordination. Unlike an ordinarily detached
thread, it cannot attach and resume Python execution until the pause controller
permits it.
See [distinct thread states](09-cpython-concurrency-model.md#attached-detached-and-suspended-are-distinct-states).

### Suspension (critical section)

Temporarily marking a CPython critical section inactive and releasing its locks.
Other threads can change the state before resumption, so old observations may
need revalidation.
See [suspension](11-cpython-critical-sections.md#detachment-suspends-all-active-sections)
and [reacquisition](11-cpython-critical-sections.md#reacquisition-does-not-restore-old-facts).

### Synchronization

Coordination that controls concurrent access or establishes ordering between
threads. A synchronization protocol must cover every competing access path;
source statement order alone is insufficient.
See [synchronization](05-synchronization.md) and
[protocol review](14-choosing-a-technique.md#review-the-complete-protocol).

### Synchronizes-with

A relation established by suitable synchronization operations, such as mutex
unlock and subsequent acquisition or a release and an acquire observing its
value or release sequence. It connects threads and contributes to happens-before.
See [synchronizes-with](03-the-c-memory-model.md#synchronizes-with-connects-threads).

## T–W

### Thread registration

Enrolling a thread in a reclamation protocol before it accesses protected data.
Exit and detachment must update metadata without dropping protection while the
thread can still use old pointers.
See [reclamation lifecycle](08-safe-memory-reclamation.md#thread-exit-and-detachment-require-cleanup)
and [CPython QSBR registration](13-qsbr-in-cpython.md#attached-and-detached-states-affect-grace-periods).

### Torn access

An access observing part of a write rather than one complete value. Atomic
access prevents tearing of its own object, not inconsistent snapshots across
multiple objects.
See [atomic loads and stores](04-atomic-operations.md#loads-and-stores-transfer-individual-values).

### Two-object critical section

`Py_BEGIN_CRITICAL_SECTION2` / `Py_END_CRITICAL_SECTION2` protect two object locks
together while active. The section can still suspend both locks. Nested
single-object sections do not reliably provide simultaneous ownership.
See [two-object locking](11-cpython-critical-sections.md#nested-single-object-sections-do-not-lock-two-objects-reliably).

### Type-stable storage

Backing storage whose relevant layout remains suitable for explicitly permitted
speculative accesses even during allocation reuse. It does not preserve object
identity or make arbitrary stale-pointer accesses valid in portable C.
See [type-stable reuse](08-safe-memory-reclamation.md#type-stable-storage-allows-limited-reuse)
and [CPython allocator guarantees](13-qsbr-in-cpython.md#allocator-reuse-is-part-of-the-lifetime-problem).

### Undefined behavior

An execution for which C imposes no requirements. A data race need not crash or
produce a predictable failure, and optimizers can assume valid programs avoid it.
See [undefined behavior](02-the-c-abstract-machine-and-undefined-behavior.md#undefined-behavior-removes-the-normal-requirements).

### Use-after-free

Access to storage after its allocation has been freed. Atomic pointer access
and validation after dereferencing do not make it safe.
See [pointer target lifetime](08-safe-memory-reclamation.md#an-atomic-pointer-does-not-protect-its-target).

### Validation / revalidation

Checking that tentative observations still satisfy the protocol, or checking them
again after possible interference such as lock suspension. Validation cannot
retroactively make invalid memory accesses legal.
See [optimistic validation](07-lock-free-algorithms.md#optimistic-operations-read-validate-and-retry)
and [revalidation after reacquisition](11-cpython-critical-sections.md#reacquisition-does-not-restore-old-facts).

### volatile

A C qualifier governing volatile-object accesses, not a synchronization mechanism.
In ISO C it does not make accesses atomic, establish happens-before, or safely
publish other data. Compiler-specific modes such as MSVC's `/volatile:ms` are
not portable ISO C synchronization.
See [volatile](02-the-c-abstract-machine-and-undefined-behavior.md#volatile-does-not-provide-synchronization).

### Wait-free / bounded wait-free

A progress guarantee that each operation completes in finitely many of its own
steps regardless of other threads. Bounded wait-free adds a fixed bound on those
steps. This is stronger than system-wide lock-free progress.
See [progress guarantees](07-lock-free-algorithms.md#lock-free-describes-system-wide-progress).

### Wraparound

A bounded counter cycling back to a previously used value. Generation, version,
and epoch protocols must not confuse that value with an earlier occurrence.
See [ABA and counter wraparound](07-lock-free-algorithms.md#aba-defeats-value-only-validation)
and [epoch comparisons](08-safe-memory-reclamation.md#epoch-based-reclamation-groups-readers).

---

Return to the [contents and topic index](contents.md) or
[primer introduction](index.md).
