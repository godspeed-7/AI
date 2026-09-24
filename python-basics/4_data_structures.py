# DATA STRUCTURES IN PYTHON — quick reference notes
#
#    1. Lists              create · index & slice · loop · unpack · copy
#    2. List methods       append/insert/extend · remove/pop/del · search
#    3. Sorting            sort vs sorted · key= · reverse=True
#    4. Tuples             immutable · the (5,) trap · unpacking · as keys
#    5. Sets               unique · unordered · operations · deduplicating
#    6. Dictionaries       get vs [] · keys/values/items · nested · Counter
#    7. Comprehensions     list · dict · set · conditions · nested
#    8. Built-ins          len/sum/min/max/any/all · zip
#    9. Iterators          map/filter/zip are one-shot · lazy evaluation
#   10. Generators         (n for n in ...) · next() · memory · one-shot
#   11. Unpacking * / **   build · pass arguments · collect · unzip
#   12. Stacks & queues    list as a stack · deque
#   13. Which one to use?  comparison table · speed · NumPy note
#   14. Practice           word counting · list of dicts · try-it-yourself
#   15. Gotchas recap      every surprise from this file in one list
#
# How to read this file:
#   # →       what the line prints (under a block: what the block prints)
#   # ❌      the line would raise an error, so it is commented out
#   GOTCHA    surprising behaviour — search for "GOTCHA" to review them all
#
# Coming from JavaScript:
#   Array                → list          [1, 2, 3]
#   Object / Map         → dict          {"a": 1}
#   Set                  → set           {1, 2, 3}
#   (no equivalent)      → tuple         (1, 2)   a frozen list
#   arr.length           → len(lst)
#   arr.push(x)          → lst.append(x)
#   arr.pop()            → lst.pop()
#   arr.unshift(x)       → lst.insert(0, x)
#   arr.shift()          → lst.pop(0)
#   [...a, ...b]         → [*a, *b]   or   a + b
#   {...a, ...b}         → {**a, **b}
#   arr.map(f)           → [f(x) for x in arr]
#   arr.filter(f)        → [x for x in arr if f(x)]
#   arr.includes(x)      → x in lst
#   Object.keys(o)       → o.keys()
#   obj.hasOwnProperty() → "key" in o

import copy
import sys
from collections import Counter, deque


# ======================================================================
# 1. LISTS
# ======================================================================
print("\n===== 1. LISTS =====")

letters = ["a", "b", "c", "d", "e"]
mixed = [1, "two", 3.0, True, None]  # a list can hold any types
nested = [[1, 2], [3, 4]]            # lists inside lists
empty = []
print(letters)       # → ['a', 'b', 'c', 'd', 'e']
print(mixed)         # → [1, 'two', 3.0, True, None]
print(len(letters))  # → 5

# Building a list from something else
print(list("Hello"))       # → ['H', 'e', 'l', 'l', 'o']
print(list(range(5)))      # → [0, 1, 2, 3, 4]
print([0] * 5)             # → [0, 0, 0, 0, 0]   repeat
print([1, 2] + [3, 4])     # → [1, 2, 3, 4]      join two lists
print([*[1, 2], *[3, 4]])  # → [1, 2, 3, 4]      same, JS spread style

# --- Index & slice (same rules as strings, see file 1) -----------------
print("\n--- Index & slice ---")
print(letters[0])     # → a
print(letters[-1])    # → e
print(letters[1:3])   # → ['b', 'c']   end not included
print(letters[::2])   # → ['a', 'c', 'e']
print(letters[::-1])  # → ['e', 'd', 'c', 'b', 'a']
print(nested[1][0])   # → 3   a list inside a list

# Unlike strings, lists are MUTABLE — you can change them in place
letters[0] = "A"
print(letters)  # → ['A', 'b', 'c', 'd', 'e']
letters[0] = "a"

# --- Looping -----------------------------------------------------------
print("\n--- Looping ---")
for letter in letters:
    print(letter, end=" ")
print()
# → a b c d e

for index, letter in enumerate(letters):  # index AND value
    print(f"{index}:{letter}", end=" ")
print()
# → 0:a 1:b 2:c 3:d 4:e

for number, letter in enumerate(letters, start=1):  # start anywhere
    print(f"{number}:{letter}", end=" ")
