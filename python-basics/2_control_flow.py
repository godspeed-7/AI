# CONTROL FLOW IN PYTHON — quick reference notes
#
#   1. Comparison operators  == != < > <= >= · chaining · comparing types
#                            · comparing strings · == vs is
#   2. Logical operators     and / or / not · precedence · short-circuit
#                            · and/or return values · the "or" trap
#   3. if / elif / else      order matters · truthy checks · nesting · pass
#   4. Ternary operator      value_if_true if condition else value_if_false
#   5. match / case          Python's version of switch (3.10+)
#   6. for loops             range() · break / continue · for-else · nested
#   7. while loops           while True + break · infinite loops
#   8. Practice              even numbers · FizzBuzz · try-it-yourself
#   9. Gotchas recap         every surprise from this file in one list
#
# How to read this file:
#   # →       what the line prints (under a block: what the block prints)
#   # ❌      the line would raise an error, so it is commented out
#   GOTCHA    surprising behaviour — search for "GOTCHA" to review them all
#   end=" "   print(x, end=" ") prints a space instead of a new line,
#             so a loop's output fits on one line


# ======================================================================
# 1. COMPARISON OPERATORS
# ======================================================================
print("\n===== 1. COMPARISON OPERATORS =====")

# Every comparison returns a bool (True / False)
a = 10
b = 20
print(a == b)  # → False  equal to
print(a != b)  # → True   not equal to
print(a > b)   # → False  greater than
print(a < b)   # → True   less than
print(a >= b)  # → False  greater than or equal to
print(a <= b)  # → True   less than or equal to

# GOTCHA: = assigns a value, == compares two values
# if a = 10:   # ❌ SyntaxError: invalid syntax. Maybe you meant '=='...

# --- Chaining ----------------------------------------------------------
print("\n--- Chaining ---")
age = 10
print(0 < age < 20)  # → True    same as: 0 < age and age < 20
print(a < b < 15)    # → False   because 20 < 15 is False

# --- Comparing different types -----------------------------------------
print("\n--- Comparing different types ---")
print(10 == 10.0)        # → True    int and float compare by value
print(1 == True)         # → True    bool is a kind of int (see file 1)
# GOTCHA: Python never converts types for you (unlike == in JavaScript)
print("10" == 10)        # → False   a str is never equal to an int
print(int("10") == 10)   # → True    convert first, then compare
# print("10" < 5)        # ❌ TypeError: '<' not supported between
#                        #    instances of 'str' and 'int'

# --- Comparing strings -------------------------------------------------
print("\n--- Comparing strings ---")
text = "programming"
print(text == "programming")   # → True
print(text == "Programming")   # → False   GOTCHA: case-sensitive
print(text == "PROGRAMMING".lower())  # → True   lower() for a
#                                               case-insensitive check

# < and > compare strings character by character (alphabetical order)
print("apple" < "banana")  # → True
# GOTCHA: ALL uppercase letters come before ALL lowercase letters
print("Zebra" < "apple")   # → True
# GOTCHA: digits in strings are compared as text, not as numbers
print("10" < "9")          # → True    compares "1" with "9"

# --- == vs is ----------------------------------------------------------
# ==  → do they have the same VALUE?
# is  → are they the very same OBJECT in memory?
print("\n--- == vs is ---")
list_a = [1, 2, 3]
list_b = [1, 2, 3]
print(list_a == list_b)  # → True    same values
print(list_a is list_b)  # → False   two separate lists
# Rule of thumb: only use `is` with None →  if result is None:


# ======================================================================
# 2. LOGICAL OPERATORS
# ======================================================================
print("\n===== 2. LOGICAL OPERATORS =====")

high_income = True
good_credit = False
student = True

print(high_income and good_credit)  # → False  and: True if BOTH are True
print(high_income or good_credit)   # → True   or: True if AT LEAST ONE is
print(not student)                  # → False  not: flips True ↔ False
print(high_income and not student)  # → False  they can be combined

