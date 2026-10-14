# Python asyncio --- Quick Reference / Learning Spec

> **Purpose:** Quick lookup for Python `asyncio` syntax and concepts,
> especially for developers coming from JavaScript.

------------------------------------------------------------------------

## 1. Mental Model

`asyncio` is Python's system for **asynchronous/concurrent I/O work**.

Think of it as the Python equivalent of the JavaScript async/event-loop
model.

The key idea:

``` text
Start async operation
        ↓
operation is waiting for I/O
        ↓
event loop runs other async work
        ↓
operation becomes ready
        ↓
resume the original coroutine
```

### Best suited for

-   HTTP/API calls
-   Database queries
-   Network operations
-   WebSockets
-   Waiting for external services
-   Other I/O-bound work

### Not primarily for

-   Heavy CPU calculations
-   Large loops doing computation
-   CPU-intensive image/video processing

For CPU-heavy work, consider multiprocessing / process pools instead.

------------------------------------------------------------------------

# 2. JavaScript → Python Mapping

  JavaScript                        Python
  --------------------------------- ----------------------------
  `async function foo()`            `async def foo():`
  `await foo()`                     `await foo()`
  `Promise.all([...])`              `asyncio.gather(...)`
  `setTimeout` wrapped in Promise   `await asyncio.sleep(...)`
  Promise                           Coroutine / awaitable
  Event Loop                        `asyncio` event loop
  Start async program               `asyncio.run(main())`
  Schedule async work               `asyncio.create_task(...)`

------------------------------------------------------------------------

# 3. `async def`

Defines an asynchronous function (coroutine function).

``` python
async def hello():
    print("Hello")
```

Calling it:

``` python
hello()
```

does **not** execute it like a normal function.

It creates a coroutine that needs to be awaited/scheduled.

``` python
await hello()
```

or:

``` python
asyncio.create_task(hello())
```

------------------------------------------------------------------------

# 4. `await`

`await` waits for an asynchronous operation.

``` python
async def get_data():
    result = await fetch_data()
    return result
```

Important mental model:

> `await` pauses the current coroutine and allows the event loop to run
> other async work while the awaited operation is waiting.

You can only use `await` inside an `async def` function.

``` python
async def main():
    await something()
```

------------------------------------------------------------------------

# 5. Starting an Async Program

Typical Python entry point:

``` python
import asyncio

async def main():
    print("Hello")

asyncio.run(main())
```

Think:

``` text
normal Python
     ↓
asyncio.run()
     ↓
event loop
     ↓
main()
     ↓
await / tasks / gather
```

JavaScript usually manages the event loop for you through the runtime.
Python commonly starts it explicitly with `asyncio.run()`.

------------------------------------------------------------------------

# 6. `asyncio.sleep()`

Async equivalent of waiting without blocking the event loop.

``` python
import asyncio

async def test():
    print("Start")

    await asyncio.sleep(3)

    print("End")

asyncio.run(test())
```

### DON'T do this inside async code

``` python
import time

time.sleep(3)
```

`time.sleep()` blocks the thread.

### Prefer

``` python
await asyncio.sleep(3)
```

This allows other async tasks to run.

------------------------------------------------------------------------

# 7. Sequential vs Concurrent

## Sequential

``` python
async def main():
    user = await fetch_user()
    movies = await fetch_movies()
```

Execution:

``` text
fetch_user
    ↓ wait
done

fetch_movies
    ↓ wait
done
```

If each takes 2 seconds:

``` text
2 + 2 = 4 seconds
```

------------------------------------------------------------------------

## Concurrent with `gather()`

``` python
async def main():
    user, movies = await asyncio.gather(
        fetch_user(),
        fetch_movies()
    )
```

Execution:

``` text
fetch_user ──────────┐
                     ├──→ results
fetch_movies ────────┘
```

If each takes 2 seconds:

``` text
max(2, 2) = 2 seconds
```

### JavaScript equivalent

``` javascript
const [user, movies] = await Promise.all([
    fetchUser(),
    fetchMovies()
]);
```

------------------------------------------------------------------------

