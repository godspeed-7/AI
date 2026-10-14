# ASYNCIO IN PYTHON — quick reference notes
#
#    1. Mental model          what it is · I/O-bound vs CPU-bound
#    2. async def & await     coroutines · asyncio.run()
#    3. asyncio.sleep()       why time.sleep() is wrong in async code
#    4. Sequential vs concurrent   the same work, timed
#    5. gather()              result order · error handling
#    6. create_task()         start now, await later · TaskGroup
#    7. Coroutine vs Task     which is which
#    8. Timeouts & limits     wait_for · Semaphore
#    9. Practice              try-it-yourself
#   10. Gotchas recap         every surprise from this file in one list
#
# How to read this file:
#   # →       what the line prints (under a block: what the block prints)
#   # ❌      the line would raise an error, so it is commented out
#   GOTCHA    surprising behaviour — search for "GOTCHA" to review them all
#   Timings are real, measured with time.perf_counter(). Sleeps are kept
#   short so the whole file runs in about 2 seconds.
#
# Coming from JavaScript (this is the fastest way in):
#   async function foo()        → async def foo():
#   await foo()                 → await foo()
#   Promise                     → coroutine / awaitable
#   Promise.all([a(), b()])     → await asyncio.gather(a(), b())
#   Promise.allSettled([...])   → gather(..., return_exceptions=True)
#   setTimeout in a Promise     → await asyncio.sleep(seconds)
#   the runtime starts the loop → you call asyncio.run(main())
#   (no real equivalent)        → asyncio.create_task(coro())

import asyncio
import time


# ======================================================================
# 1. MENTAL MODEL
# ======================================================================
# asyncio runs many WAITING operations at once, in a single thread.
# While one coroutine waits for I/O, the event loop runs another:
#
#   start an operation → it waits for I/O → the loop runs other work
#                      → the I/O is ready → that coroutine resumes
#
# Worth it when you are waiting on something else:
#   HTTP / API calls · database queries · sockets · reading files
#   → exactly the AI workload: 50 LLM calls that each take a second
#
# Not the tool when your CPU is the bottleneck:
#   big loops · image processing · training maths
#   → use multiprocessing / a process pool for those
#
# Concurrency is not parallelism. One waiter serving many tables, not
# many cooks: your code still runs on one thread, one line at a time.
# It just stops sitting idle while something else is slow.


# ======================================================================
# 2. ASYNC DEF & AWAIT
# ======================================================================
print("\n===== 2. ASYNC DEF & AWAIT =====")


async def greet():            # a coroutine FUNCTION
    print("hello")
    await asyncio.sleep(0.1)  # an await is where the loop may switch
    print("bye")


# GOTCHA: calling it does NOT run it — you get a coroutine object back
coro = greet()
print(type(coro).__name__)  # → coroutine
coro.close()  # never awaited → close it, or Python warns about it

# asyncio.run() starts the event loop, runs the coroutine, shuts down
asyncio.run(greet())
# → hello
#   bye

# `await` only works inside an async def:
#   await greet()   # ❌ SyntaxError: 'await' outside function
#
# And asyncio.run() is for the top level only — one per program.
# Inside a coroutine you just `await` things.


# ======================================================================
# 3. ASYNCIO.SLEEP() — AND WHAT NOT TO DO
# ======================================================================
print("\n===== 3. ASYNCIO.SLEEP() =====")


async def nap():
    print("napping")
    await asyncio.sleep(0.1)  # pauses THIS coroutine, frees the loop
    print("awake")


asyncio.run(nap())
# → napping
#   awake

# GOTCHA: time.sleep() inside a coroutine freezes the WHOLE event loop.
# Nothing else runs, which defeats the entire point:
#   async def bad_nap():
#       time.sleep(0.1)   # ❌ blocks every other task too
#
# The same goes for any blocking library. Async code needs async
# libraries: httpx or aiohttp instead of requests, asyncpg instead of
# psycopg2. Stuck with a blocking function? Hand it to a thread:
#   result = await asyncio.to_thread(blocking_function, arg)


