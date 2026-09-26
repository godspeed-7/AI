# PYTHON BASICS — EXERCISES (files 1–4)
#
# How to use this file:
#   1. Run it:  python3 exercises.py
#      Everything FAILs at first — that's the starting point.
#   2. Replace each  pass  # TODO  with your code.
#   3. Run it again and watch FAIL turn into PASS.
#   4. Stuck? Re-read the notes file listed for that PART below.
#      Compare with exercises_solutions.py only afterwards.
#
#   PART 1  strings & numbers      → 1_primitive_types.py
#   PART 2  conditions & loops     → 2_control_flow.py
#   PART 3  functions              → 3_functions.py
#   PART 4  data structures        → 4_data_structures.py
#   PART 5  mini projects          → everything together
#
# The checker below uses try / except (a later topic) so that one broken
# exercise doesn't stop the rest of the file from running.

_passed = 0
_failed = 0


def check(name, run, expected):
    """Run one attempt and compare it with the expected answer."""
    global _passed, _failed  # see file 3, section 5
    try:
        got = run()
    except Exception as error:
        _failed += 1
        print(f"  ERROR {name}: {type(error).__name__}: {error}")
        return
    if got == expected:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}: got {got!r}, expected {expected!r}")
        # !r shows the value the way Python would write it in code


# ======================================================================
# PART 1 — STRINGS & NUMBERS  (file 1)
# ======================================================================
print("\n===== PART 1 — STRINGS & NUMBERS =====")


# --- 1. clean_name ----------------------------------------------------
# A name typed into a form arrives messy. Tidy it up: no extra spaces,
# each word capitalised.
#   clean_name("  john  DOE ") → "John Doe"
def clean_name(raw):
    return " ".join(raw.split()).title()


check("1 clean_name", lambda: clean_name("  john  DOE "), "John Doe")
check("1 clean_name", lambda: clean_name("ADA lovelace"), "Ada Lovelace")


# --- 2. initials ------------------------------------------------------
# Turn a full name into upper-case initials with dots.
#   initials("ada lovelace") → "A.L."
def initials(full_name):
    temp = ''

    for val in full_name.split():
        temp += f"{val[0].upper()}."

    return temp


check("2 initials", lambda: initials("ada lovelace"), "A.L.")
check("2 initials", lambda: initials("John Ronald Reuel Tolkien"),
      "J.R.R.T.")


# --- 3. format_price --------------------------------------------------
# Format a number as money: thousands separator and exactly 2 decimals.
#   format_price(1234.5) → "₹1,234.50"
def format_price(amount):
    return f"₹{amount:,.2f}"


check("3 format_price", lambda: format_price(1234.5), "₹1,234.50")
check("3 format_price", lambda: format_price(0), "₹0.00")


# --- 4. is_strong_password --------------------------------------------
# A password is strong when it is at least 8 characters long AND has at
# least one digit AND at least one uppercase letter.
#   is_strong_password("Abcdefg1") → True
def is_strong_password(password):
    return len(password) >= 8 and any(char.isdigit() for char in password) and any(char.isupper() for char in password)


check("4 is_strong_password", lambda: is_strong_password("abc"), False)
check("4 is_strong_password", lambda: is_strong_password("abcdefgh"),
      False)
check("4 is_strong_password", lambda: is_strong_password("abcdefg1"),
      False)
check("4 is_strong_password", lambda: is_strong_password("Abcdefg1"),
      True)


# --- 5. seconds_to_clock ----------------------------------------------
# Turn a number of seconds into a clock reading.
#   seconds_to_clock(3725) → "01:02:05"
def seconds_to_clock(total_seconds):
    pass  # TODO


check("5 seconds_to_clock", lambda: seconds_to_clock(3725), "01:02:05")
check("5 seconds_to_clock", lambda: seconds_to_clock(59), "00:00:59")


# ======================================================================
# PART 2 — CONDITIONS & LOOPS  (file 2)
# ======================================================================
print("\n===== PART 2 — CONDITIONS & LOOPS =====")


# --- 6. grade ---------------------------------------------------------
# Convert a score into a grade:
#   below 0 or above 100 → "Invalid"
#   90+ → "A"      75+ → "B"      50+ → "C"      otherwise → "Fail"
def grade(score):
    pass  # TODO


check("6 grade", lambda: grade(95), "A")
check("6 grade", lambda: grade(75), "B")
check("6 grade", lambda: grade(50), "C")
check("6 grade", lambda: grade(20), "Fail")
check("6 grade", lambda: grade(105), "Invalid")
check("6 grade", lambda: grade(-1), "Invalid")


# --- 7. shipping_cost ---------------------------------clear----------------
# Work out the shipping cost for a parcel (weight in whole kg):
#   up to 1 kg → 50        up to 5 kg → 100
#   heavier    → 100 + 20 for every kg above 5
#   express doubles the final cost
def shipping_cost(weight_kg, express=False):
    pass  # TODO


