# Contents: concurrent C and free-threaded CPython

This index covers the primer in reading order and links to every chapter section. Chapters 1–8 explain general concurrent C concepts; chapters 9–13 explain CPython's mechanisms; chapter 14 brings them together into a decision guide.

For targeted lookup, start with the topic index below. For edits, read the linked section in context and check related chapters before adding an explanation that may already exist. Section links are preferable to line numbers, which change as the guide is edited.

For definitions of concurrency terms, see the [glossary](glossary.md).

## Topic index

| Topic or question | Primary section | Related material |
| --- | --- | --- |
| Data race versus race condition | [Definitions and check-then-act example](01-shared-mutable-memory.md#data-races-and-race-conditions-are-different) | [Compound container operations](09-cpython-concurrency-model.md#container-safety-does-not-make-compound-operations-atomic) |
| Undefined behavior, compiler optimization, as-if rule | [Compiler transformations](02-the-c-abstract-machine-and-undefined-behavior.md#the-compiler-does-not-execute-the-source-literally) | [Undefined behavior](02-the-c-abstract-machine-and-undefined-behavior.md#undefined-behavior-removes-the-normal-requirements) |
| Memory locations, bit-fields, hardware atomicity | [C data races and memory locations](02-the-c-abstract-machine-and-undefined-behavior.md#an-ordinary-c-data-race-is-undefined-behavior) | [Hardware versus C atomicity](02-the-c-abstract-machine-and-undefined-behavior.md#hardware-atomicity-is-not-c-atomicity) |
| Why `volatile` is not synchronization | [`volatile`](02-the-c-abstract-machine-and-undefined-behavior.md#volatile-does-not-provide-synchronization) | [Source order](02-the-c-abstract-machine-and-undefined-behavior.md#source-order-alone-does-not-synchronize-threads) |
| Happens-before and synchronization proof | [Happens-before](03-the-c-memory-model.md#happens-before-combines-the-ordering) | [Explaining safe access](03-the-c-memory-model.md#use-the-model-to-explain-why-an-access-is-safe) |
| Release/acquire publication and reuse constraints | [Complete publication example](03-the-c-memory-model.md#publishing-data-with-release-and-acquire) | [Memory-order options](04-atomic-operations.md#relaxed-ordering-provides-atomicity-only) |
| Atomic RMW, exchange, CAS, weak versus strong CAS | [Atomic operations](04-atomic-operations.md#read-modify-write-is-one-indivisible-operation) | [CAS loops](07-lock-free-algorithms.md#cas-commits-a-conditional-change) |
| `_Py_atomic_*`, `FT_ATOMIC_*`, C11 API mapping | [CPython atomic API](04-atomic-operations.md#use-cpythons-atomic-api-in-interpreter-code) | [Build versus runtime GIL](09-cpython-concurrency-model.md#the-free-threaded-build-can-run-with-the-gil-enabled) |
| Fences and versioned optimistic snapshots | [Fence basics](04-atomic-operations.md#fences-order-without-carrying-the-value-operation) | [Advanced snapshot example and proof](07-lock-free-algorithms.md#advanced-example-optimistic-reads-need-a-precise-protocol) |
| Which fields a lock protects; complete transitions | [Mutex ownership of state](05-synchronization.md#name-the-state-protected-by-each-mutex) | [Protecting invariants](05-synchronization.md#protect-invariants-not-individual-accesses) |
| Condition variables, wakeups, events, spin locks | [Condition variables](05-synchronization.md#condition-variables-wait-for-state-changes) | [Events](05-synchronization.md#events-represent-persistent-notification-state), [spin locks](05-synchronization.md#spin-locks-trade-sleeping-for-repeated-polling) |
| Deadlocks and ordering multiple mutexes | [General lock ordering](05-synchronization.md#multiple-mutexes-require-a-lock-order) | [`PyMutex` lock ordering](10-pymutex.md#define-a-lock-order-for-multiple-mutexes) |
| Pointer lifetime and reference acquisition under a lock | [Lifetime after unlock](05-synchronization.md#locks-do-not-preserve-facts-after-unlock) | [Borrowed versus strong references](09-cpython-concurrency-model.md#borrowed-references-need-renewed-scrutiny) |
| Cache coherence, false sharing, atomic instruction cost | [Cache-line granularity](06-concurrency-and-performance.md#coherence-works-at-cache-line-granularity) | [Atomic cost](06-concurrency-and-performance.md#atomic-does-not-mean-inexpensive) |
| Sharding, per-thread state, immutable snapshots | [Sharding](06-concurrency-and-performance.md#sharding-reduces-shared-writes) | [Per-thread state](06-concurrency-and-performance.md#per-thread-state-can-eliminate-synchronization), [snapshots](06-concurrency-and-performance.md#read-mostly-data-benefits-from-immutable-snapshots) |
| Lock-free, wait-free, obstruction-free, starvation | [Progress guarantees](07-lock-free-algorithms.md#lock-free-describes-system-wide-progress) | [Fairness](05-synchronization.md#synchronization-does-not-imply-fairness) |
| Linearizability, retries, multi-field commit, ABA | [Linearization points](07-lock-free-algorithms.md#the-linearization-point-defines-when-an-operation-takes-effect) | [Multi-field commit](07-lock-free-algorithms.md#multi-field-state-needs-one-commit-mechanism), [ABA](07-lock-free-algorithms.md#aba-defeats-value-only-validation) |
| Hazard pointers, epochs, RCU, QSBR | [Reclamation reader scope](08-safe-memory-reclamation.md#reclamation-needs-a-defined-reader-scope) | [Hazard pointers](08-safe-memory-reclamation.md#hazard-pointers-protect-named-objects), [epochs](08-safe-memory-reclamation.md#epoch-based-reclamation-groups-readers), [RCU](08-safe-memory-reclamation.md#rcu-makes-read-side-work-cheap), [QSBR](08-safe-memory-reclamation.md#qsbr-reports-points-with-no-old-references) |
| Thread attachment, detachment, suspension, foreign threads | [Thread-state contracts](09-cpython-concurrency-model.md#attached-detached-and-suspended-are-distinct-states) | [`PyMutex` waiting](10-pymutex.md#waiting-temporarily-detaches-the-thread-state) |
| Extension support declaration and shared module state | [Runtime GIL and module declarations](09-cpython-concurrency-model.md#the-free-threaded-build-can-run-with-the-gil-enabled) | [Extension state](09-cpython-concurrency-model.md#extension-state-may-now-be-genuinely-shared) |
| `PyMutex` initialization, address stability, diagnostics | [`PyMutex` chapter](10-pymutex.md) | [Stable address](10-pymutex.md#a-pymutex-has-a-stable-address), [lock-state query](10-pymutex.md#pymutex_islocked-is-only-diagnostic) |
| Critical-section suspension and revalidation | [Detachment and suspension](11-cpython-critical-sections.md#detachment-suspends-all-active-sections) | [Restore invariants](11-cpython-critical-sections.md#restore-invariants-before-any-possible-suspension), [reacquisition](11-cpython-critical-sections.md#reacquisition-does-not-restore-old-facts) |
| Two-object critical sections, recursion, `ob_mutex` | [Two-object form](11-cpython-critical-sections.md#nested-single-object-sections-do-not-lock-two-objects-reliably) | [Recursive entry](11-cpython-critical-sections.md#recursive-entry-avoids-deadlock-but-can-release-outer-locks), [`ob_mutex`](11-cpython-critical-sections.md#use-critical-sections-to-acquire-ob_mutex) |
| Mutex-backed critical sections, limited API, Clinic helpers | [Mutex-backed forms](11-cpython-critical-sections.md#mutex-backed-critical-sections-support-non-object-state) | [Build and API availability](11-cpython-critical-sections.md#critical-sections-are-no-ops-in-the-default-build), [generated code](11-cpython-critical-sections.md#recognize-cpythons-generated-code-and-internal-helpers) |
| Stop-the-world scope and hazards | [Interpreter versus runtime scope](12-stop-the-world.md#a-pause-can-cover-one-interpreter-or-the-runtime) | [Lock hazards](12-stop-the-world.md#do-not-wait-for-locks-while-threads-are-suspended), [callbacks and cleanup](12-stop-the-world.md#do-not-run-arbitrary-python-code-while-stopped) |
| CPython QSBR sequences, deferred frees and decrefs | [Sequence tracking](13-qsbr-in-cpython.md#cpython-tracks-one-write-sequence-per-interpreter) | [Delayed-work helpers](13-qsbr-in-cpython.md#delayed-frees-and-decrefs-connect-lifetime-to-qsbr), [batching](13-qsbr-in-cpython.md#sequence-advancement-can-be-deferred) |
| QSBR pointer scope, retained memory, allocator reuse, try-incref | [Quiescent-state obligations](13-qsbr-in-cpython.md#a-quiescent-state-is-a-promise-from-one-thread) | [Retention](13-qsbr-in-cpython.md#a-delayed-thread-can-retain-much-memory), [allocator and reference acquisition](13-qsbr-in-cpython.md#allocator-reuse-is-part-of-the-lifetime-problem) |
| Selecting or combining mechanisms; final review checklist | [Decision order](14-choosing-a-technique.md#a-practical-decision-order) | [Combining mechanisms](14-choosing-a-technique.md#give-each-mechanism-one-explicit-job), [checklist](14-choosing-a-technique.md#review-the-complete-protocol) |

## Detailed chapter contents

### 01. [The basic problem: shared mutable memory](01-shared-mutable-memory.md)

Introduces conflicting accesses, logical races, related fields, and the separate pointer-lifetime problem.

- [A simple shared variable](01-shared-mutable-memory.md#a-simple-shared-variable)
- [Data races and race conditions are different](01-shared-mutable-memory.md#data-races-and-race-conditions-are-different)
- [Shared state is often larger than one variable](01-shared-mutable-memory.md#shared-state-is-often-larger-than-one-variable)
- [Pointer access and object lifetime are separate problems](01-shared-mutable-memory.md#pointer-access-and-object-lifetime-are-separate-problems)
- [Start by identifying the shared state](01-shared-mutable-memory.md#start-by-identifying-the-shared-state)

### 02. [The C abstract machine and undefined behavior](02-the-c-abstract-machine-and-undefined-behavior.md)

Explains why correctness depends on the C rules, not observed machine instructions or tests on one CPU.

- [The compiler does not execute the source literally](02-the-c-abstract-machine-and-undefined-behavior.md#the-compiler-does-not-execute-the-source-literally)
- [Undefined behavior removes the normal requirements](02-the-c-abstract-machine-and-undefined-behavior.md#undefined-behavior-removes-the-normal-requirements)
- [An ordinary C data race is undefined behavior](02-the-c-abstract-machine-and-undefined-behavior.md#an-ordinary-c-data-race-is-undefined-behavior)
- [Hardware atomicity is not C atomicity](02-the-c-abstract-machine-and-undefined-behavior.md#hardware-atomicity-is-not-c-atomicity)
- [`volatile` does not provide synchronization](02-the-c-abstract-machine-and-undefined-behavior.md#volatile-does-not-provide-synchronization)
- [Source order alone does not synchronize threads](02-the-c-abstract-machine-and-undefined-behavior.md#source-order-alone-does-not-synchronize-threads)
- [Object lifetime is also part of correctness](02-the-c-abstract-machine-and-undefined-behavior.md#object-lifetime-is-also-part-of-correctness)
- [Use a defined synchronization rule](02-the-c-abstract-machine-and-undefined-behavior.md#use-a-defined-synchronization-rule)

### 03. [The C memory model](03-the-c-memory-model.md)

Defines ordering relationships and gives the complete release/acquire publication example and proof.

- [`sequenced-before` orders operations within a thread](03-the-c-memory-model.md#sequenced-before-orders-operations-within-a-thread)
- [`synchronizes-with` connects threads](03-the-c-memory-model.md#synchronizes-with-connects-threads)
- [`happens-before` combines the ordering](03-the-c-memory-model.md#happens-before-combines-the-ordering)
- [Publishing data with release and acquire](03-the-c-memory-model.md#publishing-data-with-release-and-acquire)
- [Atomicity and ordering are different guarantees](03-the-c-memory-model.md#atomicity-and-ordering-are-different-guarantees)
- [Each atomic object has a modification order](03-the-c-memory-model.md#each-atomic-object-has-a-modification-order)
- [Compiler and CPU ordering are different layers](03-the-c-memory-model.md#compiler-and-cpu-ordering-are-different-layers)
- [AMD64 and ARM64 provide different hardware ordering](03-the-c-memory-model.md#amd64-and-arm64-provide-different-hardware-ordering)
- [Use the model to explain why an access is safe](03-the-c-memory-model.md#use-the-model-to-explain-why-an-access-is-safe)

### 04. [Atomic operations](04-atomic-operations.md)

Explains atomic operations and memory orders using C11 examples, then maps them to CPython's interfaces.

- [Atomic objects require atomic access](04-atomic-operations.md#atomic-objects-require-atomic-access)
- [Loads and stores transfer individual values](04-atomic-operations.md#loads-and-stores-transfer-individual-values)
- [Read-modify-write is one indivisible operation](04-atomic-operations.md#read-modify-write-is-one-indivisible-operation)
- [Exchange replaces a value](04-atomic-operations.md#exchange-replaces-a-value)
- [Compare-exchange updates conditionally](04-atomic-operations.md#compare-exchange-updates-conditionally)
- [Relaxed ordering provides atomicity only](04-atomic-operations.md#relaxed-ordering-provides-atomicity-only)
- [Release publishes earlier work](04-atomic-operations.md#release-publishes-earlier-work)
- [Acquire observes published work](04-atomic-operations.md#acquire-observes-published-work)
- [Acquire-release combines both directions](04-atomic-operations.md#acquire-release-combines-both-directions)
- [Sequential consistency provides a stronger default](04-atomic-operations.md#sequential-consistency-provides-a-stronger-default)
- [Use CPython's atomic API in interpreter code](04-atomic-operations.md#use-cpythons-atomic-api-in-interpreter-code)
- [Fences order without carrying the value operation](04-atomic-operations.md#fences-order-without-carrying-the-value-operation)
- [Atomics do not solve object lifetime](04-atomic-operations.md#atomics-do-not-solve-object-lifetime)
- [Choose atomics for a complete, explainable protocol](04-atomic-operations.md#choose-atomics-for-a-complete-explainable-protocol)

### 05. [Synchronization](05-synchronization.md)

Teaches mutex-based protection of complete operations, lock ownership and ordering, and waiting primitives.

- [A mutex provides mutual exclusion and ordering](05-synchronization.md#a-mutex-provides-mutual-exclusion-and-ordering)
- [Name the state protected by each mutex](05-synchronization.md#name-the-state-protected-by-each-mutex)
- [Protect invariants, not individual accesses](05-synchronization.md#protect-invariants-not-individual-accesses)
- [Locks do not preserve facts after unlock](05-synchronization.md#locks-do-not-preserve-facts-after-unlock)
- [Locking has ownership rules](05-synchronization.md#locking-has-ownership-rules)
- [Multiple mutexes require a lock order](05-synchronization.md#multiple-mutexes-require-a-lock-order)
- [Condition variables wait for state changes](05-synchronization.md#condition-variables-wait-for-state-changes)
- [Events represent persistent notification state](05-synchronization.md#events-represent-persistent-notification-state)
- [Spin locks trade sleeping for repeated polling](05-synchronization.md#spin-locks-trade-sleeping-for-repeated-polling)
- [Synchronization does not imply fairness](05-synchronization.md#synchronization-does-not-imply-fairness)
- [Prefer locks for related state](05-synchronization.md#prefer-locks-for-related-state)
- [Review a synchronization rule as a whole](05-synchronization.md#review-a-synchronization-rule-as-a-whole)

### 06. [Concurrency and performance](06-concurrency-and-performance.md)

Covers coherence, contention, false sharing, instruction costs, and structural ways to reduce sharing.

- [CPU cores communicate through a cache-coherence system](06-concurrency-and-performance.md#cpu-cores-communicate-through-a-cache-coherence-system)
- [Coherence works at cache-line granularity](06-concurrency-and-performance.md#coherence-works-at-cache-line-granularity)
- [Contended writes move cache-line ownership](06-concurrency-and-performance.md#contended-writes-move-cache-line-ownership)
- [Atomic does not mean inexpensive](06-concurrency-and-performance.md#atomic-does-not-mean-inexpensive)
- [Mutexes have fast and contended paths](06-concurrency-and-performance.md#mutexes-have-fast-and-contended-paths)
- [Atomics and locks can both serialize execution](06-concurrency-and-performance.md#atomics-and-locks-can-both-serialize-execution)
- [Keep mutex-protected regions focused](06-concurrency-and-performance.md#keep-mutex-protected-regions-focused)
- [Sharding reduces shared writes](06-concurrency-and-performance.md#sharding-reduces-shared-writes)
- [Per-thread state can eliminate synchronization](06-concurrency-and-performance.md#per-thread-state-can-eliminate-synchronization)
- [Read-mostly data benefits from immutable snapshots](06-concurrency-and-performance.md#read-mostly-data-benefits-from-immutable-snapshots)
- [Memory allocation and layout affect scaling](06-concurrency-and-performance.md#memory-allocation-and-layout-affect-scaling)
- [Optimize only after identifying the bottleneck](06-concurrency-and-performance.md#optimize-only-after-identifying-the-bottleneck)

### 07. [Lock-free algorithms](07-lock-free-algorithms.md)

Develops progress guarantees, CAS and linearization, optimistic validation, ABA, and reclamation obligations. The advanced versioned-snapshot example is explicitly not lock-free.

- [Lock-free describes system-wide progress](07-lock-free-algorithms.md#lock-free-describes-system-wide-progress)
- [CAS commits a conditional change](07-lock-free-algorithms.md#cas-commits-a-conditional-change)
- [The linearization point defines when an operation takes effect](07-lock-free-algorithms.md#the-linearization-point-defines-when-an-operation-takes-effect)
- [Optimistic operations read, validate, and retry](07-lock-free-algorithms.md#optimistic-operations-read-validate-and-retry)
- [Advanced example: optimistic reads need a precise protocol](07-lock-free-algorithms.md#advanced-example-optimistic-reads-need-a-precise-protocol)
- [CAS can fail repeatedly under contention](07-lock-free-algorithms.md#cas-can-fail-repeatedly-under-contention)
- [Multi-field state needs one commit mechanism](07-lock-free-algorithms.md#multi-field-state-needs-one-commit-mechanism)
- [ABA defeats value-only validation](07-lock-free-algorithms.md#aba-defeats-value-only-validation)
- [Removal and reclamation are separate operations](07-lock-free-algorithms.md#removal-and-reclamation-are-separate-operations)
- [Reference counting alone may be too late](07-lock-free-algorithms.md#reference-counting-alone-may-be-too-late)
- [Safe reclamation delays freeing](07-lock-free-algorithms.md#safe-reclamation-delays-freeing)
- [Lock-free code needs a complete proof](07-lock-free-algorithms.md#lock-free-code-needs-a-complete-proof)

### 08. [Safe memory reclamation](08-safe-memory-reclamation.md)

Surveys reader protection, grace periods, hazard pointers, epochs, RCU, QSBR, and destruction constraints.

- [An atomic pointer does not protect its target](08-safe-memory-reclamation.md#an-atomic-pointer-does-not-protect-its-target)
- [Grace periods separate removal from reclamation](08-safe-memory-reclamation.md#grace-periods-separate-removal-from-reclamation)
- [Reclamation needs a defined reader scope](08-safe-memory-reclamation.md#reclamation-needs-a-defined-reader-scope)
- [Hazard pointers protect named objects](08-safe-memory-reclamation.md#hazard-pointers-protect-named-objects)
- [Epoch-based reclamation groups readers](08-safe-memory-reclamation.md#epoch-based-reclamation-groups-readers)
- [RCU makes read-side work cheap](08-safe-memory-reclamation.md#rcu-makes-read-side-work-cheap)
- [QSBR reports points with no old references](08-safe-memory-reclamation.md#qsbr-reports-points-with-no-old-references)
- [Stalled threads trade safety for memory retention](08-safe-memory-reclamation.md#stalled-threads-trade-safety-for-memory-retention)
- [Thread exit and detachment require cleanup](08-safe-memory-reclamation.md#thread-exit-and-detachment-require-cleanup)
- [Reclamation and destruction are different concerns](08-safe-memory-reclamation.md#reclamation-and-destruction-are-different-concerns)
- [Type-stable storage allows limited reuse](08-safe-memory-reclamation.md#type-stable-storage-allows-limited-reuse)
- [Ordering and lifetime remain separate proofs](08-safe-memory-reclamation.md#ordering-and-lifetime-remain-separate-proofs)
- [Choose reclamation from the reader contract](08-safe-memory-reclamation.md#choose-reclamation-from-the-reader-contract)

### 09. [CPython's concurrency model](09-cpython-concurrency-model.md)

Introduces the two builds, thread-state contracts, public API implications, and replacements for GIL-based assumptions.

- [The GIL serializes attached threads in the traditional build](09-cpython-concurrency-model.md#the-gil-serializes-attached-threads-in-the-traditional-build)
- [Free threading allows several attached threads](09-cpython-concurrency-model.md#free-threading-allows-several-attached-threads)
- [The free-threaded build can run with the GIL enabled](09-cpython-concurrency-model.md#the-free-threaded-build-can-run-with-the-gil-enabled)
- [Attached, detached, and suspended are distinct states](09-cpython-concurrency-model.md#attached-detached-and-suspended-are-distinct-states)
- [Stop-the-world operations use thread-state transitions](09-cpython-concurrency-model.md#stop-the-world-operations-use-thread-state-transitions)
- [The GIL's old assumptions must be replaced individually](09-cpython-concurrency-model.md#the-gils-old-assumptions-must-be-replaced-individually)
- [Container safety does not make compound operations atomic](09-cpython-concurrency-model.md#container-safety-does-not-make-compound-operations-atomic)
- [Direct field access bypasses API synchronization](09-cpython-concurrency-model.md#direct-field-access-bypasses-api-synchronization)
- [Borrowed references need renewed scrutiny](09-cpython-concurrency-model.md#borrowed-references-need-renewed-scrutiny)
- [Reference counting is concurrency-aware](09-cpython-concurrency-model.md#reference-counting-is-concurrency-aware)
- [Extension state may now be genuinely shared](09-cpython-concurrency-model.md#extension-state-may-now-be-genuinely-shared)

### 10. [`PyMutex`](10-pymutex.md)

Explains the concrete mutex API, initialization and address requirements, waiting behavior, diagnostics, and callback hazards.

- [Store the mutex beside the state it protects](10-pymutex.md#store-the-mutex-beside-the-state-it-protects)
- [A `PyMutex` has a stable address](10-pymutex.md#a-pymutex-has-a-stable-address)
- [Lock and unlock delimit the invariant](10-pymutex.md#lock-and-unlock-delimit-the-invariant)
- [Keep complete state transitions under one acquisition](10-pymutex.md#keep-complete-state-transitions-under-one-acquisition)
- [Waiting temporarily detaches the thread state](10-pymutex.md#waiting-temporarily-detaches-the-thread-state)
- [The implementation has fast and parked paths](10-pymutex.md#the-implementation-has-fast-and-parked-paths)
- [`PyMutex` is not recursive](10-pymutex.md#pymutex-is-not-recursive)
- [`PyMutex_IsLocked()` is only diagnostic](10-pymutex.md#pymutex_islocked-is-only-diagnostic)
- [Unlock exactly once on every path](10-pymutex.md#unlock-exactly-once-on-every-path)
- [Define a lock order for multiple mutexes](10-pymutex.md#define-a-lock-order-for-multiple-mutexes)
- [Avoid arbitrary Python execution while holding a direct mutex](10-pymutex.md#avoid-arbitrary-python-execution-while-holding-a-direct-mutex)
- [Do not lock `ob_mutex` directly](10-pymutex.md#do-not-lock-ob_mutex-directly)
- [Choose direct locking when the lock must stay held](10-pymutex.md#choose-direct-locking-when-the-lock-must-stay-held)

### 11. [CPython critical sections](11-cpython-critical-sections.md)

Explains suspend-and-resume locking, lexical pairing, nesting and recursion, build contracts, and object/mutex-backed APIs.

- [Use critical sections for Python object state](11-cpython-critical-sections.md#use-critical-sections-for-python-object-state)
- [The macros form a lexical block](11-cpython-critical-sections.md#the-macros-form-a-lexical-block)
- [Each thread has a stack of critical sections](11-cpython-critical-sections.md#each-thread-has-a-stack-of-critical-sections)
- [Detachment suspends all active sections](11-cpython-critical-sections.md#detachment-suspends-all-active-sections)
- [Restore invariants before any possible suspension](11-cpython-critical-sections.md#restore-invariants-before-any-possible-suspension)
- [Reacquisition does not restore old facts](11-cpython-critical-sections.md#reacquisition-does-not-restore-old-facts)
- [Nested single-object sections do not lock two objects reliably](11-cpython-critical-sections.md#nested-single-object-sections-do-not-lock-two-objects-reliably)
- [At most two object locks are supported](11-cpython-critical-sections.md#at-most-two-object-locks-are-supported)
- [Recursive entry avoids deadlock but can release outer locks](11-cpython-critical-sections.md#recursive-entry-avoids-deadlock-but-can-release-outer-locks)
- [Object locks exclude only cooperating operations](11-cpython-critical-sections.md#object-locks-exclude-only-cooperating-operations)
- [Built-in APIs usually manage their own locking](11-cpython-critical-sections.md#built-in-apis-usually-manage-their-own-locking)
- [Use critical sections to acquire `ob_mutex`](11-cpython-critical-sections.md#use-critical-sections-to-acquire-ob_mutex)
- [Mutex-backed critical sections support non-object state](11-cpython-critical-sections.md#mutex-backed-critical-sections-support-non-object-state)
- [Critical sections are no-ops in the default build](11-cpython-critical-sections.md#critical-sections-are-no-ops-in-the-default-build)
- [Recognize CPython's generated code and internal helpers](11-cpython-critical-sections.md#recognize-cpythons-generated-code-and-internal-helpers)
- [Choose between a direct mutex and a critical section](11-cpython-critical-sections.md#choose-between-a-direct-mutex-and-a-critical-section)

### 12. [Stop-the-world](12-stop-the-world.md)

Explains pause scopes, thread-state transitions, rare global updates, and the hazards of locks and arbitrary code during a pause.

- [A pause can cover one interpreter or the runtime](12-stop-the-world.md#a-pause-can-cover-one-interpreter-or-the-runtime)
- [Attached threads stop at safe points](12-stop-the-world.md#attached-threads-stop-at-safe-points)
- [A pause provides a global exclusion point](12-stop-the-world.md#a-pause-provides-a-global-exclusion-point)
- [Prepare before stopping, but read changing state afterward](12-stop-the-world.md#prepare-before-stopping-but-read-changing-state-afterward)
- [Do not wait for locks while threads are suspended](12-stop-the-world.md#do-not-wait-for-locks-while-threads-are-suspended)
- [Do not run arbitrary Python code while stopped](12-stop-the-world.md#do-not-run-arbitrary-python-code-while-stopped)
- [Garbage-collection state is not proof of a pause](12-stop-the-world.md#garbage-collection-state-is-not-proof-of-a-pause)
- [Stop-the-world has a broad performance cost](12-stop-the-world.md#stop-the-world-has-a-broad-performance-cost)
- [Choose a narrower mechanism when possible](12-stop-the-world.md#choose-a-narrower-mechanism-when-possible)

### 13. [QSBR in CPython](13-qsbr-in-cpython.md)

Explains CPython's reader obligations, sequences, delayed-work helpers, lifecycle and retention costs, and specialized allocator reuse.

- [QSBR complements reference counting](13-qsbr-in-cpython.md#qsbr-complements-reference-counting)
- [A quiescent state is a promise from one thread](13-qsbr-in-cpython.md#a-quiescent-state-is-a-promise-from-one-thread)
- [CPython tracks one write sequence per interpreter](13-qsbr-in-cpython.md#cpython-tracks-one-write-sequence-per-interpreter)
- [Retirement follows a fixed sequence](13-qsbr-in-cpython.md#retirement-follows-a-fixed-sequence)
- [Delayed frees and decrefs connect lifetime to QSBR](13-qsbr-in-cpython.md#delayed-frees-and-decrefs-connect-lifetime-to-qsbr)
- [Sequence advancement can be deferred](13-qsbr-in-cpython.md#sequence-advancement-can-be-deferred)
- [Attached and detached states affect grace periods](13-qsbr-in-cpython.md#attached-and-detached-states-affect-grace-periods)
- [A delayed thread can retain much memory](13-qsbr-in-cpython.md#a-delayed-thread-can-retain-much-memory)
- [Allocator reuse is part of the lifetime problem](13-qsbr-in-cpython.md#allocator-reuse-is-part-of-the-lifetime-problem)
- [QSBR does not provide publication ordering by itself](13-qsbr-in-cpython.md#qsbr-does-not-provide-publication-ordering-by-itself)
- [QSBR is useful for read-mostly internal storage](13-qsbr-in-cpython.md#qsbr-is-useful-for-read-mostly-internal-storage)

### 14. [Choosing a technique](14-choosing-a-technique.md)

Provides the decision order, important qualifications, combined-protocol example, and final review checklist.

- [A practical decision order](14-choosing-a-technique.md#a-practical-decision-order)
- [Check the qualifications before choosing](14-choosing-a-technique.md#check-the-qualifications-before-choosing)
  - [Removing sharing needs an ownership rule](14-choosing-a-technique.md#removing-sharing-needs-an-ownership-rule)
  - [A critical section may release its locks](14-choosing-a-technique.md#a-critical-section-may-release-its-locks)
  - [Atomic operations must match the whole operation](14-choosing-a-technique.md#atomic-operations-must-match-the-whole-operation)
  - [Internal mechanisms have restricted scopes](14-choosing-a-technique.md#internal-mechanisms-have-restricted-scopes)
- [Keep ordering and lifetime as separate checks](14-choosing-a-technique.md#keep-ordering-and-lifetime-as-separate-checks)
- [Give each mechanism one explicit job](14-choosing-a-technique.md#give-each-mechanism-one-explicit-job)
- [Review the complete protocol](14-choosing-a-technique.md#review-the-complete-protocol)
