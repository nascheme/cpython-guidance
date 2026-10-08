# The basic problem: shared mutable memory

Concurrent programs do more than one thing at a time. For example, two threads may run at the same time. Their operations can overlap, and the operating system may pause either thread between any two operations.

Concurrency becomes difficult when the threads share **mutable memory**. This is memory that one thread can change while another thread can access it.

Memory that is not shared does not have this problem. Immutable memory is also simpler because no thread changes it after it is safely published. Publication still needs synchronization so that other threads can safely read the initialized memory. Shared mutable memory needs a clear synchronization rule.

Do not assume that an immutable Python object is entirely immutable C memory. CPython still updates reference counts, GC state, and some caches. For example, `str` and `tuple` lazily cache their hashes. Free-threaded builds use atomic accesses for those hash caches. Use the runtime APIs for fields managed by CPython. If you add a mutable field to an otherwise immutable type, that field needs its own synchronization rule.

## A simple shared variable

Consider an ordinary C variable:

```c
static int value = 0;
```

One thread writes to it:

```c
value = 1;
```

At the same time, another thread reads it:

```c
int seen = value;
```

The read and write **conflict**. Two memory accesses conflict when they access the same location and at least one of them writes to it.

The source code does not say which access must happen first. There is no mutex, atomic operation, or other synchronization between the threads. This is a **data race** in C.

A C data race is not just a chance that the reader will see an old value. A data race on an ordinary, non-atomic C object gives the program undefined behavior. The [next chapter](02-the-c-abstract-machine-and-undefined-behavior.md) explains what that means and why the compiler matters.

## Data races and race conditions are different

The terms *data race* and *race condition* are sometimes used as if they mean the same thing. This document uses them for different problems.

A **data race** has a specific meaning in the C memory model. It occurs when:

- two threads access the same memory location;
- at least one access is a write;
- at least one access is non-atomic; and
- synchronization does not order one access before the other.

The formal name for the required ordering is **happens-before**. A later section defines it in detail.

A **race condition** is a broader program bug. The result depends on which thread wins a race. A program can have a race condition even when every individual memory access is protected by a mutex or uses an atomic operation.

For example, suppose `remaining` is a shared item count that starts at a non-negative value. The mutex `lock` protects it. Every reader and writer holds that same mutex:

```c
bool
take_one(void)
{
    bool available;

    lock_mutex(&lock);
    available = (remaining > 0);
    unlock_mutex(&lock);

    if (!available) {
        return false;
    }

    lock_mutex(&lock);
    remaining--;
    unlock_mutex(&lock);
    return true;
}
```

There is no data race on `remaining`. Each access holds the mutex. However, the function still has a race condition.

If `remaining` starts at 1, two threads can both observe that an item is available. Both can then decrement it. The final value is -1.

The check and the decrement form one logical operation. The mutex must protect that complete operation:

```c
bool
take_one(void)
{
    lock_mutex(&lock);
    if (remaining == 0) {
        unlock_mutex(&lock);
        return false;
    }
    remaining--;
    unlock_mutex(&lock);
    return true;
}
```

This distinction is important:

- Preventing data races removes a source of undefined behavior.
- Preventing race conditions makes the program's behavior correct.

A program needs both.

## Shared state is often larger than one variable

Real code rarely has only one shared integer. Several fields may describe one logical state.

For example, a structure may contain a pointer and a flag that says the pointer is ready:

```c
struct shared_result {
    PyObject *result;
    int ready;
};
```

A writer might set `result` and then set `ready`. A reader might check `ready` and then use `result`.

The two fields are related. It is not enough to ask whether each load or store is indivisible. The program must also ensure that a reader which observes `ready` can safely observe and use the matching `result`.

This is one reason synchronization protects **state and its rules**, not just individual variables. Start with a lock that protects both `result` and `ready`. Every reader and writer must use that same lock. Keep the reader's check of `ready` and use of `result` together under the lock.

In CPython, prefer a critical section for per-object state or a `PyMutex` for independently owned shared state. Atomic operations can also publish state, but they need the correct memory ordering. Consider them when measured performance justifies the extra complexity. Later sections explain these approaches.

## Pointer access and object lifetime are separate problems

Pointers add another question. Consider this code:

```c
PyObject *obj = shared->obj;
use_object(obj);
```

The code must answer two separate questions:

1. Is reading `shared->obj` safe while another thread might change it?
2. After the pointer is read, what keeps `obj` alive until `use_object()` finishes?

Making the pointer access atomic would address only the first question. It would not, by itself, stop another thread from destroying the object.

This distinction appears often in CPython. Locks, reference counts, borrowed references, and safe memory reclamation can all affect the answer. Later sections return to this example.

## Start by identifying the shared state

Before choosing a mutex or an atomic operation, write down what is shared. For each piece of mutable state, ask:

- Which threads can access it?
- Which accesses read it?
- Which accesses change it?
- Which object's lock or other synchronization rule protects each field?
- Which fields must agree with each other?
- Which checks and updates form one logical operation?
- What keeps referenced objects alive while they are in use?

The answers define the synchronization problem. The rest of this document explains the C rules and the CPython tools used to solve it.

---

Next: [The C abstract machine and undefined behavior](02-the-c-abstract-machine-and-undefined-behavior.md)