print()
# → 1:a 2:b 3:c 4:d 5:e

for letter in reversed(letters):
    print(letter, end=" ")
print()
# → e d c b a

# --- Unpacking ---------------------------------------------------------
print("\n--- Unpacking ---")
x, y = [1, 2]
print(x, y)  # → 1 2

first, *rest = [1, 2, 3, 4]  # * collects the rest (JS ...rest)
print(first, rest)  # → 1 [2, 3, 4]

a, b = 1, 2
a, b = b, a  # swap — no temp variable needed
print(a, b)  # → 2 1

# GOTCHA: the number of names must match the number of values
# x, y = [1, 2, 3]   # ❌ ValueError: too many values to unpack
#                    #    (expected 2, got 3)

# --- Copy vs alias -----------------------------------------------------
print("\n--- Copy vs alias ---")
# GOTCHA: assigning does NOT copy — both names point to the SAME list
original = [1, 2, 3]
alias = original
alias.append(4)
print(original)           # → [1, 2, 3, 4]   changed through alias!
print(alias is original)  # → True

# Real copies — pick any of these three
copy1 = original.copy()
copy2 = list(original)
copy3 = original[:]
copy1.append(99)
print(original)           # → [1, 2, 3, 4]   untouched this time
print(copy2 == original)  # → True    same contents
print(copy2 is original)  # → False   but a different object

# GOTCHA: a copy is SHALLOW — inner lists are still shared
outer = [[1, 2], [3, 4]]
shallow = outer.copy()
shallow[0].append(99)
print(outer)  # → [[1, 2, 99], [3, 4]]   the inner list is the same one

deep = copy.deepcopy(outer)  # copies every level
deep[0].append(100)
print(outer)  # → [[1, 2, 99], [3, 4]]   unaffected


# ======================================================================
# 2. LIST METHODS
# ======================================================================
print("\n===== 2. LIST METHODS =====")

# --- Adding ------------------------------------------------------------
letters = ["a", "b", "c"]
letters.append("d")         # add ONE item at the end
letters.insert(0, "z")      # insert at an index
letters.extend(["e", "f"])  # add every item of another list
print(letters)  # → ['z', 'a', 'b', 'c', 'd', 'e', 'f']

# GOTCHA: append adds one item — even when that item is a list
demo = [1, 2]
demo.append([3, 4])
print(demo)  # → [1, 2, [3, 4]]
demo = [1, 2]
demo.extend([3, 4])
print(demo)  # → [1, 2, 3, 4]

# --- Removing ----------------------------------------------------------
print("\n--- Removing ---")
letters = ["a", "b", "c", "d", "e", "f"]
letters.remove("c")     # remove by VALUE (the first match only)
print(letters)          # → ['a', 'b', 'd', 'e', 'f']

last = letters.pop()    # remove AND return the last item
print(last, letters)    # → f ['a', 'b', 'd', 'e']

first = letters.pop(0)  # remove and return by index
print(first, letters)   # → a ['b', 'd', 'e']

del letters[0]          # delete by index, returns nothing
print(letters)          # → ['d', 'e']

numbers = list(range(10))
del numbers[2:5]        # del can remove a whole RANGE (pop can't)
print(numbers)          # → [0, 1, 5, 6, 7, 8, 9]

numbers.clear()         # remove everything
print(numbers)          # → []
# letters.remove("x")   # ❌ ValueError: list.remove(x): x not in list

# --- Searching ---------------------------------------------------------
print("\n--- Searching ---")
letters = ["a", "b", "c", "b"]
print("b" in letters)      # → True    the readable way to check
print("z" not in letters)  # → True
print(letters.index("b"))  # → 1       index of the FIRST match
print(letters.count("b"))  # → 2
# print(letters.index("z"))  # ❌ ValueError: list.index(x): x not in list
# Lists have no .find() (that's strings only) — check with `in` first


# ======================================================================
# 3. SORTING
# ======================================================================
print("\n===== 3. SORTING =====")

numbers = [5, 2, 9, 1, 5, 6]
numbers.sort()  # sorts IN PLACE
print(numbers)  # → [1, 2, 5, 5, 6, 9]
numbers.sort(reverse=True)
print(numbers)  # → [9, 6, 5, 5, 2, 1]