# ======================================================================
# 4. SEQUENTIAL VS CONCURRENT
# ======================================================================
# The whole reason asyncio exists. Same two calls, timed both ways.
print("\n===== 4. SEQUENTIAL VS CONCURRENT =====")


async def fetch_user():
    await asyncio.sleep(0.3)  # pretend: an API call
    return "user"


async def fetch_movies():
    await asyncio.sleep(0.3)
    return "movies"


async def sequential():
    start = time.perf_counter()
    user = await fetch_user()      # wait for this to finish...
    movies = await fetch_movies()  # ...only then start this
    print(f"sequential: {user}, {movies} "
          f"in {time.perf_counter() - start:.1f}s")


async def concurrent():
    start = time.perf_counter()
    user, movies = await asyncio.gather(fetch_user(), fetch_movies())
    print(f"concurrent: {user}, {movies} "
          f"in {time.perf_counter() - start:.1f}s")


asyncio.run(sequential())  # → sequential: user, movies in 0.6s
asyncio.run(concurrent())  # → concurrent: user, movies in 0.3s
#   sequential → 0.3 + 0.3 = 0.6s
#   concurrent → max(0.3, 0.3) = 0.3s
#
# GOTCHA: two awaits in a row are SEQUENTIAL. Writing `async def` buys
# you nothing on its own — gather() or create_task() is what overlaps
# the waiting.


# ======================================================================
# 5. GATHER()
# ======================================================================
print("\n===== 5. GATHER() =====")


async def quick():
    await asyncio.sleep(0.1)
    return "quick"


async def slow():
    await asyncio.sleep(0.3)
    return "slow"


async def boom():
    await asyncio.sleep(0.1)
    raise ValueError("boom")


async def show_order():
    results = await asyncio.gather(slow(), quick())
    print(results)  # → ['slow', 'quick']


asyncio.run(show_order())
# Results come back in the order you PASSED them, never the order they
# finished — so unpacking stays predictable:
#   user, movies = await asyncio.gather(fetch_user(), fetch_movies())


async def one_fails():
    try:
        await asyncio.gather(quick(), boom())
    except ValueError as error:
        print(f"gather raised: {error}")  # → gather raised: boom


asyncio.run(one_fails())
# GOTCHA: the first exception is raised immediately and you lose the
# other results.