# --- Precedence: not → and → or ----------------------------------------
print("\n--- Precedence ---")
print(True or True and False)    # → True    means True or (True and False)
print((True or True) and False)  # → False   brackets change the result
# Use brackets whenever you mix `and` with `or` — much easier to read

# --- Short-circuit evaluation ------------------------------------------
# and → stops at the first False (nothing after it can make it True)
# or  → stops at the first True  (nothing after it can make it False)
print("\n--- Short-circuit evaluation ---")
True or print("never printed")    # `or` already has True  → skips the rest
False and print("never printed")  # `and` already has False → skips the rest
False or print("this one prints")  # → this one prints

# Why it matters: put the safety check FIRST
x = 0
print(x != 0 and 10 / x > 1)  # → False   10 / x never runs → no error
# print(10 / x > 1 and x != 0)  # ❌ ZeroDivisionError: division by zero

# --- and / or return one of the values, not always True / False --------
print("\n--- and / or return values ---")
print("" or "Guest")       # → Guest   "" is falsy, so `or` moves on
print("Alice" or "Guest")  # → Alice   first truthy value wins
print(0 and 5)             # → 0       `and` returns the first falsy value
print(3 and 5)             # → 5       ...or the last one if all truthy

# Common use: a default value
name = ""
display_name = name or "Guest"
print(display_name)  # → Guest

# --- GOTCHA: the "or" trap ---------------------------------------------
print("\n--- The 'or' trap ---")
color = "green"
# WRONG — Python reads this as (color == "red") or ("blue").
# "blue" is a non-empty string → truthy → an `if` would ALWAYS run!
print(color == "red" or "blue")           # → blue
# RIGHT
print(color == "red" or color == "blue")  # → False
print(color in ("red", "blue"))           # → False   shorter & clearer


# ======================================================================
# 3. IF / ELIF / ELSE
# ======================================================================
print("\n===== 3. IF / ELIF / ELSE =====")

# Indentation (4 spaces) defines the block — there are no { } in Python.
# Wrong indentation → IndentationError
x = 10
if x > 0:
    print("positive")
elif x < 0:
    print("negative")
else:
    print("zero")
# → positive

# --- elif order matters: only the FIRST true branch runs ---------------
print("\n--- elif order ---")
score = 95

# GOTCHA: wrong order — 95 >= 50 is True, so Python stops right there
if score >= 50:
    print("Pass")
elif score >= 90:
    print("Distinction")  # never reached!
# → Pass

# Right: check the most specific condition first
if score >= 90:
    print("Distinction")
elif score >= 50:
    print("Pass")
else:
    print("Fail")
# → Distinction

# --- Truthy checks (see file 1, section 4) -----------------------------
print("\n--- Truthy checks ---")
name = ""
if not name:
    print("Name is empty")  # → Name is empty

items = [1, 2]
if items:
    print("List has items")  # → List has items

# Pythonic:  `if name:`   instead of   `if name != "":`
#            `if items:`  instead of   `if len(items) > 0:`

# --- Nested if ---------------------------------------------------------
print("\n--- Nested if ---")
age = 25
has_id = True
if age >= 18:
    if has_id:
        print("Entry allowed")  # → Entry allowed

# Often cleaner flattened with `and`:
if age >= 18 and has_id:
    print("Entry allowed")  # → Entry allowed

# --- pass: a placeholder for an empty block ----------------------------
# A block can't be empty. `pass` does nothing — it just fills the space.
if age > 100:
    pass  # TODO: handle this later


# ======================================================================
# 4. TERNARY OPERATOR
# ======================================================================
print("\n===== 4. TERNARY OPERATOR =====")

age = 18
status = "Adult" if age >= 18 else "Minor"
print(status)  # → Adult