# GOTCHA: .sort() changes the list and returns None — never assign it
# result = numbers.sort()   # result would be None
result = sorted(numbers)    # sorted() returns a NEW list instead
print(result)   # → [1, 2, 5, 5, 6, 9]
print(numbers)  # → [9, 6, 5, 5, 2, 1]   the original is untouched

# Strings sort alphabetically, uppercase first (see file 2)
words = ["banana", "apple", "Cherry"]
print(sorted(words))                 # → ['Cherry', 'apple', 'banana']
print(sorted(words, key=str.lower))  # → ['apple', 'banana', 'Cherry']

# --- key= : sort by something other than the value itself --------------
print("\n--- key= ---")
items = [("apple", 5), ("banana", 2), ("cherry", 9)]


def by_count(item):
    return item[1]  # the second element of each tuple


items.sort(key=by_count)  # key = a function applied to every item
print(items)  # → [('banana', 2), ('apple', 5), ('cherry', 9)]

items.sort(key=lambda item: item[1], reverse=True)  # same, as a lambda
print(items)  # → [('cherry', 9), ('apple', 5), ('banana', 2)]

print(sorted(["pear", "fig", "banana"], key=len))  # any function works
# → ['fig', 'pear', 'banana']


# ======================================================================
# 4. TUPLES
# ======================================================================
print("\n===== 4. TUPLES =====")

point = (1, 2)
print(point)       # → (1, 2)
print(point[0])    # → 1   index and slice them like a list
print(len(point))  # → 2

# The commas make the tuple — the brackets are optional
also_a_tuple = 1, 2, 3
print(also_a_tuple)  # → (1, 2, 3)

# GOTCHA: a one-item tuple needs a trailing comma
print(type((5)))   # → <class 'int'>     just a number in brackets
print(type((5,)))  # → <class 'tuple'>

# Tuples are IMMUTABLE — a frozen list
# point[0] = 9   # ❌ TypeError: 'tuple' object does not support item
#                #    assignment
print(point + (3, 4))  # → (1, 2, 3, 4)   these make NEW tuples
print(point * 2)       # → (1, 2, 1, 2)

# Unpacking — extremely common in Python
x, y = point
print(x, y)  # → 1 2

for name, count in [("a", 1), ("b", 2)]:
    print(name, count, end="  ")
print()
# → a 1  b 2

# Only immutable values can be dict keys or set items,
# so a tuple can be a key — a list can't
locations = {(0, 0): "start", (1, 5): "goal"}
print(locations[(1, 5)])  # → goal
# {[0, 0]: "start"}   # ❌ TypeError: cannot use 'list' as a dict key
#                     #    (unhashable type: 'list')

# Use a tuple when the number of items is fixed and shouldn't change:
# coordinates, RGB colours, a function returning several values (file 3)


# ======================================================================
# 5. SETS
# ======================================================================
print("\n===== 5. SETS =====")

numbers = {1, 2, 3, 4, 5}
print(numbers)  # → {1, 2, 3, 4, 5}

# GOTCHA: {} is an empty DICT — use set() for an empty set
print(type({}))     # → <class 'dict'>
print(type(set()))  # → <class 'set'>

# A set holds UNIQUE items — duplicates simply disappear
print({1, 2, 2, 3, 3, 3})  # → {1, 2, 3}

# The most common real use: removing duplicates from a list
print(list(set([3, 1, 2, 1, 3])))    # → [1, 2, 3]   order NOT guaranteed
print(sorted(set([3, 1, 2, 1, 3])))  # → [1, 2, 3]   sort if order matters

# GOTCHA: sets are UNORDERED and can't be indexed
# print(numbers[0])  # ❌ TypeError: 'set' object is not subscriptable

# --- Adding & removing -------------------------------------------------
print("\n--- Adding & removing ---")
numbers.add(6)
numbers.discard(3)  # remove if present — no error when missing
numbers.remove(2)   # remove, but raises KeyError if it isn't there
print(numbers)      # → {1, 4, 5, 6}
print(3 in numbers)  # → False
print(4 in numbers)  # → True   membership is very fast in a set