check("7 shipping_cost", lambda: shipping_cost(1), 50)
check("7 shipping_cost", lambda: shipping_cost(3), 100)
check("7 shipping_cost", lambda: shipping_cost(7), 140)
check("7 shipping_cost", lambda: shipping_cost(3, True), 200)


# --- 8. sum_even_digits -----------------------------------------------
# Add up only the even digits of a number.
#   sum_even_digits(123456) → 12      (2 + 4 + 6)
def sum_even_digits(number):
    pass  # TODO


check("8 sum_even_digits", lambda: sum_even_digits(123456), 12)
check("8 sum_even_digits", lambda: sum_even_digits(13579), 0)


# --- 9. longest_word --------------------------------------------------
# Return the longest word in a sentence. On a tie, the FIRST one wins.
#   longest_word("the quick brown fox") → "quick"
def longest_word(sentence):
    pass  # TODO


check("9 longest_word", lambda: longest_word("the quick brown fox"),
      "quick")
check("9 longest_word", lambda: longest_word("a bb ccc"), "ccc")


# --- 10. first_prime_above --------------------------------------------
# Find the first prime number strictly greater than n.
#   first_prime_above(10) → 11
def first_prime_above(n):
    pass  # TODO


check("10 first_prime_above", lambda: first_prime_above(10), 11)
check("10 first_prime_above", lambda: first_prime_above(14), 17)
check("10 first_prime_above", lambda: first_prime_above(1), 2)


# ======================================================================
# PART 3 — FUNCTIONS  (file 3)
# ======================================================================
print("\n===== PART 3 — FUNCTIONS =====")


# --- 11. make_tag -----------------------------------------------------
# Build an HTML tag. Extra keyword arguments become attributes.
#   make_tag("hi")                      → "<p>hi</p>"
#   make_tag("click", "a", href="/x")   → '<a href="/x">click</a>'
def make_tag(text, tag="p", **attrs):
    pass  # TODO


check("11 make_tag", lambda: make_tag("hi"), "<p>hi</p>")
check("11 make_tag", lambda: make_tag("click", "a", href="/x"),
      '<a href="/x">click</a>')
check("11 make_tag", lambda: make_tag("x", "div", id="main", title="t"),
      '<div id="main" title="t">x</div>')


# --- 12. average ------------------------------------------------------
# Average any number of values. No values at all → 0 (not an error).
#   average(2, 4) → 3.0        average() → 0
def average(*numbers):
    pass  # TODO


check("12 average", lambda: average(2, 4), 3.0)
check("12 average", lambda: average(1, 2, 3, 4), 2.5)
check("12 average", lambda: average(), 0)


# --- 13. apply_discount -----------------------------------------------
# Return a NEW list of discounted prices, rounded to 2 decimals.
# The list you were given must stay untouched.
#   apply_discount([100, 200]) → [90.0, 180.0]
def apply_discount(prices, percent=10):
    pass  # TODO


original = [100, 200]
check("13 apply_discount", lambda: apply_discount(original), [90.0, 180.0])
check("13 apply_discount", lambda: apply_discount([100, 200], 50),
      [50.0, 100.0])
check("13 apply_discount keeps the original",
      lambda: original, [100, 200])


# --- 14. add_skill ----------------------------------------------------
# Add a skill to a list and return it. Called without a list, it starts a
# fresh one EVERY time — no leaking between calls.
#   add_skill("python") → ["python"]
#   add_skill("js")     → ["js"]          (not ["python", "js"]!)
#   add_skill("ai", ["python"]) → ["python", "ai"]
def add_skill(skill, skills=None):
    pass  # TODO


check("14 add_skill", lambda: add_skill("python"), ["python"])
check("14 add_skill no leaking", lambda: add_skill("js"), ["js"])
check("14 add_skill", lambda: add_skill("ai", ["python"]),
      ["python", "ai"])


# --- 15. sort_records -------------------------------------------------
# Sort a list of dicts by one field, without changing the original list.
#   sort_records(people, "age") → youngest first
def sort_records(records, field, descending=False):
    pass  # TODO


people = [
    {"name": "John", "age": 22},
    {"name": "Jane", "age": 30},
    {"name": "Bob", "age": 19},
]
check("15 sort_records",
      lambda: [p["name"] for p in sort_records(people, "age")],
      ["Bob", "John", "Jane"])
check("15 sort_records descending",
      lambda: [p["name"] for p in sort_records(people, "age", True)],
      ["Jane", "John", "Bob"])


# ======================================================================
# PART 4 — DATA STRUCTURES  (file 4)
# ======================================================================
print("\n===== PART 4 — DATA STRUCTURES =====")


# --- 16. unique_sorted ------------------------------------------------
# Remove duplicates and sort what's left.
#   unique_sorted([3, 1, 2, 1, 3]) → [1, 2, 3]
def unique_sorted(items):
    pass  # TODO


