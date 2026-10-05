# EXCEPTIONS IN PYTHON — quick reference notes
#
#   1. What an exception is   traceback · the common error types
#   2. try / except          as error · several types · order matters
#   3. else & finally        what runs when
#   4. with                  automatic cleanup, instead of finally
#   5. raise                 your own errors · re-raise · custom type
#   6. Everyday patterns     safe conversion · retry · ask forgiveness
#   7. What it costs         timeit
#   8. Practice              safe_divide · config reader · try-it-yourself
#   9. Gotchas recap         every surprise from this file in one list
#
# How to read this file:
#   # →       what the line prints (under a block: what the block prints)
#   # ❌      the line would raise an error, so it is commented out
#   GOTCHA    surprising behaviour — search for "GOTCHA" to review them all
#
# Coming from JavaScript:
#   try / catch / finally  → try / except / else / finally
#   throw new Error("x")   → raise ValueError("x")
#   catch (e)              → except Exception as error
#   (no equivalent)        → else: runs when nothing went wrong

from timeit import timeit


# ======================================================================
# 1. WHAT AN EXCEPTION IS
# ======================================================================
# An exception is Python saying "I can't do this" and stopping.
# Left alone it ends the program and prints a traceback:
#
#   print(10 / 0)   # ❌ ZeroDivisionError: division by zero
#
# Read a traceback BOTTOM-UP: the last line says what went wrong,
# the lines above show the path that got there.
#
# The ones you'll meet most (files 1–4 produced nearly all of them):
#   ValueError         right type, impossible value    int("abc")
#   TypeError          wrong type altogether           "a" + 1
#   KeyError           missing dict key                user["nope"]
#   IndexError         index past the end              [1, 2][5]
#   AttributeError     no such method                  None.upper()
#   ZeroDivisionError  divided by zero                 10 / 0
#   FileNotFoundError  no such file                    open("a.txt")
#   NameError          name was never defined          prnt("hi")
#
# "Handling" an exception means: expect it, and decide what to do.


# ======================================================================
# 2. TRY / EXCEPT
# ======================================================================
print("\n===== 2. TRY / EXCEPT =====")

# input() would stop the file and wait for typing, so these are the
# answers we pretend someone typed. The real line is at the end.
answers = ["abc", "0", "25"]

for answer in answers:
    try:
        age = int(answer)         # may raise ValueError
        per_year = 100 / age      # may raise ZeroDivisionError
    except ValueError as error:
        print(f"not a number — {error}")
    except ZeroDivisionError:
        print("age cannot be zero")
    except Exception as e:
        print("generic exception")
    else:
        print(f"age {age} → {per_year} per year")
# → not a number — invalid literal for int() with base 10: 'abc'
#   age cannot be zero
#   age 25 → 4.0 per year
#
# The real version of line 1 inside the try:
#   age = int(input("Enter your age: "))

# --- `as error` gives you the exception object --------------------------
print("\n--- as error ---")
try:
    int("abc")
except ValueError as error:
    print(error)                   # → invalid literal for int() with
    #                                  base 10: 'abc'
    print(type(error).__name__)    # → ValueError

# --- One block for several types ---------------------------------------
print("\n--- Several types ---")
try:
    value = int(None)
except (ValueError, TypeError) as error:  # note the brackets: a tuple
    print(f"bad input: {type(error).__name__}")  # → bad input: TypeError

# --- Order matters: specific first, catch-all last ---------------------
print("\n--- Order ---")
try:
    10 / 0
except ZeroDivisionError:
    print("the specific one wins")  # → the specific one wins
except Exception as error:
    print(f"catch-all: {error}")

# GOTCHA: `except Exception` catches almost everything, so it must come
# LAST — put it first and the specific blocks below it never run.
#
# GOTCHA: a bare `except:` also swallows Ctrl+C and SystemExit.
# Always write `except Exception as error:` instead.
#
# GOTCHA: don't silence what you don't understand —
#   except Exception:
#       pass          ← the bug vanishes and you never hear about it