# --- Set operations ----------------------------------------------------
print("\n--- Set operations ---")
evens = {2, 4, 6, 8}
smalls = {1, 2, 3, 4}
print(evens | smalls)  # → {1, 2, 3, 4, 6, 8}   union         .union()
print(evens & smalls)  # → {2, 4}               intersection  .intersection()
print(evens - smalls)  # → {8, 6}               difference    .difference()
print(evens ^ smalls)  # → {1, 3, 6, 8}         in one or the other, not both


# ======================================================================
# 6. DICTIONARIES
# ======================================================================
print("\n===== 6. DICTIONARIES =====")

user = {"name": "John", "age": 22, "tags": ["admin", "dev"]}
print(user)       # → {'name': 'John', 'age': 22, 'tags': ['admin', 'dev']}
print(len(user))  # → 3
# Keys are usually strings, but any immutable value works (int, tuple)

# --- Reading -----------------------------------------------------------
print("\n--- Reading ---")
print(user["name"])            # → John
# print(user["email"])         # ❌ KeyError: 'email'
print(user.get("email"))       # → None   no error for a missing key
print(user.get("email", "-"))  # → -      default value when missing
print("age" in user)           # → True   check before using []

# --- Writing -----------------------------------------------------------
print("\n--- Writing ---")
point = {"x": 1, "y": 2}
point["z"] = 3   # a new key
point["x"] = 10  # an existing key is overwritten
print(point)     # → {'x': 10, 'y': 2, 'z': 3}

point.update({"y": 20, "w": 4})  # add / overwrite several at once
print(point)  # → {'x': 10, 'y': 20, 'z': 3, 'w': 4}

merged = {**point, "extra": True}  # JS-style spread {...obj}
print(merged)
# → {'x': 10, 'y': 20, 'z': 3, 'w': 4, 'extra': True}

del point["w"]
removed = point.pop("z")  # removes AND returns the value
print(removed, point)     # → 3 {'x': 10, 'y': 20}

# --- Looping -----------------------------------------------------------
print("\n--- Looping ---")
user = {"name": "John", "age": 22}
for key in user:  # GOTCHA: a plain loop gives you the KEYS
    print(key, end=" ")
print()
# → name age

for value in user.values():
    print(value, end=" ")
print()
# → John 22

for key, value in user.items():  # the usual way
    print(f"{key}={value}", end=" ")
print()
# → name=John age=22

print(list(user.keys()))  # → ['name', 'age']
# Dicts keep their insertion order (Python 3.7+)

# --- Nested data -------------------------------------------------------
# This is the shape of JSON, API responses and most datasets
print("\n--- Nested data ---")
people = [
    {"name": "John", "age": 22, "skills": ["python", "js"]},
    {"name": "Jane", "age": 30, "skills": ["ai"]},
]
print(people[0]["skills"][1])  # → js
for person in people:
    print(f"{person['name']} ({person['age']})", end="  ")
print()
# → John (22)  Jane (30)
# Note the single quotes inside the f-string's { }

# --- Counting ----------------------------------------------------------
print("\n--- Counting ---")
words = ["a", "b", "a", "c", "a"]
counts = {}
for word in words:
    counts[word] = counts.get(word, 0) + 1  # .get with a default of 0
print(counts)  # → {'a': 3, 'b': 1, 'c': 1}

print(Counter(words))                 # → Counter({'a': 3, 'b': 1, 'c': 1})
print(Counter(words).most_common(1))  # → [('a', 3)]


# ======================================================================
# 7. COMPREHENSIONS
# ======================================================================
print("\n===== 7. COMPREHENSIONS =====")

# [expression for item in iterable]           ← JS: arr.map(...)
# [expression for item in iterable if test]   ← JS: arr.filter(...).map(...)
numbers = [1, 2, 3, 4, 5, 6]
print([n * n for n in numbers])            # → [1, 4, 9, 16, 25, 36]
print([n for n in numbers if n % 2 == 0])  # → [2, 4, 6]

# if/else BEFORE the for is a ternary (file 2), not a filter
print(["even" if n % 2 == 0 else "odd" for n in numbers])
# → ['odd', 'even', 'odd', 'even', 'odd', 'even']

# Nested: flatten a matrix — read it as two stacked for loops
matrix = [[1, 2, 3], [4, 5, 6]]
print([n for row in matrix for n in row])  # → [1, 2, 3, 4, 5, 6]