check("16 unique_sorted", lambda: unique_sorted([3, 1, 2, 1, 3]),
      [1, 2, 3])
check("16 unique_sorted", lambda: unique_sorted(["b", "a", "b"]),
      ["a", "b"])


# --- 17. word_frequency -----------------------------------------------
# Count how often each word appears, ignoring case.
#   word_frequency("The cat the CAT sat")
#       → {"the": 2, "cat": 2, "sat": 1}
def word_frequency(text):
    pass  # TODO


check("17 word_frequency", lambda: word_frequency("The cat the CAT sat"),
      {"the": 2, "cat": 2, "sat": 1})


# --- 18. group_by -----------------------------------------------------
# Group records into a dict: field value → list of names.
#   group_by(staff, "dept") → {"eng": ["John", "Jane"], "sales": ["Bob"]}
def group_by(records, field):
    pass  # TODO


staff = [
    {"name": "John", "dept": "eng"},
    {"name": "Jane", "dept": "eng"},
    {"name": "Bob", "dept": "sales"},
]
check("18 group_by", lambda: group_by(staff, "dept"),
      {"eng": ["John", "Jane"], "sales": ["Bob"]})


# --- 19. merge_settings -----------------------------------------------
# Merge user settings over the defaults, without changing either dict.
#   merge_settings({"theme": "light", "lang": "en"}, {"lang": "hi"})
#       → {"theme": "light", "lang": "hi"}
def merge_settings(defaults, overrides):
    pass  # TODO


check("19 merge_settings",
      lambda: merge_settings({"theme": "light", "lang": "en"},
                             {"lang": "hi"}),
      {"theme": "light", "lang": "hi"})


# --- 20. top_scorers --------------------------------------------------
# Return the names of the n highest scores, best first.
#   top_scorers({"ann": 90, "bob": 75, "cy": 95}, 2) → ["cy", "ann"]
def top_scorers(scores, n):
    pass  # TODO


check("20 top_scorers",
      lambda: top_scorers({"ann": 90, "bob": 75, "cy": 95}, 2),
      ["cy", "ann"])
check("20 top_scorers",
      lambda: top_scorers({"ann": 90, "bob": 75, "cy": 95}, 1), ["cy"])


# --- 21. flatten ------------------------------------------------------
# Flatten a list of lists into one flat list.
#   flatten([[1, 2], [3], [4, 5]]) → [1, 2, 3, 4, 5]
def flatten(matrix):
    pass  # TODO


check("21 flatten", lambda: flatten([[1, 2], [3], [4, 5]]),
      [1, 2, 3, 4, 5])
check("21 flatten", lambda: flatten([]), [])


# ======================================================================
# PART 5 — MINI PROJECTS  (everything together)
# ======================================================================
print("\n===== PART 5 — MINI PROJECTS =====")


# --- 22. parse_log_line -----------------------------------------------
# Split one log line into its three parts. The message itself can
# contain spaces, so only split off the first two fields.
#   parse_log_line("2026-09-24 ERROR Database timeout")
#       → {"date": "2026-09-24", "level": "ERROR",
#          "message": "Database timeout"}
def parse_log_line(line):
    pass  # TODO


check("22 parse_log_line",
      lambda: parse_log_line("2026-09-24 ERROR Database timeout"),
      {"date": "2026-09-24", "level": "ERROR",
       "message": "Database timeout"})


# --- 23. summarise_orders ---------------------------------------------
# From a list of orders, return:
#   total → the value of all orders (qty * price, added up)
#   items → how many orders there were
#   best  → the product with the highest line value
#   summarise_orders(orders) → {"total": 860, "items": 3, "best": "book"}
def summarise_orders(orders):
    pass  # TODO


orders = [
    {"product": "pen", "qty": 3, "price": 20},
    {"product": "book", "qty": 1, "price": 500},
    {"product": "bag", "qty": 2, "price": 150},
]
check("23 summarise_orders", lambda: summarise_orders(orders),
      {"total": 860, "items": 3, "best": "book"})


# --- 24. clean_rows ---------------------------------------------------
# Clean a column of messy names for a dataset: trim the spaces,
# capitalise, drop the empty ones, and remove duplicates while keeping
# the original order.
#   clean_rows(["  Ann ", "bob", "ANN", "", "  ", "Bob"])
#       → ["Ann", "Bob"]
def clean_rows(rows):
    pass  # TODO


check("24 clean_rows",
      lambda: clean_rows(["  Ann ", "bob", "ANN", "", "  ", "Bob"]),
      ["Ann", "Bob"])
check("24 clean_rows", lambda: clean_rows([]), [])


# ======================================================================
# SCORE
# ======================================================================
print("\n" + "=" * 60)
print(f"{_passed} passed, {_failed} still to do")