# 8. `asyncio.gather()`

Use when multiple independent async operations can happen concurrently.

``` python
results = await asyncio.gather(
    operation1(),
    operation2(),
    operation3()
)
```

Example:

``` python
user, movies, channels = await asyncio.gather(
    fetch_user(),
    fetch_movies(),
    fetch_channels()
)
```

The results are returned in the **same order as the inputs**.

``` python
a, b, c = await asyncio.gather(
    task_a(),
    task_b(),
    task_c()
)
```

Even if `task_c()` finishes first, `a`, `b`, and `c` still correspond to
A, B, and C.

------------------------------------------------------------------------

# 9. `asyncio.create_task()`

Use `create_task()` when you want to explicitly schedule a coroutine to
run concurrently.

``` python
async def main():

    user_task = asyncio.create_task(fetch_user())
    movies_task = asyncio.create_task(fetch_movies())

    user = await user_task
    movies = await movies_task
```

Important:

``` python
task = asyncio.create_task(coroutine())
```

means:

> Schedule this coroutine to run as an asyncio Task.

It does not mean a new CPU thread/process is created.

------------------------------------------------------------------------

# 10. `gather()` vs `create_task()`

### `gather()`

Best when you simply want:

> "Run these operations concurrently and give me all their results."

``` python
results = await asyncio.gather(
    fetch_a(),
    fetch_b(),
    fetch_c()
)
```

### `create_task()`

Useful when you want to start something now and await it later.

``` python
task = asyncio.create_task(fetch_data())

# Do other async work

result = await task
```

------------------------------------------------------------------------

# 11. Realistic API Example

Suppose an application needs:

``` text
1. User profile
2. Subscription
3. Recommendations
4. Channels
```

Sequential:

``` python
async def main():
    profile = await get_profile()
    subscription = await get_subscription()
    recommendations = await get_recommendations()
    channels = await get_channels()
```

If each takes \~1 second:

``` text
1 + 1 + 1 + 1 = ~4 seconds
```

Concurrent:

``` python
async def main():
    profile, subscription, recommendations, channels = await asyncio.gather(
        get_profile(),
        get_subscription(),
        get_recommendations(),
        get_channels()
    )
```

Approximately:

``` text
max(1, 1, 1, 1) = ~1 second
```

This is one of the main reasons to use asyncio.

------------------------------------------------------------------------

# 12. Complete Basic Example

``` python
import asyncio


async def fetch_user():
    print("Fetching user...")
    await asyncio.sleep(2)
    return "User"


async def fetch_movies():
    print("Fetching movies...")
    await asyncio.sleep(3)
    return "Movies"


async def main():
    user, movies = await asyncio.gather(
        fetch_user(),
        fetch_movies()
    )

    print(user)
    print(movies)


asyncio.run(main())
```

Expected behavior:

``` text
Fetching user...
Fetching movies...

(wait ~3 seconds)

User
Movies
```

------------------------------------------------------------------------

# 13. What Actually Happens in the Event Loop?

Suppose:

``` python
async def task_a():
    await asyncio.sleep(3)

async def task_b():
    await asyncio.sleep(1)
```

When both are scheduled:

``` text
                 Event Loop
                     |
             ┌───────┴───────┐
             ↓               ↓
           Task A          Task B
             |               |
           await           await
          3 seconds        1 second
             |               |
             |          Task B resumes
             |
        Task A resumes
```

The event loop can switch between tasks when they reach an `await`
point.

This is called **cooperative concurrency**.

------------------------------------------------------------------------

# 14. Important: Asyncio ≠ Parallelism

`asyncio` is primarily about **concurrency**, not automatically running
code on multiple CPU cores.

Think of a waiter:

``` text
Take order A
   ↓
Kitchen is preparing A
   ↓
Take order B
   ↓
Kitchen is preparing B
   ↓
Serve A
   ↓
Serve B
```

The waiter doesn't stand around waiting for the kitchen.

Likewise, an asyncio event loop can work on other async tasks while one
task is waiting for I/O.

------------------------------------------------------------------------

