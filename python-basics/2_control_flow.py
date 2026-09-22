# comparison comparison

print("comparison comparison -----------------------------------------------------------------")
a = 10
b = 20
text = 'programming'
print(f"a == b: {a == b}")  # Equal to
print(f"a != b: {a != b}")  # Not equal to
print(f"a > b: {a > b}")  # Greater than
print(f"a < b: {a < b}")  # Less than
print(f"a >= b: {a >= b}")  # Greater than or equal to
print(f"a <= b: {a <= b}")  # Less than or equal to
print(f"string equality : {text == 'Programming'}")  # String comparison


# conditional statements
print("conditional statements -----------------------------------------------------------------")
x = 10
if x > 0:
    print("x is positive")
elif x < 0:
    print("x is negative")
else:
    print("x is zero")


# ternary operator
print("ternary operator -----------------------------------------------------------------")
age = 18
status = "Adult" if age >= 18 else "Minor"
print(f"status: {status}")


# logical operators [and, or, not]
print("logical operators -----------------------------------------------------------------")
high_income = True
good_credit = True
student = True
# Logical AND
if high_income and good_credit:
    print("Eligible for loan")
# Logical OR
if high_income or good_credit:
    print("Eligible for loan")

if high_income and good_credit and not student:
    print("Eligible for loan")

# short circuit evaluation
# in case of and operator, if the first condition is false, the second condition is not evaluated.
# In case of or operator, if the first condition is true, the second condition is not evaluated.
print("short circuit evaluation -----------------------------------------------------------------")
high_income = True
good_credit = False
if high_income and good_credit:
    print("Eligible for loan")


# chaining comparison operators
print("chaining comparison operators -----------------------------------------------------------------")
age = 10
if 0 < age < 20:
    print("age is between 0 and 20")

# for loop
print("for loop -----------------------------------------------------------------")
for i in range(5):
    print(f"i: {i}")
    if i == 3:
        print("Breaking the loop")
        break  # exit the loop when i is 3


# for loop with else
print("for loop with else -----------------------------------------------------------------")
for i in range(5):
    print(f"i: {i}")
else:
    print("Loop completed without break")


# Nested loops
print("Nested loops -----------------------------------------------------------------")
for i in range(3):
    for j in range(3):
        print(f"i: {i}, j: {j}")

# while loop
print("while loop -----------------------------------------------------------------")
count = 0
while count < 5:
    print(f"count: {count}")
    count += 1


# exercise: print even numbers from 1-10exerciese print even number from 1-10
count = 0
for i in range(1, 10):
    if (i % 2 == 0):
        print(f"even number {i}")
        count += 1
print(f"total even numbers found: {count}")
