# CLASSES IN PYTHON — quick reference notes
#
#    1. Class & object        class · __init__ · self · attributes
#    2. Instance vs class     shared data · the mutable attribute trap
#    3. Methods               instance · @classmethod · @staticmethod
#    4. Magic methods         __str__ vs __repr__ · __eq__ · __add__
#    5. Container protocol    __len__ · __getitem__ · __contains__
#    6. Private members       _one underscore · __two (name mangling)
#    7. Properties            @property getter · setter with validation
#    8. Inheritance           override · super() · isinstance · levels
#    9. Abstract classes      ABC + @abstractmethod
#   10. Polymorphism          one call, many classes · duck typing
#   11. Extending built-ins   class Text(str)
#   12. Data classes          @dataclass · frozen · namedtuple
#   13. Gotchas recap         every surprise from this file in one list
#
# How to read this file:
#   # →       what the line prints (under a block: what the block prints)
#   # ❌      the line would raise an error, so it is commented out
#   GOTCHA    surprising behaviour — search for "GOTCHA" to review them all
#
# Coming from JavaScript:
#   class X { }          → class X:
#   constructor()        → def __init__(self, ...)
#   this                 → self   (explicit, always the 1st parameter)
#   extends Parent       → class Child(Parent):
#   super()              → super().__init__(...)
#   static method()      → @classmethod / @staticmethod
#   get x() / set x(v)   → @property / @x.setter
#   toString()           → __str__  (and __repr__ for developers)
#   #privateField        → _name (a hint) or __name (name-mangled)
#   obj instanceof X     → isinstance(obj, X)

from abc import ABC, abstractmethod
from collections import namedtuple
from dataclasses import dataclass


# ======================================================================
# 1. CLASS & OBJECT
# ======================================================================
# A class is the blueprint; an object is one thing built from it.
#   class Human  →  objects jack, mary, jan
print("\n===== 1. CLASS & OBJECT =====")


class Point:
    """A point on a 2D grid."""  # docstring (file 3, section 1)

    def __init__(self, x, y):   # the constructor
        self.x = x              # instance attributes
        self.y = y

    def draw(self):             # an instance method
        print(f"Point({self.x}, {self.y})")


point = Point(1, 2)  # calling the class runs __init__
point.draw()         # → Point(1, 2)
print(point.x)       # → 1
print(type(point))   # → <class '__main__.Point'>
print(isinstance(point, Point))  # → True

# `self` is the object itself, handed over automatically.
# Python spells it out; JavaScript hides it as `this`.
# So  point.draw()  really means  Point.draw(point):
Point.draw(point)  # → Point(1, 2)

# Python lets you bolt on new attributes from outside, too
point.z = 3
print(point.z)  # → 3


# ======================================================================
# 2. INSTANCE VS CLASS ATTRIBUTES
# ======================================================================
print("\n===== 2. INSTANCE VS CLASS ATTRIBUTES =====")


class Dog:
    species = "Canis familiaris"  # CLASS attribute → shared by all dogs

    def __init__(self, name):
        self.name = name          # INSTANCE attribute → one per dog


rex = Dog("Rex")
bela = Dog("Bela")
print(rex.name, bela.name)        # → Rex Bela                  different
print(rex.species == bela.species)  # → True                    shared
print(Dog.species)  # → Canis familiaris   reachable on the class itself

# Assigning through an object creates a NEW instance attribute —
# it does not touch the class attribute
rex.species = "Good boy"
print(rex.species, bela.species)  # → Good boy Canis familiaris


# GOTCHA: a MUTABLE class attribute is shared by everyone — the same
# trap as a mutable default argument (file 3, section 3)
class Basket:
    items = []  # ← one single list for every basket ever made

    def add(self, item):
        self.items.append(item)


first = Basket()
second = Basket()
first.add("apple")
print(second.items)  # → ['apple']   the other basket sees it too!
# Fix: create it per object, inside __init__ →  self.items = []


# ======================================================================
# 3. METHODS
# ======================================================================
print("\n===== 3. METHODS =====")


