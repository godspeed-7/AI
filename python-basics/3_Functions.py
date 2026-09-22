# functions

# basic non-returning function
print("basic non-returning function ----------------------------------------------------------------")


def greet(first_name, last_name):
    print(f"hello and welcome {first_name} {last_name}")


greet("john", "doe")


# basic returning function
print("basic returning function ----------------------------------------------------------------")


def get_name(first_name):
    return f"Hi {first_name}"


name = get_name("John")
print(name)

# xargs example

print("xargs ----------------------------------------------------------------")


def multiply(*numbers):
    total = 1
    for num in numbers:
        total *= num
    return total


print(multiply(2, 3, 4, 5))

# xxargs example
print("xxargs ----------------------------------------------------------------")


def save_user(**user):
    print(user)


save_user(id=1, name="john", age=22)


# exercise for fizzbuzz
def fizz_buzz(input):
    if input % 3 == 0 and input % 5 == 0:
        return 'fizzbuzz'
    if input % 3 == 0:
        return 'fizz'
    if input % 5 == 0:
        return 'buzz'
    else:
        return input


print(fizz_buzz(15))