# Dict comprehension
print({n: n * n for n in [1, 2, 3]})  # → {1: 1, 2: 4, 3: 9}
prices = {"apple": 5, "banana": 2}
print({k: v * 2 for k, v in prices.items()})
# → {'apple': 10, 'banana': 4}

# Set comprehension — unique results
print({len(w) for w in ["hi", "to", "hello"]})  # → {2, 5}

# Round brackets make a lazy generator instead of a list — section 10
print(sum(n * n for n in range(1000)))  # → 332833500


# ======================================================================
# 8. BUILT-INS THAT WORK ON ANY COLLECTION
# ======================================================================
print("\n===== 8. BUILT-INS =====")

numbers = [5, 2, 9, 1]
print(len(numbers))                 # → 4
print(sum(numbers))                 # → 17
print(min(numbers), max(numbers))   # → 1 9
print(sum(numbers) / len(numbers))  # → 4.25   there is no .average()
print(any(n > 8 for n in numbers))  # → True   at least one matches
print(all(n > 0 for n in numbers))  # → True   every one matches
print(max({"a": 3, "b": 7}.values()))  # → 7   works on dict values too

# --- zip: walk through two collections side by side --------------------
print("\n--- zip ---")
names = ["apple", "banana", "cherry"]
prices = [5, 2, 9]
pairs = list(zip(names, prices))
print(pairs)  # → [('apple', 5), ('banana', 2), ('cherry', 9)]

for name, price in zip(names, prices):
    print(f"{name}:{price}", end=" ")
print()
# → apple:5 banana:2 cherry:9

print(dict(zip(names, prices)))  # build a dict from two lists
# → {'apple': 5, 'banana': 2, 'cherry': 9}

# GOTCHA: zip stops at the SHORTEST input
print(list(zip([1, 2, 3], ["a"])))  # → [(1, 'a')]

print(list(zip(*pairs)))  # * unzips it again
# → [('apple', 'banana', 'cherry'), (5, 2, 9)]


# ======================================================================
# 9. ITERATORS
# ======================================================================
print("\n===== 9. ITERATORS =====")

# map(), filter(), zip(), enumerate(), reversed() and range() do NOT
# return lists. They return lazy iterators that produce values on demand.
squares = map(lambda n: n * n, [1, 2, 3])
print(squares)        # → <map object at 0x...>
print(list(squares))  # → [1, 4, 9]   convert it to see the values

# GOTCHA: an iterator is used up after ONE pass
print(list(squares))  # → []   already empty!

# So either convert once to a list, or build the iterator again
evens = filter(lambda n: n % 2 == 0, [1, 2, 3, 4])
print(list(evens))  # → [2, 4]

# In Python a comprehension usually reads better than map / filter
print([n * n for n in [1, 2, 3]])  # → [1, 4, 9]

# Why lazy? Memory. Nothing is built until it's needed, so this works
# even on a billion items.


# ======================================================================
# 10. GENERATOR EXPRESSIONS
# ======================================================================
print("\n===== 10. GENERATOR EXPRESSIONS =====")

# Same syntax as a list comprehension, but with ( ) instead of [ ].
# A list builds every value right now and keeps them all in memory.
# A generator builds nothing — it hands over one value at a time.
numbers = [1, 2, 3, 4, 5]
squares_list = [n * n for n in numbers]  # a real list
squares_gen = (n * n for n in numbers)   # a generator
print(squares_list)  # → [1, 4, 9, 16, 25]
print(squares_gen)   # → <generator object <genexpr> at 0x...>
print(list(squares_gen))  # → [1, 4, 9, 16, 25]   values arrive on demand

# GOTCHA: a generator is an iterator (section 9), so it is ONE-SHOT
print(list(squares_gen))  # → []   already used up

# --- next(): take one value at a time ----------------------------------
print("\n--- next() ---")
gen = (n * n for n in [1, 2, 3])
print(next(gen))  # → 1
print(next(gen))  # → 4
print(next(gen))  # → 9
# print(next(gen))  # ❌ StopIteration  (nothing left)

# next() with a default is the safe version — and it stops as soon as it
# finds a match, so the rest is never computed (JS: arr.find(...))
print(next((n for n in numbers if n > 3), None))   # → 4
print(next((n for n in numbers if n > 99), None))  # → None

