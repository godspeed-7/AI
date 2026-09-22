
# PRIMITIVE TYPES IN PYTHON — quick reference notes

#   1. Overview          int, float, bool, str, None · type() · isinstance() · dynamic typing
#   2. Strings           quotes · escape sequences · indexing & slicing · immutability
#                        · concatenation · methods · f-strings
#   3. Numbers           operators · precedence · augmented assignment · built-ins
#                        · math module · float precision
#   4. Booleans & None   truthy / falsy · bool is an int · checking for None
#   5. Type conversion   int() · float() · str() · errors to expect
#   6. Gotchas recap     every surprise from this file in one list

# How to read this file:
#   # →       what the line prints
#   # ❌      the line would raise an error, so it is commented out
#   GOTCHA    surprising behaviour — search for "GOTCHA" to review them all


import math


# ======================================================================
# 1. OVERVIEW
# ======================================================================
print("\n===== 1. OVERVIEW =====")

student_count = 1000  # int    → whole numbers (no size limit in Python)
rating = 4.5          # float  → decimal numbers
is_active = True      # bool   → True / False (capitalised!)
name = "John Doe"     # str    → text
middle_name = None    # None   → "no value" (like null in other languages)

# type() — tells you the type of a value
print(type(student_count))  # → <class 'int'>
print(type(rating))         # → <class 'float'>
print(type(is_active))      # → <class 'bool'>
print(type(name))           # → <class 'str'>
print(type(middle_name))    # → <class 'NoneType'>

# isinstance() — the preferred way to CHECK a type
print(isinstance(rating, float))         # → True
# → True   (pass a tuple to check several types)
print(isinstance(rating, (int, float)))

# Dynamic typing — the VALUE has a type, the variable doesn't.
# The same variable can hold an int now and a str later.
x = 10
print(type(x))  # → <class 'int'>
x = "ten"
print(type(x))  # → <class 'str'>


# ======================================================================
# 2. STRINGS
# ======================================================================
print("\n===== 2. STRINGS =====")

# --- Quotes ------------------------------------------------------------
print("\n--- Quotes ---")
single = 'Hello'       # single and double quotes are the same thing
double = "Hello"       # pick one style and stay consistent
mixed = "It's easy"    # use the other quote type to avoid escaping
multi = """Line 1
Line 2"""              # triple quotes → string can span multiple lines
print(mixed)  # → It's easy
print(multi)  # → Line 1
#               Line 2

# --- Escape sequences --------------------------------------------------
# \"  double quote      \'  single quote      \\  backslash
# \n  new line          \t  tab
print("\n--- Escape sequences ---")
print("Python \"Programming\"")  # → Python "Programming"
print('It\'s fine')              # → It's fine
print("C:\\Users\\john")         # → C:\Users\john
print("Line1\nLine2")            # → Line1
#                                    Line2
print("Name:\tJohn")             # → Name:   John   (tab)

# Raw string r"..." — backslashes are kept as-is (handy for Windows paths & regex)
print(r"C:\new\folder")  # → C:\new\folder
# GOTCHA: without the r, "\n" inside "C:\new\folder" would turn into a new line!

# --- Indexing & slicing ------------------------------------------------
print("\n--- Indexing & slicing ---")
course = "Python Programming"
# → 18   len() is a built-in FUNCTION: len(course), not course.len()
print(len(course))
print(course[0])     # → P    first character (indexes start at 0)
# → g    last character (negative index counts from the end)
print(course[-1])

# Slicing: [start:end:step] → start is INCLUDED, end is NOT included
print(course[0:6])   # → Python              characters 0 to 5
print(course[:6])    # → Python              start defaults to 0
# → Programming         end defaults to the end of the string
print(course[7:])
print(course[:])     # → Python Programming  full copy
print(course[::2])   # → Pto rgamn           every 2nd character
print(course[::-1])  # → gnimmargorP nohtyP  reversed

# GOTCHA: indexing past the end raises an error, slicing past the end does not
# print(course[100])   # ❌ IndexError: string index out of range
print(course[0:100])   # → Python Programming  (slicing just stops at the end)

# --- Immutability ------------------------------------------------------
# Strings are IMMUTABLE — you can never change a string in place.
print("\n--- Immutability ---")
# course[0] = "J"   # ❌ TypeError: 'str' object does not support item assignment