class Circle:
    def __init__(self, radius):
        self.radius = radius

    def area(self):          # instance method → works on one object
        return 3.14 * self.radius ** 2

    @classmethod
    def unit(cls):           # class method → receives the CLASS
        return cls(1)        # a "factory": builds and returns an object

    @staticmethod
    def describe():          # no self, no cls — just a function that
        return "a round shape"  # lives in the class for tidiness


circle = Circle(2)
print(circle.area())           # → 12.56
print(Circle.unit().radius)    # → 1    factory method, no object needed
print(Circle.describe())       # → a round shape
# JS: @classmethod and @staticmethod both look like `static` methods


# ======================================================================
# 4. MAGIC METHODS
# ======================================================================
# Methods named __like_this__ hook your class into Python's syntax.
print("\n===== 4. MAGIC METHODS =====")


class Money:
    def __init__(self, amount):
        self.amount = amount

    def __str__(self):   # print() and str()  → for humans
        return f"₹{self.amount}"

    def __repr__(self):  # the shell, and lists → for developers
        return f"Money({self.amount})"

    def __eq__(self, other):  # makes  a == b  work
        if not isinstance(other, Money):
            return NotImplemented  # "I can't compare these"
        return self.amount == other.amount

    def __gt__(self, other):  # makes  a > b  work
        return self.amount > other.amount

    def __add__(self, other):  # makes  a + b  work
        return Money(self.amount + other.amount)


ten = Money(10)
also_ten = Money(10)
print(ten)             # → ₹10         uses __str__
print(repr(ten))       # → Money(10)   uses __repr__
print([ten])           # → [Money(10)]  lists always use __repr__
print(ten == also_ten)  # → True       without __eq__ this would be False
print(ten > Money(5))  # → True
print(ten + also_ten)  # → ₹20
print(ten == "10")     # → False   NotImplemented → Python falls back

# Without __str__ / __repr__ you get <__main__.Money object at 0x...>
#
# Worth knowing:  __init__ __str__ __repr__ __eq__ __lt__ __gt__
#                 __add__ __len__ __getitem__ __contains__ __iter__
#
# GOTCHA: defining __eq__ makes your objects unhashable — they can't go
# in a set or be used as dict keys until you also define __hash__.


# ======================================================================
# 5. CONTAINER PROTOCOL
# ======================================================================
# Implement a few magic methods and your class behaves like a dict/list.
print("\n===== 5. CONTAINER PROTOCOL =====")


class TagCloud:
    def __init__(self):
        self.tags = {}

    def add(self, tag):
        key = tag.lower()
        self.tags[key] = self.tags.get(key, 0) + 1

    def __getitem__(self, tag):          # cloud["python"]
        return self.tags.get(tag.lower(), 0)

    def __setitem__(self, tag, count):   # cloud["python"] = 5
        self.tags[tag.lower()] = count

    def __len__(self):                   # len(cloud)
        return len(self.tags)

    def __contains__(self, tag):         # "python" in cloud
        return tag.lower() in self.tags

    def __iter__(self):                  # for tag in cloud
        return iter(self.tags)


cloud = TagCloud()
cloud.add("Python")
cloud.add("python")
cloud.add("Java")
print(cloud["PYTHON"])  # → 2      lower() on both sides, so it matches
print(cloud["ruby"])    # → 0      missing tags answer 0, not KeyError
print(len(cloud))       # → 2
print("java" in cloud)  # → True
cloud["Go"] = 7
print(cloud["go"])      # → 7
print(list(cloud))      # → ['python', 'java', 'go']


# ======================================================================
# 6. PRIVATE MEMBERS
# ======================================================================
# Python has no real `private`. It has two conventions.
print("\n===== 6. PRIVATE MEMBERS =====")


class Account:
    def __init__(self):
        self._bank = "HDFC"  # one _  → "internal, please leave alone"
        self.__pin = 1234    # two __ → renamed behind the scenes


