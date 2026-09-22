# FUNCTIONS IN PYTHON — quick reference notes
#
#    1. Defining & calling      def · parameters vs arguments · docstrings
#                               · naming · define before calling
#    2. Return values           print vs return · None · early return
#                               · returning multiple values
#    3. Parameters & arguments  positional · keyword · defaults
#                               · the mutable default trap
#    4. *args & **kwargs        tuple / dict · combining · unpacking
#    5. Scope                   local vs global · UnboundLocalError · global
#                               · hiding built-ins
#    6. Passing lists in        mutable vs immutable arguments
#    7. Functions as values     passing functions around · lambda intro
#    8. Type hints              name: str -> str · not enforced
#    9. Recursion               base case · RecursionError
#   10. Practice                fizz_buzz · try-it-yourself
#   11. Gotchas recap           every surprise from this file in one list
#
# How to read this file:
#   # →       what the line prints (under a block: what the block prints)
#   # ❌      the line would raise an error, so it is commented out
#   GOTCHA    surprising behaviour — search for "GOTCHA" to review them all


# ======================================================================
# 1. DEFINING & CALLING
# ======================================================================
print("\n===== 1. DEFINING & CALLING =====")


# def name(parameters):  → the colon and the indented body are required
def greet(first_name, last_name):
    """Print a welcome message."""  # docstring: describes the function
    print(f"Hello and welcome {first_name} {last_name}")


greet("John", "Doe")  # → Hello and welcome John Doe

# Parameters = the names in the definition   → first_name, last_name
# Arguments  = the values you pass when calling → "John", "Doe"

# The docstring is what help(greet) shows you (and what your editor
# shows when you hover over the function name)
print(greet.__doc__)  # → Print a welcome message.

# Naming: snake_case, usually starting with a verb
#   get_name · save_user · is_valid · calculate_total

# GOTCHA: a function must be defined BEFORE the line that calls it
# say_bye()   # ❌ NameError: name 'say_bye' is not defined
#             #    (if def say_bye(): only appears further down the file)


# ======================================================================
# 2. RETURN VALUES
# ======================================================================
print("\n===== 2. RETURN VALUES =====")


def get_greeting(first_name):
    return f"Hi {first_name}"


message = get_greeting("John")        # store the returned value...
print(message)                        # → Hi John
print(get_greeting("Jane").upper())   # → HI JANE   ...or use it directly

# --- print vs return ---------------------------------------------------
# GOTCHA: print() only SHOWS a value on screen.
#         return HANDS IT BACK to the code that called the function.
# A function without `return` still returns something: None.
print("\n--- print vs return ---")
result = greet("John", "Doe")  # → Hello and welcome John Doe
print(result)                  # → None


# --- Early return ------------------------------------------------------
# `return` exits the function IMMEDIATELY — nothing after it runs.
def describe_age(age):
    if age < 0:
        return "Invalid age"
    if age < 18:
        return "Minor"
    return "Adult"  # only reached if nothing above returned


# Because each `return` exits, you don't need elif / else here.
print("\n--- Early return ---")
print(describe_age(-5))  # → Invalid age
print(describe_age(10))  # → Minor
print(describe_age(30))  # → Adult


# --- Returning multiple values -----------------------------------------
def min_max(numbers):
    return min(numbers), max(numbers)  # really returns ONE tuple


print("\n--- Returning multiple values ---")
print(min_max([3, 9, 1]))         # → (1, 9)
low, high = min_max([3, 9, 1])    # unpack the tuple into two variables
print(low, high)                  # → 1 9


# ======================================================================
# 3. PARAMETERS & ARGUMENTS
# ======================================================================
print("\n===== 3. PARAMETERS & ARGUMENTS =====")


def introduce(name, city):
    print(f"{name} lives in {city}")


# Positional arguments — matched by ORDER
introduce("John", "Paris")            # → John lives in Paris
introduce("Paris", "John")            # → Paris lives in John   (oops!)

# Keyword arguments — matched by NAME, so the order doesn't matter
introduce(city="Paris", name="John")  # → John lives in Paris

# You can mix them, but positional arguments must come first
introduce("John", city="Paris")       # → John lives in Paris
# introduce(name="John", "Paris")     # ❌ SyntaxError: positional
#                                     #    argument follows keyword argument


# --- Default values ----------------------------------------------------
def greet_user(name, greeting="Hello"):
    return f"{greeting}, {name}!"


print("\n--- Default values ---")
print(greet_user("John"))                      # → Hello, John!
print(greet_user("John", "Hi"))                # → Hi, John!
print(greet_user("John", greeting="Welcome"))  # → Welcome, John!

# greet_user()   # ❌ TypeError: greet_user() missing 1 required
#                #    positional argument: 'name'

# Parameters WITH a default must come after the ones without
# def greet_user(greeting="Hello", name):   # ❌ SyntaxError: parameter
#     ...                                   #    without a default follows
#                                           #    parameter with a default