async def collect_failures():
    results = await asyncio.gather(quick(), boom(),
                                   return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            print(f"failed: {type(result).__name__}: {result}")
        else:
            print(f"ok: {result}")


asyncio.run(collect_failures())
# → ok: quick
#   failed: ValueError: boom
# return_exceptions=True hands you errors as values — JS allSettled.


# ======================================================================
# 6. CREATE_TASK()
# ======================================================================
# gather() when you want everything at once. create_task() when you
# want to start something now and pick up the result later.
print("\n===== 6. CREATE_TASK() =====")


async def start_early():
    start = time.perf_counter()
    task = asyncio.create_task(slow())  # starts running right away
    print("task scheduled, meanwhile doing other work")
    await asyncio.sleep(0.1)            # ...the other work
    result = await task                 # collect it when needed
    print(f"got {result} in {time.perf_counter() - start:.1f}s")


asyncio.run(start_early())
# → task scheduled, meanwhile doing other work
#   got slow in 0.3s
# 0.3s, not 0.4s — the sleep and the task overlapped.

# GOTCHA: create_task does NOT start a thread or a process. Same single
# thread, same event loop.
# GOTCHA: keep a reference to your task. If nothing holds it, it can be
# garbage-collected and quietly never finish.


# --- TaskGroup (Python 3.11+) — the modern gather ---------------------
async def with_task_group():
    async with asyncio.TaskGroup() as group:
        user_task = group.create_task(fetch_user())
        movie_task = group.create_task(fetch_movies())
    # leaving the block waits for every task in it
    print(user_task.result(), movie_task.result())  # → user movies


asyncio.run(with_task_group())
# Prefer TaskGroup for new code: if one task fails it cancels the rest
# and raises, instead of leaving half-finished work behind.


# ======================================================================
# 7. COROUTINE VS TASK
# ======================================================================
#   async def fetch_user          → a coroutine FUNCTION
#   fetch_user()                  → a coroutine OBJECT (nothing runs)
#   asyncio.create_task(coro)     → a TASK, already running on the loop
#   await task                    → its result
print("\n===== 7. COROUTINE VS TASK =====")


async def show_types():
    coro = fetch_user()
    task = asyncio.create_task(fetch_movies())
    print(type(coro).__name__, "vs", type(task).__name__)
    # → coroutine vs Task
    print(await coro, await task)  # → user movies


asyncio.run(show_types())


# ======================================================================
# 8. TIMEOUTS & LIMITS
# ======================================================================
print("\n===== 8. TIMEOUTS & LIMITS =====")


async def too_slow():
    await asyncio.sleep(5)


async def with_timeout():
    try:
        await asyncio.wait_for(too_slow(), timeout=0.2)
    except TimeoutError:  # Python 3.11+: the plain built-in one
        print("gave up after 0.2s")  # → gave up after 0.2s


asyncio.run(with_timeout())
# The slow coroutine is cancelled for you. Always put a timeout on a
# network call — otherwise one hung request hangs your program.


async def call_api(index, limit):
    async with limit:  # waits here while the limit is full
        await asyncio.sleep(0.1)
        return index


async def rate_limited():
    limit = asyncio.Semaphore(2)  # at most 2 calls in flight
    start = time.perf_counter()
    results = await asyncio.gather(
        *(call_api(i, limit) for i in range(6))  # * unpacks (file 4)
    )
    print(results, f"in {time.perf_counter() - start:.1f}s")


asyncio.run(rate_limited())
# → [0, 1, 2, 3, 4, 5] in 0.3s
# 6 calls, 2 at a time → 3 rounds of 0.1s. This is how you stay inside
# an API rate limit and still run concurrently.


# ======================================================================
# 9. PRACTICE
# ======================================================================
# Try it yourself:
#   a) An async function that prints "Start", waits 1 second, prints
#      "End". Run it with asyncio.run().
#   b) Two coroutines sleeping 1s and 2s. Time them sequentially, then
#      with gather(). Confirm 3s becomes 2s.
#   c) fetch_user / fetch_movies / fetch_channels with different sleeps,
#      all three in one gather(), unpacked into three variables.
#   d) Start a task with create_task(), print something, then await it.
#      Add prints inside the coroutine to see when it really starts.
#   e) gather() three calls where the middle one raises. Handle it with
#      return_exceptions=True and print which one failed.
#   f) Wrap a 2-second coroutine in wait_for(..., timeout=0.5) and catch
#      the TimeoutError.


# ======================================================================
# 10. GOTCHAS RECAP
# ======================================================================
#  1. foo()                     returns a coroutine; nothing runs until
#                               you await it (Python warns if you don't)
#  2. await a(); await b()      sequential — use gather for concurrency
#  3. async def on its own      makes nothing faster
#  4. time.sleep()              blocks the whole loop → asyncio.sleep()
#  5. requests / psycopg2       blocking libraries block the loop too →
#                               httpx / aiohttp / asyncpg, or to_thread
#  6. await                     only inside an async def
#  7. asyncio.run()             top level only, once — never inside a
#                               coroutine
#  8. gather() results          input order, not completion order
#  9. gather() + one error      raises at once and you lose the rest →
#                               return_exceptions=True
# 10. create_task()             no new thread; keep a reference to it
# 11. no timeout                one hung call hangs everything →
#                               wait_for / asyncio.timeout
# 12. asyncio ≠ parallelism     CPU-bound work needs processes
#
# If you remember one thing:
#   await asyncio.gather(call_1(), call_2(), call_3())
# is Python's
#   await Promise.all([call1(), call2(), call3()])