account = Account()
print(account._bank)  # → HDFC   nothing stops you; it's a polite hint
# print(account.__pin)  # ❌ AttributeError: 'Account' object has no
#                       #    attribute '__pin'
print(account._Account__pin)  # → 1234   renamed, not locked away
# The __ version ("name mangling") exists to avoid clashes with
# subclasses, not to provide security.


# ======================================================================
# 7. PROPERTIES
# ======================================================================
# A property looks like an attribute from outside, but runs a method —
# so you can validate a value instead of trusting it.
print("\n===== 7. PROPERTIES =====")


class Product:
    def __init__(self, price):
        self.price = price  # this already goes through the setter below

    @property
    def price(self):        # getter →  product.price
        return self.__price

    @price.setter
    def price(self, value):  # setter →  product.price = 20
        if value < 0:
            raise ValueError("price cannot be negative")
        self.__price = value


product = Product(10)
print(product.price)  # → 10    reads like an attribute
product.price = 20
print(product.price)  # → 20
try:
    product.price = -5
except ValueError as error:
    print(error)  # → price cannot be negative

# Why: start with a plain attribute. If you later need validation, a
# property adds it without changing any code that uses the class.
# JS equivalent: get price() / set price(value)


# ======================================================================
# 8. INHERITANCE
# ======================================================================
print("\n===== 8. INHERITANCE =====")


class Animal:  # parent / base class
    def __init__(self, name):
        self.name = name

    def eat(self):
        print(f"{self.name} eats")

    def speak(self):
        print("...")


class Cat(Animal):  # child / subclass
    def __init__(self, name, indoor=True):
        super().__init__(name)  # run the parent's __init__ first
        self.indoor = indoor    # then add our own

    def speak(self):            # OVERRIDES Animal.speak
        print(f"{self.name} says meow")

    def nap(self):              # and adds something new
        print("naps for 14 hours")


cat = Cat("Bela")
cat.eat()    # → Bela eats              inherited unchanged
cat.speak()  # → Bela says meow         overridden
cat.nap()    # → naps for 14 hours      only on Cat
print(cat.indoor)  # → True

print(isinstance(cat, Cat))      # → True
print(isinstance(cat, Animal))   # → True   a Cat IS an Animal
print(issubclass(Cat, Animal))   # → True

# GOTCHA: forget super().__init__(name) and self.name is never set —
# you get an AttributeError the first time something uses it.


# --- Multi-level: extend the parent's version instead of replacing it -
class LoudCat(Cat):  # Animal → Cat → LoudCat
    def speak(self):
        super().speak()   # do what Cat does...
        print("MEOW!!!")  # ...then add to it


LoudCat("Rex").speak()
# → Rex says meow
#   MEOW!!!

# Multiple inheritance exists too:  class Manager(Employee, Person).
# Python looks for a method left to right; Cat.__mro__ shows the order.
print(LoudCat.__mro__[:3])
# → (<class '__main__.LoudCat'>, <class '__main__.Cat'>,
#    <class '__main__.Animal'>)


# ======================================================================
# 9. ABSTRACT CLASSES
# ======================================================================
# An abstract class can't be created directly, and it forces its
# subclasses to implement the methods it marks as abstract.
print("\n===== 9. ABSTRACT CLASSES =====")


class UIControl(ABC):  # ← inheriting ABC is what makes it abstract
    @abstractmethod
    def draw(self):
        ...  # no body needed — subclasses must write it


class TextBox(UIControl):
    def draw(self):
        print("TextBox drawn")


TextBox().draw()  # → TextBox drawn

try:
    UIControl()
except TypeError as error:
    print(f"blocked: {error}")
# → blocked: Can't instantiate abstract class UIControl without an
#   implementation for abstract method 'draw'


# GOTCHA: @abstractmethod on its own does NOTHING. Without (ABC) the
# class is an ordinary class and this would have worked silently:
class NotReallyAbstract:  # ← forgot (ABC)
    @abstractmethod
    def draw(self):
        ...


NotReallyAbstract()  # no error at all
print("no error — @abstractmethod needs (ABC) to have any effect")