# --- GOTCHA: the mutable default trap ----------------------------------
# A default value is created ONCE, when the function is defined — not on
# every call. So a list (or dict) default is SHARED between all calls.
# (Your editor warns about the line below — linters know this bug.)
def add_item_wrong(item, items=[]):
    items.append(item)
    return items


print("\n--- Mutable default trap ---")
print(add_item_wrong("apple"))   # → ['apple']
print(add_item_wrong("banana"))  # → ['apple', 'banana']   (!!)


# Fix: use None as the default and create a fresh list inside
def add_item(item, items=None):
    if items is None:
        items = []
    items.append(item)
    return items


print(add_item("apple"))   # → ['apple']
print(add_item("banana"))  # → ['banana']


# ======================================================================
# 4. *ARGS & **KWARGS
# ======================================================================
print("\n===== 4. *ARGS & **KWARGS =====")


# *args → collects any number of POSITIONAL arguments into a TUPLE
def show_args(*args):
    print(args)


show_args(1, 2, 3)  # → (1, 2, 3)
show_args()         # → ()
# The * is what matters — "args" is just the usual name.


def multiply(*numbers):
    total = 1
    for number in numbers:
        total *= number
    return total


print(multiply(2, 3, 4, 5))  # → 120
print(multiply())            # → 1     no numbers → the loop never runs


# **kwargs → collects any number of KEYWORD arguments into a DICT
def save_user(**user):
    print(user)
    print(user["name"])  # read values like any dict


save_user(id=1, name="John", age=22)
# → {'id': 1, 'name': 'John', 'age': 22}
#   John


# --- Combining: regular parameters → *args → **kwargs ------------------
def make_pizza(size, *toppings, **extras):
    print(f"size={size} toppings={toppings} extras={extras}")


print("\n--- Combining ---")
make_pizza("L", "cheese", "olives", delivery=True)
# → size=L toppings=('cheese', 'olives') extras={'delivery': True}

# --- Unpacking when CALLING: the reverse of *args / **kwargs -----------
# * spreads a list into separate arguments, ** spreads a dict
print("\n--- Unpacking ---")
numbers = [2, 3, 4]
print(multiply(*numbers))  # → 24    same as multiply(2, 3, 4)

person = {"name": "John", "city": "Paris"}
introduce(**person)        # → John lives in Paris
#                            same as introduce(name="John", city="Paris")


# ======================================================================
# 5. SCOPE
# ======================================================================
print("\n===== 5. SCOPE =====")


# A variable created INSIDE a function (local) only exists inside it
def make_secret():
    secret = 42
    return secret


make_secret()
# print(secret)   # ❌ NameError: name 'secret' is not defined

# A variable created OUTSIDE (global) can be READ inside a function
app_name = "MyApp"


def show_app():
    print(app_name)


show_app()  # → MyApp

# GOTCHA: ASSIGNING to it inside a function creates a NEW local variable,
# so reading it first (counter + 1) fails
counter = 0


def increment_wrong():
    counter += 1  # ← this line is the problem


# increment_wrong()  # ❌ UnboundLocalError: cannot access local variable
#                    #    'counter' where it is not associated with a value


# `global` lets a function change a global variable...
def increment_global():
    global counter
    counter += 1


increment_global()
print(counter)  # → 1


# ...but avoid it — it makes code hard to follow. Better: pass the value
# in and return the new one.
def increment(value):
    return value + 1


counter = increment(counter)
print(counter)  # → 2

# --- GOTCHA: hiding built-ins ------------------------------------------
# Naming a variable or parameter input, list, str, sum, max, type...
# hides Python's built-in with that name


def show_max(max):  # parameter named after the built-in max()
    print(max)
    # print(max(3, 7))  # ❌ TypeError: 'int' object is not callable
    #                   #    in here, max is the parameter, not max()


print("\n--- Hiding built-ins ---")
show_max(10)      # → 10
print(max(3, 7))  # → 7    outside the function the built-in still works


# ======================================================================
# 6. PASSING LISTS IN
# ======================================================================
# Python passes the object itself, not a copy.
#   int, float, str, bool → immutable → the function can't change yours
#   list, dict, set       → mutable   → changes inside affect the original
print("\n===== 6. PASSING LISTS IN =====")


def add_one(number):
    number += 1  # makes a NEW int, visible only inside the function


x = 5
add_one(x)
print(x)  # → 5    unchanged


def add_fruit(fruits):
    fruits.append("mango")  # changes the SAME list the caller has


my_fruits = ["apple"]
add_fruit(my_fruits)
print(my_fruits)  # → ['apple', 'mango']   GOTCHA: the original changed!

# Don't want that? Pass a copy:  add_fruit(my_fruits.copy())


# ======================================================================
# 7. FUNCTIONS AS VALUES
# ======================================================================
print("\n===== 7. FUNCTIONS AS VALUES =====")


# A function is a value like any other: you can store it and pass it.
# greet_user   (no brackets) → the function itself
# greet_user() (brackets)    → CALLS it
def double(n):
    return n * 2


