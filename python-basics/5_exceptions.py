# Excetions

# Handling Exceptions
try:
    age = int(input('enter yor age'))
    xfactor = 10 / age
except ValueError as ex:
    print('You enterted an invalid age')
    print(f'Detailed log - {ex}')
except ZeroDivisionError:
    print('age cannot be zero')
else:
    print('no exception was thrown')
print('Eecution continues from here.')

# finally block
try:
    file = open('a.txt')
except ValueError as ex:
    print(f'Detailed log - {ex}')
else:
    print('no exception was thrown')
finally:
    file.close()

# With statement
# it automaticllay rlease the resources

try:
    with open('a.txt') as file:
        print('file opened')
except ValueError as ex:
    print(f'Detailed log - {ex}')
else:
    print('no exception was thrown')

# Raisng exceptions


def calculate_age(age):
    if age < 0:
        raise ValueError('age cannot be less then zero')


try:
    calculate_age(0)
except ValueError as ex:
    print(f'error - {ex}')


# cost of raising exceptions

# use timneit module to measure
# timeit(codeblock, number of times to excute code)
