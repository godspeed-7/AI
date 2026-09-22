import math


# ----------------------------------------------------------------------------------------------------------------------------------------------------
# Primitive Types in Python
# ----------------------------------------------------------------------------------------------------------------------------------------------------
student_count = 1000  # number
rating = 4.5  # float
is_active = True  # boolean
name = "John Doe"  # string


# STRINGS ----------------------------------------------------------------------------------------------------------

course = "Python Programming"
print(f"Length: {len(course)}")  # Length of the string
print(f"First character: {course[0]}")  # First character
print(f"Last character: {course[-1]}")  # Last character
# Substring from index 0 to 5, chaeacter at the end index is not included
print(f"Substring [0:6]: {course[0:6]}")
print(f"Substring [0:]: {course[0:]}")  # Substring from index 0 to the end
print(f"Substring [:6]: {course[:6]}")  # Substring from the start to index 6
print(f"Substring [:]: {course[:]}")  # returns copy of the string
print(f"Substring [::2]: {course[::2]}")  # Every second character
print(f"Substring [::-1]: {course[::-1]}")  # Reverse the string


print(course.split(" "))     # string → list
print("-".join(["a", "b"]))   # list → string  (join is on the separator!)
print(course.startswith("py"))
# membership — cleaner than .find() for yes/no checks
print("pro" in course)

# Strings are immutable. Every method (.upper(), .replace()) returns a new string — it never changes the original. Worth a one-line comment, because it's a JS-familiar idea but Python people trip on expecting in-place changes:


# Escape sequences -------------------------------------------------------------------------------------------------

# \"
# \'
# \\
# \n
print("Escape Sequences -----------------------------------------------------------------")
course = "Python \"Programming\""  # To include a double quote in the string
print(f"course: {course}")


# Formatted Strings -------------------------------------------------------------------------------------------------
print("Formatted Strings -----------------------------------------------------------------")
first = "John"
last = "Doe"
full_name = f"{first} {last}"  # Using f-string for formatting
print(f"full_name: {full_name}")


# String Methods -------------------------------------------------------------------------------------------------
print("String Methods -----------------------------------------------------------------")
course = "pyrthon programming"
print(f"Uppercase: {course.upper()}")  # Convert to uppercase
print(f"Lowercase: {course.lower()}")  # Convert to lowercase
print(f"Title case: {course.title()}")  # Convert to title case
print(f"Stripped: {course.strip()}")  # Remove leading and trailing whitespace
# Find the index of a substring
print(f"Find 'pro': {course.find('pro')}")
# Replace a substring
print(f"Replace 'python' with 'java': {course.replace('python', 'java')}")

# Numbers -------------------------------------------------------------------------------------------------
print("Numbers -----------------------------------------------------------------")
print(f"10 + 3: {10 + 3}")  # Addition
print(f"10 - 3: {10 - 3}")  # Subtraction
print(f"10 * 3: {10 * 3}")  # Multiplication
print(f"10 / 3: {10 / 3}")  # Division
print(f"10 // 3: {10 // 3}")  # Floor Division
print(f"10 % 3: {10 % 3}")  # Modulus
print(f"10 ** 3: {10 ** 3}")  # Exponentiation

# Number Methods -------------------------------------------------------------------------------------------------
print("Number Methods -----------------------------------------------------------------")
x = 10.5
print(f"Round: {round(x)}")  # Round to nearest integer
print(f"Absolute: {abs(-x)}")  # Absolute value
print(f"Ceiling: {math.ceil(x)}")  # Ceiling
print(f"Floor: {math.floor(x)}")  # Floor


# Type Conversion -------------------------------------------------------------------------------------------------
print("Type Conversion -----------------------------------------------------------------")
x = 10  # int
y = 3.5  # float
# Convert int to float
x_float = float(x)
print(f"x_float: {x_float} (type: {type(x_float)})")
# Convert float to int
y_int = int(y)
print(f"y_int: {y_int} (type: {type(y_int)})")
# Convert int to string
x_str = str(x)
print(f"x_str: {x_str} (type: {type(x_str)})")
# CONVERT TO BOOLEAN
x_bool = bool(x)
print(f"x_bool: {x_bool} (type: {type(x_bool)})")
# FALSY VALUES: 0, 0.0, "", None, [], {}, set(), False
print(f"Falsy value: {bool(0)}")
print(f"Falsy value: {bool(0.0)}")
print(f"Falsy value: {bool('')}")
print(f"Falsy value: {bool(None)}")