# GOTCHA: the order is   value_if_true if condition else value_if_false
# (other languages write  condition ? value_if_true : value_if_false)
# Keep it to ONE condition — nested ternaries are hard to read,
# use if / elif / else instead.


# ======================================================================
# 5. MATCH / CASE  (Python 3.10+)
# ======================================================================
print("\n===== 5. MATCH / CASE =====")

command = "stop"
match command:
    case "start":
        print("Starting")
    case "stop" | "quit":     # | means "or"
        print("Stopping")
    case _:                   # _ matches anything, like `default`
        print("Unknown command")
# → Stopping

# Only the first matching case runs — no `break` needed, no fall-through.

# A guard adds an extra condition to a case with `if`
status_code = 503
match status_code:
    case 200:
        print("OK")
    case 404:
        print("Not found")
    case code if code >= 500:  # `code` holds the value being matched
        print(f"Server error {code}")
    case _:
        print("Something else")
# → Server error 503


# ======================================================================
# 6. FOR LOOPS
# ======================================================================
print("\n===== 6. FOR LOOPS =====")

# --- range(start, stop, step) — stop is NOT included -------------------
# (list() is only here so we can print all the numbers at once)
print("\n--- range() ---")
print(list(range(5)))         # → [0, 1, 2, 3, 4]    start defaults to 0
print(list(range(1, 6)))      # → [1, 2, 3, 4, 5]
print(list(range(2, 11, 2)))  # → [2, 4, 6, 8, 10]   step of 2
print(list(range(5, 0, -1)))  # → [5, 4, 3, 2, 1]    count down
# GOTCHA: range(1, 10) stops at 9 — write range(1, 11) to include 10

# --- Looping over things -----------------------------------------------
print("\n--- Looping over things ---")
for i in range(5):
    print(i, end=" ")
print()
# → 0 1 2 3 4

# Strings and lists can be looped over directly
for char in "Hi!":
    print(char, end=" ")
print()
# → H i !

fruits = ["apple", "banana", "cherry"]
for fruit in fruits:
    print(fruit, end=" ")
print()
# → apple banana cherry
# Need the index as well? Use enumerate() — see 4_data_structures.py

# Use _ as the name when you don't need the loop variable
for _ in range(3):
    print("Hi", end=" ")
print()
# → Hi Hi Hi

# --- break & continue --------------------------------------------------
print("\n--- break & continue ---")
# break → leave the loop completely
for i in range(10):
    if i == 3:
        break
    print(i, end=" ")
print()
# → 0 1 2

# continue → skip the rest of THIS round, go to the next one
for i in range(6):
    if i % 2 == 0:
        continue
    print(i, end=" ")
print()
# → 1 3 5

# --- for-else: else runs only if the loop did NOT break ----------------
# Think of `else` here as "no break". Handy for searching.
print("\n--- for-else ---")
numbers = [3, 7, 9]
for n in numbers:
    if n % 2 == 0:
        print(f"Found an even number: {n}")
        break
else:
    print("No even number found")
# → No even number found

numbers = [3, 8, 9]
for n in numbers:
    if n % 2 == 0:
        print(f"Found an even number: {n}")
        break
else:
    print("No even number found")
# → Found an even number: 8   (else skipped because of the break)

# --- Nested loops ------------------------------------------------------
print("\n--- Nested loops ---")
# The inner loop runs completely for EACH round of the outer loop
for i in range(1, 4):
    for j in range(1, 4):
        print(i * j, end=" ")
    print()
# → 1 2 3
#   2 4 6
#   3 6 9

# GOTCHA: break only leaves the INNER loop — the outer one keeps going
for i in range(3):
    for j in range(3):
        if j == 1:
            break
        print(f"({i},{j})", end=" ")
print()
# → (0,0) (1,0) (2,0)

# GOTCHA: the loop variable still exists after the loop ends
for i in range(3):
    pass
print(i)  # → 2   (its last value)


# ======================================================================
# 7. WHILE LOOPS
# ======================================================================
print("\n===== 7. WHILE LOOPS =====")