# 15. Coroutine vs Task

### Coroutine

Created by calling an async function:

``` python
coro = fetch_user()
```

This represents async work that can be awaited/scheduled.

### Task

A coroutine scheduled on the event loop:

``` python
task = asyncio.create_task(fetch_user())
```

Simple mental model:

``` text
async def fetch_user()
        ↓
coroutine
        ↓
asyncio.create_task()
        ↓
Task scheduled on event loop
```

------------------------------------------------------------------------

# 16. Common Pattern: Multiple API Calls

``` python
async def load_dashboard():
    profile, orders, recommendations = await asyncio.gather(
        get_profile(),
        get_orders(),
        get_recommendations()
    )

    return {
        "profile": profile,
        "orders": orders,
        "recommendations": recommendations,
    }
```

Use this when the operations are independent.

------------------------------------------------------------------------

# 17. When NOT to Use `gather()`

If operation B depends on operation A:

``` python
user = await get_user()

orders = await get_orders(user["id"])
```

You cannot meaningfully start both at the same time because B needs A's
result.

Use concurrency only when operations are independent.

------------------------------------------------------------------------

# 18. Common Mistake #1 --- Forgetting `await`

Wrong:

``` python
async def main():
    result = fetch_user()
    print(result)
```

`result` is a coroutine object, not the actual result.

Correct:

``` python
async def main():
    result = await fetch_user()
```

Or schedule it:

``` python
task = asyncio.create_task(fetch_user())
result = await task
```

------------------------------------------------------------------------

# 19. Common Mistake #2 --- Blocking the Event Loop

Bad:

``` python
async def main():
    time.sleep(5)
```

This blocks the event loop.

Better:

``` python
async def main():
    await asyncio.sleep(5)
```

The same principle applies to blocking libraries.

If a library performs synchronous/blocking I/O, it can block your async
application even if called from an `async def`.

------------------------------------------------------------------------

# 20. Common Mistake #3 --- Assuming `async def` Automatically Runs Concurrently

This:

``` python
async def main():
    await task_a()
    await task_b()
```

is sequential.

To run independent tasks concurrently:

``` python
async def main():
    await asyncio.gather(
        task_a(),
        task_b()
    )
```

------------------------------------------------------------------------

# 21. Error Handling with `gather()`

Normal:

``` python
try:
    results = await asyncio.gather(
        task_a(),
        task_b()
    )
except Exception as e:
    print(e)
```

If you want exceptions returned as results instead of immediately being
raised:

``` python
results = await asyncio.gather(
    task_a(),
    task_b(),
    return_exceptions=True
)
```

Then inspect the results.

``` python
for result in results:
    if isinstance(result, Exception):
        print("Failed:", result)
```

------------------------------------------------------------------------

# 22. `asyncio` Quick Syntax Sheet

### Import

``` python
import asyncio
```

### Async function

``` python
async def foo():
    ...
```

### Await

``` python
result = await foo()
```

### Start program

``` python
asyncio.run(main())
```

### Async sleep

``` python
await asyncio.sleep(2)
```

### Concurrent operations

``` python
results = await asyncio.gather(
    foo(),
    bar(),
    baz()
)
```

### Create task

``` python
task = asyncio.create_task(foo())
```

### Wait for task

``` python
result = await task
```

### Error handling

``` python
try:
    result = await foo()
except Exception as e:
    print(e)
```

------------------------------------------------------------------------

# 23. One-Line Mental Models

``` text
async def
→ "This function can perform async operations."

await
→ "Pause this coroutine until this async operation is ready; let other async work run."

asyncio.run()
→ "Start the event loop and run my async program."

asyncio.gather()
→ "Run independent async operations concurrently and wait for all of them."

asyncio.create_task()
→ "Schedule this coroutine as a Task so it can run concurrently."

asyncio.sleep()
→ "Wait without blocking the event loop."

asyncio
→ "Useful mainly for I/O-bound concurrency."
```

------------------------------------------------------------------------

# 24. JavaScript Developer Cheat Sheet

### JS