# ======================================================================
# 3. ELSE & FINALLY
# ======================================================================
print("\n===== 3. ELSE & FINALLY =====")

# try     → the risky code
# except  → only when that kind of error happened
# else    → only when NOTHING went wrong
# finally → ALWAYS, error or not. Cleanup goes here.


def divide(a, b):
    try:
        result = a / b
    except ZeroDivisionError:
        print("cannot divide by zero", end="  ")
        return None
    else:
        print(f"ok: {result}", end="  ")
        return result
    finally:
        print("(finally still runs)")


divide(10, 2)  # → ok: 5.0  (finally still runs)
divide(10, 0)  # → cannot divide by zero  (finally still runs)
# Note: finally runs even after `return` — that's the whole point of it.

# GOTCHA (this was the bug in the first version of this file):
# if open() fails, `file` never gets created, so the cleanup crashes too
# try:
#     file = open("missing.txt")
# except FileNotFoundError:
#     print("no file")
# finally:
#     file.close()   # ❌ NameError: name 'file' is not defined


# ======================================================================
# 4. WITH — AUTOMATIC CLEANUP
# ======================================================================
print("\n===== 4. WITH =====")

# `with` closes the resource for you, however the block ends.
# For files this replaces try / finally completely.
try:
    with open("missing.txt") as file:
        print(file.read())
except FileNotFoundError as error:
    print(f"could not open it — {error}")
# → could not open it — [Errno 2] No such file or directory:
#   'missing.txt'
# GOTCHA: the old version caught ValueError here, which never matches.
# A missing file is a FileNotFoundError.

# A file that definitely exists: this one. __file__ is its own path.
with open(__file__) as file:
    first_line = file.readline().strip()

print(first_line)    # → # EXCEPTIONS IN PYTHON — quick reference notes
print(file.closed)   # → True   `with` already closed it


# ======================================================================
# 5. RAISE — THROWING YOUR OWN
# ======================================================================
print("\n===== 5. RAISE =====")


def set_age(age):
    if not isinstance(age, int):
        raise TypeError("age must be a whole number")
    if age < 0:
        raise ValueError("age cannot be negative")
    return age


try:
    set_age(-5)
except ValueError as error:
    print(f"rejected: {error}")  # → rejected: age cannot be negative

try:
    set_age("ten")
except (TypeError, ValueError) as error:
    print(f"rejected: {error}")  # → rejected: age must be a whole number

print(set_age(30))  # → 30   nothing raised, normal return

# GOTCHA: the old version called calculate_age(0) with a check of
# `age < 0`. 0 is not below 0, so nothing was raised and the except
# block never ran — the demo silently proved nothing. Test the case
# that should actually fail.

# --- Re-raising: handle part of it, pass the rest on -------------------
print("\n--- Re-raising ---")
try:
    try:
        int("abc")
    except ValueError as error:
        print(f"logging it here: {error}")
        raise  # bare `raise` sends the SAME error further up
except ValueError:
    print("and handling it out here")
# → logging it here: invalid literal for int() with base 10: 'abc'
#   and handling it out here

# --- Your own exception type -------------------------------------------
# It's just a class inheriting from an existing exception. Classes come
# later; this three-line shape is all you need for now.
print("\n--- Custom exception ---")


class InsufficientFunds(Exception):
    """Raised when an account doesn't have enough money."""


def withdraw(balance, amount):
    if amount > balance:
        raise InsufficientFunds(f"balance is only {balance}")
    return balance - amount


try:
    withdraw(100, 500)
except InsufficientFunds as error:
    print(f"declined: {error}")  # → declined: balance is only 100

# Why bother? The caller can catch YOUR error specifically, instead of
# guessing from an error message.


# ======================================================================
# 6. EVERYDAY PATTERNS
# ======================================================================
print("\n===== 6. EVERYDAY PATTERNS =====")


