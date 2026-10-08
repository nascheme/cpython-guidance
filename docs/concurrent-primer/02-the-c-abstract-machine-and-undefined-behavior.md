# The C abstract machine and undefined behavior

A C program does not directly describe CPU instructions. It describes operations in the **C abstract machine**. The C standard defines the rules of this machine.

A compiler translates those operations for a real machine. It may combine, remove, or reorder operations during translation. The compiler must preserve the behavior that the C standard requires. It does not have to preserve every step suggested by the source code.

Concurrent C code must therefore follow the C rules. It is not enough to know how a particular CPU usually behaves.

## The compiler does not execute the source literally

Consider a function that reads an ordinary variable twice:

```c
static int value;

int
sum_twice(void)
{
    return value + value;
}
```

The source contains two reads of `value`. The compiler may generate one load and use its result twice. This transformation is valid when it does not change the behavior of a valid C program.

The same principle applies to more complex code. A compiler may:

- keep a value in a register instead of loading it again;
- remove a store whose value is never used;
- combine several operations into one;
- split one source operation into several instructions; or
- move operations when the required behavior stays the same.

This freedom is called the **as-if rule**. The compiler can transform the program as if it had followed the abstract machine, as long as it preserves the observable behavior required by C.

This is why reading generated machine code is useful but not enough. Different compiler versions, options, or surrounding code can produce different instructions from the same source.

## Undefined behavior removes the normal requirements

Some C operations have **undefined behavior**. When an execution has undefined behavior, the C standard places no requirements on that execution.

Undefined behavior is not a special value or a predictable failure mode. It does not mean that the program must crash. A program might appear to work during testing and fail after a compiler update. It might also fail only when surrounding code changes.

The compiler does not need to prove that undefined behavior will occur at run time. It may reason that valid programs do not perform undefined operations. Optimizations can then use that assumption.

Common examples include accessing an object after its lifetime ends, overflowing a signed integer, and accessing an array outside its bounds. For concurrent code, the central example is a data race.

## An ordinary C data race is undefined behavior

Recall the shared variable from the previous section:

```c
static int value;
```

If one thread writes `value` while another thread reads or writes it, the accesses conflict. If synchronization does not order the accesses, the program has a data race.