``` javascript
async function getUser() {
    const response = await fetch("/user");
    return response.json();
}
```

### Python conceptually

``` python
async def get_user():
    response = await fetch("/user")
    return await response.json()
```

------------------------------------------------------------------------

### JS

``` javascript
const [user, movies] = await Promise.all([
    getUser(),
    getMovies()
]);
```

### Python

``` python
user, movies = await asyncio.gather(
    get_user(),
    get_movies()
)
```

------------------------------------------------------------------------

### JS

``` javascript
setTimeout(...);
```

### Python

``` python
await asyncio.sleep(...)
```

------------------------------------------------------------------------

### JS mental model

``` text
Promise
  ↓
Event Loop
  ↓
async/await
```

### Python mental model

``` text
Coroutine
  ↓
asyncio Event Loop
  ↓
async/await
```

------------------------------------------------------------------------

# 25. Recommended Learning Order

Learn these in this order:

``` text
1. async def
      ↓
2. await
      ↓
3. asyncio.run()
      ↓
4. asyncio.sleep()
      ↓
5. Sequential vs concurrent execution
      ↓
6. asyncio.gather()
      ↓
7. asyncio.create_task()
      ↓
8. Exceptions
      ↓
9. Task cancellation
      ↓
10. asyncio.Queue
      ↓
11. Semaphores
      ↓
12. Real HTTP clients (httpx / aiohttp)
```

You don't need to memorize everything.

For day-to-day reference, the most important four are:

``` python
async def foo():
    ...

await foo()

asyncio.run(main())

await asyncio.gather(
    foo(),
    bar()
)
```

------------------------------------------------------------------------

# 26. Tiny Practice Exercises

### Exercise 1

Create an async function that:

``` text
prints "Start"
waits 2 seconds
prints "End"
```

------------------------------------------------------------------------

### Exercise 2

Create two async functions:

``` text
task A → waits 3 seconds
task B → waits 1 second
```

Run them sequentially and measure the time.

Then run them with `asyncio.gather()`.

Observe the difference.

------------------------------------------------------------------------

### Exercise 3

Create:

``` python
fetch_user()
fetch_movies()
fetch_channels()
```

Make each sleep for a different amount of time.

Run all three concurrently using:

``` python
asyncio.gather()
```

------------------------------------------------------------------------

### Exercise 4

Use `asyncio.create_task()`:

``` python
task = asyncio.create_task(fetch_user())

# do something else

user = await task
```

Observe when `fetch_user()` actually starts and finishes.

------------------------------------------------------------------------

# 27. The Core Rule

When deciding whether asyncio is useful, ask:

> **"Am I mostly waiting for something external, or am I mostly
> calculating?"**

If you're mostly waiting:

``` text
HTTP
DB
Network
WebSocket
External service
     ↓
asyncio can be useful
```

If you're mostly calculating:

``` text
CPU-heavy loop
Image processing
Large computation
     ↓
asyncio alone is usually NOT the answer
```

------------------------------------------------------------------------

# 28. Final Cheat Sheet

``` text
┌────────────────────────────────────────────┐
│             PYTHON ASYNCIO                 │
├────────────────────────────────────────────┤
│ async def       → define async function    │
│ await           → wait without blocking    │
│ asyncio.run()   → start async program      │
│ gather()        → run independent work     │
│ create_task()   → schedule async task      │
│ sleep()         → non-blocking wait        │
├────────────────────────────────────────────┤
│ Best for: I/O-bound concurrent work        │
│ Not a replacement for CPU parallelism      │
└────────────────────────────────────────────┘
```

## Most important JS comparison

``` text
JavaScript                 Python
──────────────────────────────────────────
async function             async def
await                      await
Promise.all()              asyncio.gather()
Promise                    coroutine/awaitable
Event Loop                 asyncio event loop
```

**If you remember only one thing:**

``` python
await asyncio.gather(
    api_call_1(),
    api_call_2(),
    api_call_3()
)
```

is conceptually:

``` javascript
await Promise.all([
    apiCall1(),
    apiCall2(),
    apiCall3()
]);
```

That is the core of asyncio.