# --- Convert safely, with a fallback -----------------------------------
def to_int(text, default=0):
    try:
        return int(text)
    except (ValueError, TypeError):
        return default


print(to_int("42"), to_int("abc"), to_int(None, -1))  # → 42 0 -1

# --- Keep asking until the input is valid (file 2: while True) ---------
print("\n--- Retry ---")
pretend_inputs = iter(["abc", "", "30"])  # real code: input("Age: ")
while True:
    try:
        age = int(next(pretend_inputs))
        break
    except ValueError:
        print("not a number, try again")
print(age)
# → not a number, try again
#   not a number, try again
#   30

# --- Ask forgiveness, not permission ----------------------------------
# A JS habit is to check first. Python often prefers to just try it —
# one lookup instead of two, and no gap between check and use.
print("\n--- Ask forgiveness ---")
user = {"name": "John"}

if "age" in user:           # checking first
    print(user["age"])
else:
    print("no age")         # → no age

try:                        # just trying
    print(user["age"])
except KeyError:
    print("no age")         # → no age

print(user.get("age", "no age"))  # → no age   simplest of the three


# ======================================================================
# 7. WHAT IT COSTS
# ======================================================================
print("\n===== 7. WHAT IT COSTS =====")

# timeit(code, number=how many times) → seconds taken.
# Setting up a try block is nearly free. RAISING is the expensive part.
SAFE = 'try:\n    int("5")\nexcept ValueError:\n    pass'
RAISES = 'try:\n    int("x")\nexcept ValueError:\n    pass'
print(f"10,000 runs, no error : {timeit(SAFE, number=10000):.4f}s")
print(f"10,000 runs, raising  : {timeit(RAISES, number=10000):.4f}s")
# → roughly 0.0005s vs 0.0050s here — raising costs about 10x more.
#   (Your numbers will differ on every run.)
#
# So: exceptions for the exceptional case. Inside a hot loop that fails
# most of the time, a plain `if` check is cheaper.


# ======================================================================
# 8. PRACTICE
# ======================================================================
print("\n===== 8. PRACTICE =====")


# Exercise 1: divide, but return None instead of blowing up
def safe_divide(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        return None


print(safe_divide(10, 2), safe_divide(10, 0))  # → 5.0 None


# Exercise 2: read a port out of a config, falling back to 80
def get_port(settings):
    try:
        return int(settings["port"])
    except KeyError:
        print("no 'port' in config →", end=" ")
        return 80
    except ValueError:
        print("'port' is not a number →", end=" ")
        return 80


print(get_port({"port": "8080"}))  # → 8080
print(get_port({}))                # → no 'port' in config → 80
print(get_port({"port": "abc"}))   # → 'port' is not a number → 80

# Try it yourself:
#   a) parse_point("3,4") → (3, 4), and None for anything unparseable
#   b) check_password(text) that raises ValueError when it's under
#      8 characters, and returns True otherwise
#   c) read_or_default(path) that returns a file's first line, or
#      "no file" when the path doesn't exist
#   d) retry a function 3 times before giving up, printing each attempt


# ======================================================================
# 9. GOTCHAS RECAP
# ======================================================================
#  1. except ValueError            won't catch FileNotFoundError —
#                                  catch the type that is actually raised
#  2. finally + a failed line      the variable doesn't exist yet →
#                                  file.close() raises NameError
#  3. bare except:                 also catches Ctrl+C — use
#                                  `except Exception as error`
#  4. except Exception: pass       hides the bug; at least print it
#  5. except Exception first       the specific blocks below never run
#  6. else                         runs only when nothing was raised
#  7. finally                      runs even after return / raise
#  8. if age < 0: raise ...        never fires for 0 — test the real case
#  9. with open(...)               better than try / finally for files
# 10. raising is slow              a try that never raises is nearly free
# 11. ask forgiveness              try / except is often more Pythonic
#                                  than checking first
