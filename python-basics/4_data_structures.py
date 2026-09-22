# Data structures

# Lists

from array import array
from collections import deque
print('Lists --------------------------------------------------------------------------------------------------------')
letters = ['a', 'b', 'c', 'd', 'e']
print(f"letters: {letters}")
matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
print(f"matrix: {matrix}")
zeroes = [0] * 5
print(f"zeroes: {zeroes}")
combined = zeroes + letters
print(f"combined: {combined}")
numbers = list(range(20))
print(f"numbers: {numbers}")
chars = list('Hello World')
print(f"chars: {chars}")
print(f"Length of letters: {len(chars)}")


numbers = list(range(20))
print(f"numbers: {numbers[::2]}")  # Even numbers
print(f"numbers: {numbers[1::2]}")  # Odd numbers
print(f"numbers: {numbers[::-1]}")  # Reverse the list

print(f"numbers: {numbers[::3]}")  # Every third number


# looping through a list
print('looping through a list --------------------------------------------------------------------------------------------------------')
letters = ['a', 'b', 'c', 'd', 'e']
for letter in letters:
    print(f"letter: {letter}")


# enumarate function
print('enumarate function --------------------------------------------------------------------------------------------------------')
letters = ['a', 'b', 'c', 'd', 'e']
for index, letter in enumerate(letters):
    print(f"index: {index}, letter: {letter}")


# adding and removing elements from a list
print('adding and removing elements from a list --------------------------------------------------------------------------------------------------------')
letters = ['a', 'b', 'c', 'd', 'e']
# adding elements
letters.append('f')  # add at the end
letters.insert(0, 'z')  # add at the beginning
print(f"letters after append: {letters}")
# remove elements
letters.remove('c')  # remove by value
print(f"letters after remove: {letters}")
letters.pop()  # remove last element
print(f"letters after pop: {letters}")
letters.pop(0)  # remove element at index 0
print(f"letters after pop(0): {letters}")

del letters[0]  # remove element at index 0
print(f"letters after del: {letters}")

# with delete we can remove range of elements, where with pop we can only remove one element at a time

letters.clear()  # remove all elements
print(f"letters after clear: {letters}")


# finding elements in a list
print('finding elements in a list --------------------------------------------------------------------------------------------------------')
letters = ['a', 'b', 'c', 'd', 'e']
print(f"index of 'c': {letters.index('c')}")  # find index
print(f"'c' in letters: {'c' in letters}")  # check if element exists
print(f"count of 'c': {letters.count('c')}")  # count


# check element exists in a list
if 'c' in letters:
    print(f"'c' exists in letters")


# sorting a list
print('sorting a list --------------------------------------------------------------------------------------------------------')
numbers = [5, 2, 9, 1, 5, 6]
numbers.sort()  # sort in ascending order
print(f"numbers after sort: {numbers}")

# sort in ascending order and return a new list
sorted_numbers = sorted(numbers)
print(f"sorted_numbers: {sorted_numbers}")

# sorted returns a new list, while sort() modifies the original list in place.
# with both methods we can alwasy change the sort method to descending order by passing reverse=True as an argument.

numbers.sort(reverse=True)  # sort in descending order
print(f"numbers after sort (descending): {numbers}")

# custom sort example

items = [('apple', 5), ('banana', 2), ('cherry', 9)]


def sort_item(item):
    return item[1]  # sort by the second element of each tuple


items.sort(key=sort_item)  # sort by the second element of each tuple
print(f"items after custom sort: {items}")

# lambda function example
items = [('apple', 5), ('banana', 2), ('cherry', 9)]
items.sort(key=lambda item: item[1])  # sort by the second element
print(f"items after custom sort with lambda: {items}")


# map functions
print('map functions --------------------------------------------------------------------------------------------------------')
items = [('apple', 5), ('banana', 2), ('cherry', 9)]
# map returns a map object, which is an iterator
x = map(lambda item: item[1], items)

for item in x:
    print(f"item: {item}")


# we can also convert the map object to a list
x = map(lambda item: item[1], items)
print(f"x as list: {list(x)}")


# filter functions
print('filter functions --------------------------------------------------------------------------------------------------------')
items = [('apple', 5), ('banana', 2), ('cherry', 9)]
# filter returns a filter object, which is an iterator
x = filter(lambda item: item[1] >= 5, items)
print(f"x as list: {list(x)}")  # convert to list and print


# list comprehensions
print('list comprehensions --------------------------------------------------------------------------------------------------------')
items = [('apple', 5), ('banana', 2), ('cherry', 9)]
# list comprehension is a concise way to create lists
# [expression for item in iterable if condition]
x = [item[1] for item in items]  # get the second element of each tuple


# get the second element of each tuple if it is greater than or equal to 5
y = [item[1] for item in items if item[1] >= 5]
print(f"x: {x}")
print(f"y: {y}")


# zip functions
print('zip functions --------------------------------------------------------------------------------------------------------')

names = ['apple', 'banana', 'cherry']
names2 = ['orange', 'grape', 'kiwi']

zipped = list(zip(names, names2))
print(f"zipped: {zipped}")

# stacks
print('stacks --------------------------------------------------------------------------------------------------------')
stack = []
stack.append(1)
stack.append(2)
stack.append(3)
print(f"stack: {stack}")
stack.pop()
print(f"stack after pop: {stack}")
stack[-1]  # peek at the last element without removing it

# queues
print('queues --------------------------------------------------------------------------------------------------------')
queue = deque([])
queue.append(1)
queue.append(2)
queue.append(3)
print(f"queue: {queue}")
queue.popleft()
print(f"queue after popleft: {queue}")

# tuples
print('tuples --------------------------------------------------------------------------------------------------------')
point = (1, 2)
print(f"point: {point}")

print(f"concatenated: {point + (3, 4)}")  # concatenation
print(f"repeated: {point * 2}")  # repetition

# arrays
# arrays to be only used when we need to store large amount of data and we want to save memory.
# Otherwise, lists are more flexible and easier to use.
print('arrays --------------------------------------------------------------------------------------------------------')
# 'i' is the type code for signed integers
numbers = array('i', [1, 2, 3, 4, 5])
print(f"numbers: {numbers}")


# Sets
print('Sets --------------------------------------------------------------------------------------------------------')
numbers = {1, 2, 3, 4, 5}
print(f"numbers: {numbers}")

# adding and removing elements from a set
numbers.add(6)
print(f"numbers after add: {numbers}")
numbers.remove(3)
print(f"numbers after remove: {numbers}")

# checking if an element exists in a set
print(f"3 in numbers: {3 in numbers}")

# set operations
evens = {2, 4, 6, 8}
odds = {1, 3, 5, 7}
print(f"evens union odds: {evens.union(odds)}")  # even | odd
print(f"evens intersection odds: {evens.intersection(odds)}")  # even & odd
print(f"evens difference odds: {evens.difference(odds)}")  # even - odd

# even ^ odd
print(f"evens symmetric difference odds: {evens.symmetric_difference(odds)}")


# Dictionaries
print('Dictionaries --------------------------------------------------------------------------------------------------------')
point = {'x': 1, 'y': 2}
print(f"point: {point}")

# adding and removing elements from a dictionary
point['z'] = 3
print(f"point after add: {point}")
del point['x']
print(f"point after delete: {point}")

# checking if a key exists in a dictionary
print(f"'x' in point: {'x' in point}")
# getting a value from a dictionary
print(f"point['y']: {point['y']}")
print(f"point.get('y'): {point.get('y')}")  # returns None if key doesn't exist
# returns 0 if key doesn't exist
print(f"point.get('y', 0): {point.get('y', 0)}")