# GOTCHA: every string method returns a NEW string, the original is untouched
course.upper()
print(course)            # → Python Programming  (unchanged!)
course = course.upper()  # reassign if you want to keep the result
print(course)            # → PYTHON PROGRAMMING

# --- Concatenation & repetition ----------------------------------------
print("\n--- Concatenation & repetition ---")
first = "John"
last = "Doe"
print(first + " " + last)  # → John Doe    + joins strings
print("-" * 10)            # → ----------  * repeats a string

# GOTCHA: you can't + a string and a number
# print("Age: " + 25)      # ❌ TypeError: can only concatenate str (not "int") to str
# → Age: 25     convert first (or use an f-string, see below)
print("Age: " + str(25))

# --- String methods ----------------------------------------------------
print("\n--- String methods ---")
course = "python programming"

# Changing case
print(course.upper())       # → PYTHON PROGRAMMING
print(course.lower())       # → python programming
print(course.title())       # → Python Programming  (first letter of EVERY word)
print(course.capitalize())  # → Python programming  (first letter only)

# Removing whitespace (brackets added so you can see the spaces)
padded = "   hello   "
print(f"[{padded.strip()}]")   # → [hello]      both sides
print(f"[{padded.lstrip()}]")  # → [hello   ]   left side only
print(f"[{padded.rstrip()}]")  # → [   hello]   right side only

# Searching
print(course.find("pro"))        # → 7      index where "pro" starts
print(course.find("java"))       # → -1     .find() returns -1 when not found
# print(course.index("java"))    # ❌ ValueError: substring not found  (.index() raises instead)
print(course.count("m"))         # → 2      how many times it appears
print(course.startswith("py"))   # → True
print(course.endswith("ing"))    # → True

# Membership with `in` — cleaner than .find() for yes/no checks
print("pro" in course)       # → True
print("java" not in course)  # → True

# GOTCHA: all of these checks are case-sensitive
print("Pro" in course)                  # → False
# → True   lower() both sides for a case-insensitive check
print("Pro".lower() in course.lower())

# Replacing
print(course.replace("python", "java"))  # → java programming
# GOTCHA: no error if the text isn't found — it silently returns the same string
print(course.replace("ruby", "java"))    # → python programming

# Checking the content (all return True / False)
print("123".isdigit())   # → True
print("12.5".isdigit())  # → False  ("." is not a digit)
print("abc".isalpha())   # → True
print("   ".isspace())   # → True

# Split & join
print(course.split(" "))          # → ['python', 'programming']   str → list
print("-".join(["a", "b", "c"]))  # → a-b-c                       list → str
# GOTCHA: join is called on the SEPARATOR, not on the list

# split(" ") vs split()
print("a  b".split(" "))  # → ['a', '', 'b']  splits on every single space
# → ['a', 'b']      no argument = split on any whitespace (usually what you want)
print("a  b".split())

# --- f-strings (formatted strings) -------------------------------------
print("\n--- f-strings ---")
full_name = f"{first} {last}"
print(full_name)                             # → John Doe
# → John has 4 letters   any expression works inside {}
print(f"{first} has {len(first)} letters")
print(f"2 + 3 = {2 + 3}")                    # → 2 + 3 = 5

# Format specs go after a colon → {value:spec}
price = 1234.5678
print(f"{price:.2f}")    # → 1234.57     2 decimal places
print(f"{price:,.2f}")   # → 1,234.57    thousands separator + 2 decimals
print(f"{0.256:.1%}")    # → 25.6%       as a percentage
print(f"{7:03}")         # → 007         pad with zeros to width 3
print(f"[{'hi':>6}]")    # → [    hi]    right-align in 6 characters
print(f"[{'hi':<6}]")    # → [hi    ]    left-align
print(f"[{'hi':^6}]")    # → [  hi  ]    center

# Debug shortcut: add = to print the name AND the value
print(f"{price=}")       # → price=1234.5678


# ======================================================================
# 3. NUMBERS
# ======================================================================
print("\n===== 3. NUMBERS =====")