The [previous chapter](01-shared-mutable-memory.md#data-races-and-race-conditions-are-different) lists the conditions for a data race. The meaning of *memory location* needs one further qualification.

A **memory location** is a scalar object or a maximal sequence of adjacent non-zero-width bit-fields. Separate scalar struct members are separate locations. Adjacent bit-fields belong to one location, so two threads writing different fields in that sequence can race. A zero-width bit-field separates such sequences.

A field that needs atomic loads and stores should be a separately addressable scalar, not a bit-field. For example, `PyASCIIObject.state.interned` is a two-bit field in the default GIL-enabled build (`Py_GIL_DISABLED` is not defined). It is an `unsigned char` in the free-threaded build (`Py_GIL_DISABLED` is defined) so it can be accessed atomically. This layout choice depends on the build, not on whether the GIL is enabled at run time.

A data race gives the program undefined behavior. It is not valid to reason that the reader must see either the old value or the new value. C provides that kind of guarantee only when the program uses the required synchronization and atomic operations.

This rule applies even if the source operation happens to become one machine instruction. The compiler processes the C program before the CPU runs it.

## Hardware atomicity is not C atomicity

AMD64, also called x86-64, provides strong memory-ordering guarantees compared with many other CPUs. An aligned load or store of a machine-sized value is also indivisible in many common cases.

Neither fact makes an ordinary C data race valid.

ARM64 has a weaker hardware memory model. It permits more kinds of reordering unless the program uses suitable instructions. This can expose bugs that were hard to observe on AMD64.

Correct C code should not depend on either architecture's accidental behavior. C atomic operations and synchronization primitives tell the compiler what the program requires. The compiler then selects instructions that meet those requirements on the target CPU. An operation may need no extra ordering instruction on AMD64 but need a special instruction on ARM64.

A later section compares these hardware models in more detail. The rule for now is simple:

> Write against the C memory model, not against the behavior you expect from one CPU.

## `volatile` does not provide synchronization

Adding `volatile` does not fix a data race:

```c
static volatile int done;
```

`volatile` tells the compiler that accesses to this object are observable and must be performed according to the rules for volatile objects. It is useful for purposes such as some forms of memory-mapped input and output.

It does not make an access atomic. It does not create a happens-before relationship between threads. It does not provide the ordering required to publish other data.

For example, this code still has a data race:

```c
static volatile int done;

/* Thread 1 */
done = 1;

/* Thread 2 */
if (done) {
    use_result();
}
```

Both threads access `done`, one access is a write, and the accesses are not atomic or ordered by synchronization. The `volatile` qualifier does not change that.

Use a synchronization primitive when threads communicate through memory. Atomic operations are an alternative when the complete protocol justifies them.

The statements above describe ISO C. Some compilers give `volatile` extra guarantees as an extension. For example, MSVC's `/volatile:ms` mode gives volatile loads acquire semantics and volatile stores release semantics. CPython's MSVC atomic implementation uses compiler-specific guarantees internally. Outside those wrappers, use locks or the appropriate `_Py_atomic_*` operations, not `volatile` casts. Those casts do not provide portable synchronization.

## Source order alone does not synchronize threads

Suppose a writer stores a result and then sets a flag:

```c
shared->result = result;
shared->ready = 1;
```

A reader checks the flag before reading the result:

```c
if (shared->ready) {
    use_object(shared->result);
}
```

The order of statements in the writer does not, by itself, order the writer's accesses with the reader's accesses. The code has data races on the shared fields.

It is misleading to describe this only as a possible compiler or CPU reordering bug. The source program is already invalid because it lacks synchronization. The fix is to establish the required C memory-model relationships. Preventing one observed reordering on one compiler would not be enough.

A mutex assigned to `shared` can protect both `shared->result` and `shared->ready`. Every reader and writer must hold that same mutex when accessing either field. The reader must keep its check of `ready` and its use of `result` together under the mutex.

Atomic release and acquire operations can also publish the result if the full protocol orders all conflicting accesses. [The next chapter](03-the-c-memory-model.md#publishing-data-with-release-and-acquire) explains that alternative.

## Object lifetime is also part of correctness

Removing the data race on a pointer does not automatically make the pointed-to object safe:

```c
PyObject *obj = load_shared_pointer();
use_object(obj);
```

The pointer load might be atomic or protected by a mutex. The program still has undefined behavior if another thread can destroy `obj` before `use_object()` finishes.

The program needs both safe access to the pointer and a rule that keeps the object alive. Loading the pointer and then calling `Py_INCREF(obj)` is not enough. Another thread could destroy the object between those two operations.

The [synchronization chapter](05-synchronization.md#locks-do-not-preserve-facts-after-unlock) explains how a mutex can protect reference acquisition. [Safe memory reclamation](08-safe-memory-reclamation.md) explains why unlocked readers need a separate lifetime protocol.

## Use a defined synchronization rule

For each shared mutable object, every conflicting access needs a defined ordering rule. Common choices are:

- protect per-object state with that object's critical section, or independently owned shared state with a `PyMutex`;
- keep state private to one thread; or
- use atomic operations with suitable memory ordering when performance justifies the extra protocol.

Include readers as well as writers in a locking rule. Later chapters explain how CPython's critical sections and `PyMutex` work.

Private construction does not make a later hand-off safe by itself. Transfer the object through synchronization, such as a mutex-protected queue or a correct release/acquire publication protocol. The construction stores must happen-before the receiving thread's reads. This is the same requirement illustrated in [source order alone does not synchronize threads](#source-order-alone-does-not-synchronize-threads).

Do not replace this rule with `volatile`, assumptions about generated instructions, or tests on one CPU. Once the C program has defined behavior, the compiler and platform are responsible for implementing its synchronization correctly.

---

Next: [The C memory model](03-the-c-memory-model.md)