def apply_twice(func, value):
    return func(func(value))


say_hello = greet_user          # store it under another name
print(say_hello("Ann"))         # → Hello, Ann!
print(apply_twice(double, 3))   # → 12   double(double(3))

# GOTCHA: forgetting the brackets doesn't call the function
print(double)  # → <function double at 0x...>   (not an error, not 8!)

# --- lambda: a tiny, nameless, one-line function -----------------------
#   lambda parameters: expression    (the result is returned automatically)
#   lambda n: n + 10  is the same as  def add_ten(n): return n + 10
print("\n--- lambda ---")
print(apply_twice(lambda n: n + 10, 1))  # → 21

names = ["Charlie", "al", "Bob"]
print(sorted(names, key=len))                    # → ['al', 'Bob', 'Charlie']
print(sorted(names, key=lambda name: name[-1]))  # → ['Bob', 'Charlie', 'al']
#                                                  sorted by LAST letter
# Use lambda only for short functions you pass straight into something
# else. If it needs a name, write a normal def.
# More lambda with sort / map / filter → see 4_data_structures.py


# ======================================================================
# 8. TYPE HINTS
# ======================================================================
print("\n===== 8. TYPE HINTS =====")


# first: str  → this parameter should be a str
# -> str      → this function returns a str
def full_name(first: str, last: str) -> str:
    return f"{first} {last}"


print(full_name("John", "Doe"))  # → John Doe

# GOTCHA: Python does NOT enforce type hints — this still runs fine
print(full_name(1, 2))           # → 1 2
# They're for humans and tools: your editor underlines the line above
# as a warning — that's exactly what type hints are for.


# More examples
def average(numbers: list[float]) -> float:    # a list of floats
    return sum(numbers) / len(numbers)


def find_user(user_id: int) -> str | None:     # a str OR None
    users = {1: "John", 2: "Jane"}
    return users.get(user_id)  # .get() gives None if the key is missing


def log(message: str, level: str = "INFO") -> None:  # returns nothing
    print(f"[{level}] {message}")


print(average([1, 2, 3]))  # → 2.0
print(find_user(1))        # → John
print(find_user(99))       # → None
log("Server started")      # → [INFO] Server started
# Note: with a type hint, write spaces around the default → level: str = ""


# ======================================================================
# 9. RECURSION
# ======================================================================
print("\n===== 9. RECURSION =====")


# A function that calls itself. It MUST have a base case that stops it.
def factorial(n):
    if n <= 1:  # base case → stop here
        return 1
    return n * factorial(n - 1)  # 5 * 4 * 3 * 2 * 1


print(factorial(5))  # → 120

# GOTCHA: no base case (or too many nested calls) → RecursionError.
# Python stops at about 1000 nested calls. A loop is usually simpler.


# ======================================================================
# 10. PRACTICE
# ======================================================================
print("\n===== 10. PRACTICE =====")


# Exercise: FizzBuzz as a function
# (parameter named `number`, not `input` — that would hide input()!)
def fizz_buzz(number: int) -> str:
    if number % 15 == 0:  # most specific check first (divisible by 3 AND 5)
        return "FizzBuzz"
    elif number % 3 == 0:
        return "Fizz"
    elif number % 5 == 0:
        return "Buzz"
    else:
        return str(number)  # str() so the function always returns a str


for n in [3, 5, 15, 7]:
    print(fizz_buzz(n), end=" ")
print()
# → Fizz Buzz FizzBuzz 7

# Try it yourself (expected results in brackets):
#   a) is_even(n) → True if n is even                   [is_even(4) → True]
#   b) count_vowels(text) → how many a/e/i/o/u        [count_vowels("banana")
#                                                        → 3]
#   c) average(*numbers) using *args, returning 0 if no numbers are given
#                                          [average(2, 4) → 3.0, average() → 0]
#   d) sum_digits(n) using recursion             [sum_digits(123) → 6]
#      hint: n % 10 is the last digit, n // 10 drops it


# ======================================================================
# 11. GOTCHAS RECAP
# ======================================================================
#  1. No return statement          the function returns None
#  2. print vs return              print shows it, return hands it back
#  3. return                       exits the function immediately
#  4. return a, b                  returns ONE tuple → unpack: x, y = f()
#  5. f(name="J", "Paris")         SyntaxError — positional args go first
#  6. def f(a=1, b)                SyntaxError — defaults go last
#  7. def f(items=[])              ONE list shared by every call!
#                                  use items=None, then create it inside
#  8. *args / **kwargs             arrive as a tuple / a dict
#  9. Local variables              don't exist outside the function
# 10. counter += 1 on a global     UnboundLocalError — return a value instead
# 11. max = 10, input = ...        hides the built-in with that name
# 12. Passing a list in            the function CAN change your list
#                                  (it can't change an int or a str)
# 13. double vs double()           no brackets = no call
# 14. Type hints                   not enforced when the code runs
# 15. Recursion                    needs a base case (limit ≈ 1000 calls)
# 16. Calling before def           NameError — define it first