# --- Why bother: memory ------------------------------------------------
print("\n--- Memory ---")
print(sys.getsizeof([n * 2 for n in range(100_000)]))  # → 800984  bytes
print(sys.getsizeof((n * 2 for n in range(100_000))))  # → 208     bytes
# The list stores 100,000 numbers; the generator stores a recipe.
# (The exact numbers vary by Python version.)

# --- Where you'll actually use them ------------------------------------
# Drop the brackets when the generator is the only argument
print(sum(n * n for n in numbers))   # → 55
print(any(n > 4 for n in numbers))   # → True
print(max(n * n for n in numbers))   # → 25

# Rule of thumb:
#   need the values again, or by index → list comprehension [ ]
#   passing through once, or huge data → generator ( )
# Reading a 10GB file or streaming rows into a model is generator work.
#
# A def with `yield` is the bigger version of the same idea
# (a generator function) — a topic for later.


# ======================================================================
# 11. UNPACKING WITH * AND **
# ======================================================================
print("\n===== 11. UNPACKING WITH * AND ** =====")

#  *  spreads any iterable (list, tuple, set, string, generator)
#  ** spreads a dict as key=value pairs
#  JS: *  ≈ ...arr        ** ≈ ...obj

# --- Building new collections ------------------------------------------
a = [1, 2]
b = [3, 4]
print([*a, *b])     # → [1, 2, 3, 4]      like [...a, ...b]
print([0, *a, 9])   # → [0, 1, 2, 9]      spread anywhere in the list
print((*a, *b))     # → (1, 2, 3, 4)      into a tuple
print({*a, *b, 1})  # → {1, 2, 3, 4}      into a set (duplicates drop)
print([*"abc"])     # → ['a', 'b', 'c']   any iterable works
print([*(n * n for n in a)])  # → [1, 4]  including a generator

defaults = {"theme": "light", "lang": "en"}
prefs = {"lang": "hi"}
print({**defaults, **prefs})  # → {'theme': 'light', 'lang': 'hi'}
# GOTCHA: with duplicate keys the LAST one wins — order decides

# --- Passing arguments (see file 3, section 4) -------------------------
print("\n--- Passing arguments ---")


def introduce(name, city):
    print(f"{name} lives in {city}")


args = ["John", "Paris"]
kwargs = {"name": "Jane", "city": "Delhi"}
introduce(*args)     # → John lives in Paris    list → positional args
introduce(**kwargs)  # → Jane lives in Delhi    dict → keyword args
print(max(*[3, 9, 1]))  # → 9    same as max(3, 9, 1)

# GOTCHA: * means the opposite in a def and in a call
#   def f(*args)  → COLLECTS many arguments into a tuple
#   f(*mylist)    → SPREADS one list into many arguments

# --- Collecting while unpacking ----------------------------------------
print("\n--- Collecting ---")
first, *rest = [1, 2, 3, 4]
print(first, rest)  # → 1 [2, 3, 4]

*most, last = [1, 2, 3, 4]
print(most, last)   # → [1, 2, 3] 4

start, *middle, end = [1, 2, 3, 4, 5]
print(middle)       # → [2, 3, 4]

one, *nothing = [1]
print(nothing)      # → []   the starred name is always a list

# --- Unzipping ---------------------------------------------------------
print("\n--- Unzipping ---")
pairs = [("apple", 5), ("banana", 2)]
names, prices = zip(*pairs)  # spreads the pairs into zip's arguments
print(names)   # → ('apple', 'banana')
print(prices)  # → (5, 2)

for index, (name, price) in enumerate(pairs):  # nested unpacking
    print(index, name, price, end="  ")
print()
# → 0 apple 5  1 banana 2

name, _ = pairs[0]  # _ = "I don't need this value"
print(name)  # → apple


# ======================================================================
# 12. STACKS & QUEUES
# ======================================================================
print("\n===== 12. STACKS & QUEUES =====")

# Stack (last in, first out) — a plain list does the job
stack = []
stack.append(1)
stack.append(2)
stack.append(3)
print(stack)        # → [1, 2, 3]
print(stack[-1])    # → 3   peek at the top without removing
print(stack.pop())  # → 3   take the top one off
print(stack)        # → [1, 2]