# for   → when you know what to loop over (a range, a list, a string)
# while → when you loop UNTIL something happens
count = 0
while count < 3:
    print(count, end=" ")
    count += 1  # GOTCHA: forget this and the loop never ends
print()
# → 0 1 2
# Stuck in an infinite loop? Press Ctrl+C in the terminal to stop it.

# Example: you don't know in advance how many rounds it will take
n = 100
steps = 0
while n > 1:
    n //= 2
    steps += 1
print(f"100 can be halved {steps} times")  # → 100 can be halved 6 times

# --- while True + break ------------------------------------------------
# Loop forever, and break out from inside when you're done
print("\n--- while True + break ---")
attempts = 0
while True:
    attempts += 1
    if attempts == 3:
        print(f"Stopped after {attempts} attempts")
        break
# → Stopped after 3 attempts

# Real-world version: keep asking until the input is valid
# (commented out so this file runs without waiting for you to type)
# while True:
#     answer = input("Enter a number: ")
#     if answer.isdigit():
#         break
#     print("That's not a number, try again")

# while also supports `else`, with the same "no break" rule as for-else


# ======================================================================
# 8. PRACTICE
# ======================================================================
print("\n===== 8. PRACTICE =====")

# Exercise 1: print the even numbers from 1 to 10 and count them
count = 0
for i in range(1, 11):  # 11 so that 10 is included
    if i % 2 == 0:
        print(i, end=" ")
        count += 1
print()
print(f"Total even numbers: {count}")
# → 2 4 6 8 10
#   Total even numbers: 5
# Shortcut: range(2, 11, 2) gives you the even numbers directly

# Exercise 2: FizzBuzz for 1–15
# multiple of 3 AND 5 → "FizzBuzz", of 3 → "Fizz", of 5 → "Buzz",
# otherwise print the number
for i in range(1, 16):
    if i % 15 == 0:  # most specific case FIRST (remember elif order!)
        print("FizzBuzz", end=" ")
    elif i % 3 == 0:
        print("Fizz", end=" ")
    elif i % 5 == 0:
        print("Buzz", end=" ")
    else:
        print(i, end=" ")
print()
# → 1 2 Fizz 4 Buzz Fizz 7 8 Fizz Buzz 11 Fizz 13 14 FizzBuzz

# Try it yourself (answers in brackets):
#   a) Add up all the numbers from 1 to 100 with a for loop       [5050]
#   b) With while True + break, find the first number above 100
#      that is divisible by both 7 and 5                          [105]
#   c) With nested loops, print a triangle of stars:              [*
#                                                                  **
#                                                                  ***]


# ======================================================================
# 9. GOTCHAS RECAP
# ======================================================================
#  1. if color == "red" or "blue"   always truthy!
#                                   use: color in ("red", "blue")
#  2. range(1, 10)                  stops at 9 — the stop is excluded
#  3. if / elif                     only the FIRST true branch runs —
#                                   put the most specific check first
#  4. "10" == 10 → False            no automatic type conversion
#  5. "10" < 5 → TypeError          can't order a str and an int
#  6. "Zebra" < "apple" → True      uppercase sorts before lowercase;
#                                   string checks are case-sensitive
#  7. "10" < "9" → True             strings compare as text, not numbers
#  8. is vs ==                      == compares values; use `is` for None
#  9. = vs ==                       = assigns, == compares
# 10. True or False and False       not → and → or; use brackets
# 11. x != 0 and 10 / x             short-circuit: safety check goes first
# 12. "" or "Guest" → "Guest"       and / or return a value, not a bool
# 13. a if cond else b              ternary order differs from cond ? a : b
# 14. for / while ... else          else runs only when there was NO break
# 15. break in nested loops         only leaves the inner loop
# 16. loop variable                 still exists after the loop ends
# 17. while loop                    forget to update → infinite loop (Ctrl+C)