# --- Arithmetic operators ----------------------------------------------
print("\n--- Arithmetic operators ---")
print(10 + 3)         # → 13
print(10 - 3)         # → 7
print(10 * 3)         # → 30
print(10 / 3)         # → 3.3333333333333335  division
# → 3                   floor division (rounds DOWN to a whole number)
print(10 // 3)
print(10 % 3)         # → 1                   modulus (the remainder)
print(10 ** 3)        # → 1000                exponent (10 to the power 3)
# → (3, 1)              floor division and remainder in one go
print(divmod(10, 3))

# GOTCHA: / ALWAYS returns a float, even when it divides evenly
print(10 / 2)   # → 5.0
print(10 // 2)  # → 5     use // if you want an int

# Mixing int and float gives a float
print(5 + 2.0)  # → 7.0

# GOTCHA: with negative numbers, // rounds toward minus infinity (not toward 0)
print(-7 // 2)  # → -4   (not -3)
print(-7 % 2)   # → 1    (not -1)

# --- Operator precedence -----------------------------------------------
# Order: ()  →  **  →  * / // %  →  + -
print("\n--- Operator precedence ---")
print(2 + 3 * 4)    # → 14
print((2 + 3) * 4)  # → 20    use brackets to be explicit
# GOTCHA: ** is evaluated right-to-left, and it binds tighter than a minus sign
print(2 ** 3 ** 2)  # → 512   means 2 ** (3 ** 2) = 2 ** 9
print(-2 ** 2)      # → -4    means -(2 ** 2);  write (-2) ** 2 to get 4

# --- Augmented assignment ----------------------------------------------
print("\n--- Augmented assignment ---")
count = 10
count += 5   # same as count = count + 5  → 15
count -= 3   # → 12
count *= 2   # → 24
count //= 5  # → 4
print(count)  # → 4
# GOTCHA: Python has no ++ or --
# count++      # ❌ SyntaxError
# ++count is allowed but does NOTHING (it just means +(+count)). Use count += 1

# --- Writing numbers ---------------------------------------------------
print("\n--- Writing numbers ---")
population = 1_000_000  # underscores are ignored — they're only for readability
print(population)       # → 1000000
print(1.5e3)            # → 1500.0   scientific notation (1.5 × 10³), always a float
# → 1267650600228229401496703205376   ints have no maximum size
print(2 ** 100)

# --- Built-in number functions -----------------------------------------
print("\n--- Built-in number functions ---")
print(round(10.7))        # → 11
print(round(3.14159, 2))  # → 3.14   round to 2 decimal places
# GOTCHA: an exact .5 rounds to the nearest EVEN number ("banker's rounding")
print(round(10.5))        # → 10   (not 11!)
print(round(11.5))        # → 12
print(abs(-7.5))          # → 7.5  absolute value (removes the minus sign)
print(max(3, 9, 1))       # → 9
print(min(3, 9, 1))       # → 1
print(pow(2, 3))          # → 8    same as 2 ** 3

# --- math module (needs `import math` at the top) ----------------------
print("\n--- math module ---")
print(math.ceil(10.2))    # → 11                  always rounds UP
print(math.floor(10.8))   # → 10                  always rounds DOWN
print(math.trunc(-3.7))   # → -3                  chops off the decimal part
print(math.floor(-3.7))   # → -4                  DOWN means more negative
print(math.sqrt(16))      # → 4.0                 square root (always a float)
print(math.pi)            # → 3.141592653589793

# --- Float precision ---------------------------------------------------
print("\n--- Float precision ---")
# GOTCHA: floats are stored in binary, so most decimals are not exact
print(0.1 + 0.2)                     # → 0.30000000000000004
print(0.1 + 0.2 == 0.3)              # → False  (!)
# → True   compare floats with math.isclose()
print(math.isclose(0.1 + 0.2, 0.3))
print(round(0.1 + 0.2, 2))           # → 0.3    or round them for display
# For money, don't use floats — look up the `decimal` module.


# ======================================================================
# 4. BOOLEANS & NONE
# ======================================================================
print("\n===== 4. BOOLEANS & NONE =====")

# GOTCHA: True, False and None are capitalised
# is_active = true   # ❌ NameError: name 'true' is not defined

# --- Truthy & falsy ----------------------------------------------------
# Every value can be used as a bool (e.g. in an `if`).
# FALSY values: 0, 0.0, "", None, False, and empty collections [], {}, set(), ()
# Everything else is TRUTHY.
print("\n--- Falsy values ---")
print(bool(0))      # → False
print(bool(0.0))    # → False
print(bool(""))     # → False  empty string
print(bool(None))   # → False
print(bool([]))     # → False  empty list
print(bool({}))     # → False  empty dict
print(bool(set()))  # → False  empty set

print("\n--- Truthy values ---")
print(bool(-1))       # → True   any non-zero number, even negative
print(bool(" "))      # → True   a space is not an empty string!
print(bool([0]))      # → True   a list with one item isn't empty
# GOTCHA: any non-empty string is truthy, even these:
print(bool("0"))      # → True
print(bool("False"))  # → True

# In practice: `if name:` is the Pythonic way to write `if name != "":`

# --- bool is a kind of int ---------------------------------------------
print("\n--- bool is a kind of int ---")
print(True + True)             # → 2      True == 1 and False == 0
print(isinstance(True, int))   # → True
# → 2    handy for counting how many things are True
print(sum([True, False, True]))

# --- None --------------------------------------------------------------
print("\n--- None ---")
result = None
# → True    always check None with `is` / `is not`, not ==
print(result is None)
print(result is not None)  # → False


# ======================================================================
# 5. TYPE CONVERSION
# ======================================================================
print("\n===== 5. TYPE CONVERSION =====")

# --- Between numbers ---------------------------------------------------
print("\n--- Between numbers ---")
print(float(10))  # → 10.0
print(int(3.9))   # → 3    GOTCHA: int() CHOPS OFF the decimal, it doesn't round
print(int(-3.9))  # → -3   (moves toward 0 — compare math.floor(-3.9) → -4)
print(round(3.9))  # → 4    use round() if you actually want rounding

# --- To and from strings -----------------------------------------------
print("\n--- To and from strings ---")
print(str(10) + "5")       # → 105     str(10) is the text "10", so + joins text
print(int("42") + 8)       # → 50      int("42") is the number 42, so + adds
print(float("3.5"))        # → 3.5
print(int("  42  "))       # → 42      spaces around the number are ignored

# GOTCHA: int() only accepts whole-number strings
# print(int("3.5"))        # ❌ ValueError: invalid literal for int() with base 10: '3.5'
print(int(float("3.5")))   # → 3       convert to float first
# print(int("abc"))        # ❌ ValueError: invalid literal for int() with base 10: 'abc'

# Check before converting
text = "123"
if text.isdigit():
    print(int(text))       # → 123

# GOTCHA: input() ALWAYS returns a string, even if the user types a number.
# (Commented out so this file runs without waiting for you to type.)
# age = input("Age: ")        # user types 25  → age is "25" (a str)
# age = int(input("Age: "))   # convert straight away if you need a number

# To bool: see section 4 — bool("False") is True!


# ======================================================================
# 6. GOTCHAS RECAP
# ======================================================================
#  1. round(10.5) → 10             an exact .5 rounds to the nearest EVEN number
#  2. 0.1 + 0.2 == 0.3 → False     floats aren't exact; use math.isclose()
#  3. 10 / 2 → 5.0                 / always returns a float; use // for an int
#  4. -7 // 2 → -4                 // rounds toward minus infinity
#  5. int(3.9) → 3                 int() chops off decimals, it doesn't round
#  6. int("3.5") → ValueError      use int(float("3.5"))
#  7. input() returns a str        convert with int() / float()
#  8. bool("False") → True         any non-empty string is truthy (even "0")
#  9. "Pro" in "programming"       → False, string checks are case-sensitive
# 10. s.upper() doesn't change s   strings are immutable; reassign: s = s.upper()
# 11. .replace() / .find()         don't raise errors when the text isn't found
# 12. "Age: " + 25 → TypeError     use str(25) or an f-string
# 13. "-".join(list)               join is called on the separator
# 14. s[100] → IndexError          but s[0:100] is fine
# 15. -2 ** 2 → -4                 ** binds tighter than minus; 2 ** 3 ** 2 → 512
# 16. No ++ / --                   use x += 1
# 17. "C:\new" has a newline in it  use a raw string r"C:\new"
# 18. true / false / none          must be capitalised: True / False / None