# ======================================================================
# 10. POLYMORPHISM & DUCK TYPING
# ======================================================================
# Same call, different behaviour per class. No switch statement needed.
print("\n===== 10. POLYMORPHISM =====")


class DropDown(UIControl):
    def draw(self):
        print("DropDown drawn")


def render_all(controls):
    for control in controls:
        control.draw()  # each object does its own thing


render_all([TextBox(), DropDown()])
# → TextBox drawn
#   DropDown drawn


# Duck typing: "if it walks like a duck and quacks like a duck..."
# Python doesn't check the class, only that the method exists.
class Duck:  # not a UIControl at all
    def draw(self):
        print("Duck drawn")


render_all([Duck()])  # → Duck drawn   works anyway


# ======================================================================
# 11. EXTENDING BUILT-IN TYPES
# ======================================================================
print("\n===== 11. EXTENDING BUILT-INS =====")


class Text(str):  # inherits every str method
    def duplicate(self):
        return self + self


text = Text("Python")
print(text.duplicate())        # → PythonPython
print(text.upper())            # → PYTHON   all str methods still work
print(type(text.duplicate()))  # → <class 'str'>
# GOTCHA: + returns a plain str, not a Text — built-in operations don't
# know about your subclass.


class TrackedList(list):
    def push(self, item):  # a JS-style name for append
        self.append(item)


items = TrackedList([1, 2])
items.push(3)
print(items)  # → [1, 2, 3]


# ======================================================================
# 12. DATA CLASSES
# ======================================================================
# Writing __init__ + __repr__ + __eq__ by hand gets old fast.
print("\n===== 12. DATA CLASSES =====")


@dataclass
class Coord:
    x: int      # type hints (file 3, section 8) describe the fields
    y: int = 0  # defaults work as usual


first = Coord(1, 2)
second = Coord(1, 2)
print(first)           # → Coord(x=1, y=2)   __repr__ written for you
print(first == second)  # → True             __eq__ written for you
first.x = 5            # still a normal, mutable object
print(first.x)         # → 5


@dataclass(frozen=True)  # frozen → immutable, and hashable
class FrozenCoord:
    x: int
    y: int


frozen = FrozenCoord(1, 2)
print(frozen)  # → FrozenCoord(x=1, y=2)
# frozen.x = 5   # ❌ FrozenInstanceError: cannot assign to field 'x'
print({frozen})  # → {FrozenCoord(x=1, y=2)}   usable in a set

# namedtuple — the older, lighter option: a tuple with named fields
Pair = namedtuple("Pair", ["x", "y"])
pair = Pair(x=1, y=2)
print(pair, pair.x, pair[0])  # → Pair(x=1, y=2) 1 1
print(pair == Pair(1, 2))     # → True   compares by value
# GOTCHA: the first version of this file wrote Point = namedtuple(...),
# which silently replaced the Point class defined at the top. Reusing a
# name doesn't error, it just overwrites.
#
# Choosing: @dataclass for most things, frozen=True when it must not
# change, namedtuple when you want a plain tuple with names.


# ======================================================================
# 13. GOTCHAS RECAP
# ======================================================================
#  1. self                      every instance method takes it first
#  2. class attribute = []      shared by ALL objects → set it in
#                               __init__ instead
#  3. obj.attr = x              creates an instance attribute; the class
#                               attribute is untouched
#  4. forgetting super()        parent __init__ never runs → missing
#                               attributes
#  5. @abstractmethod alone     does nothing without (ABC)
#  6. __str__ vs __repr__       humans vs developers; lists use __repr__
#  7. defining __eq__           makes objects unhashable until you add
#                               __hash__
#  8. self.__x                  not private, just renamed to _Class__x
#  9. property                  self.price = x in __init__ already runs
#                               the setter
# 10. class Text(str)           str operations give back plain str
# 11. Point = namedtuple(...)   overwrites any Point class of that name
# 12. the class body            runs once, when the file loads;
#                               __init__ runs once per object