stack.clear()
if not stack:  # the Pythonic "is it empty?" — not len(stack) == 0
    print("stack is empty")  # → stack is empty

# Queue (first in, first out) — use deque.
# lst.pop(0) works but has to shift every remaining item (slow).
queue = deque([1, 2, 3])
queue.append(4)         # add on the right
print(queue.popleft())  # → 1   take from the left
print(queue)            # → deque([2, 3, 4])
queue.appendleft(0)
print(list(queue))      # → [0, 2, 3, 4]


# ======================================================================
# 13. WHICH ONE SHOULD I USE?
# ======================================================================
#                 ordered?  changeable?  duplicates?  look up by
#   list  [ ]     yes       yes          yes          index   lst[0]
#   tuple ( )     yes       NO           yes          index   tup[0]
#   set   { }     no        yes          NO           —       x in s
#   dict  {k: v}  yes (*)   yes          unique keys  key     d["k"]
#   (*) insertion order, Python 3.7+
#
#   Pick by the question you ask most often:
#     "what comes next, in order?"      → list
#     "these belong together and must
#      not change"                      → tuple
#     "have I seen this already?"       → set
#     "what's the value for this key?"  → dict
#
#   Speed: `x in list` checks every item one by one. `x in set` and
#   `x in dict` jump straight to the answer, however big they get.
#   That difference matters a lot once you work with real data.
#
#   For AI work: these four are the everyday structures, but number
#   crunching moves to NumPy arrays (np.array) and pandas DataFrames.
#   They store one fixed type and run operations on the whole array at
#   once. The standard library's `array` module is rarely used — NumPy
#   replaced it.


# ======================================================================
# 14. PRACTICE
# ======================================================================
print("\n===== 14. PRACTICE =====")

# Exercise 1: count how often each word appears in a sentence
sentence = "the quick brown fox jumps over the lazy dog the end"
counts = {}
for word in sentence.split():
    counts[word] = counts.get(word, 0) + 1
print(counts["the"])  # → 3
print(Counter(sentence.split()).most_common(2))
# → [('the', 3), ('quick', 1)]

# Exercise 2: from a list of dicts, get the names of everyone over 25,
# sorted alphabetically
people = [
    {"name": "John", "age": 22},
    {"name": "Jane", "age": 30},
    {"name": "Bob", "age": 41},
]
older = sorted([p["name"] for p in people if p["age"] > 25])
print(older)  # → ['Bob', 'Jane']

# Try it yourself (expected results in brackets):
#   a) the unique letters of "banana", sorted        [['a', 'b', 'n']]
#   b) a dict of word → its length, from a list    [{'hi': 2, 'sun': 3}]
#   c) the two highest numbers in [5, 2, 9, 1, 7]            [[9, 7]]
#      hint: sorted(..., reverse=True)[:2]
#   d) flip {"a": 1, "b": 2} into {1: "a", 2: "b"}
#      hint: a dict comprehension over .items()


# ======================================================================
# 15. GOTCHAS RECAP
# ======================================================================
#  1. b = a                    doesn't copy — both names, one list.
#                              Copy: a.copy() / list(a) / a[:]
#  2. .copy() is shallow       inner lists stay shared → copy.deepcopy()
#  3. lst.sort() returns None  it sorts in place; sorted() returns a list
#  4. append vs extend         append adds ONE item (even a whole list)
#  5. .remove() / .index()     ValueError when the value isn't there
#  6. del lst[2:5]             del can remove a range; pop only one item
#  7. (5) is an int            a one-item tuple is (5,)
#  8. tuples are immutable     item assignment → TypeError
#  9. {} is an empty DICT      an empty set is set()
# 10. sets are unordered       no indexing, print order can surprise you
# 11. d["missing"] → KeyError  use d.get(key) or d.get(key, default)
# 12. for k in my_dict         gives KEYS — use .items() for both
# 13. map / filter / zip       one-shot iterators — list() them once
# 14. zip                      stops at the shortest input
# 15. dict keys / set items    must be immutable: tuple yes, list no
# 16. x in big_list            slow; a set or dict lookup is near-instant
# 17. a generator ( )          one-shot and stores nothing — list() to keep
# 18. {**a, **b}               on duplicate keys the LAST one wins
# 19. * in def vs in a call    def f(*args) COLLECTS, f(*lst) SPREADS
