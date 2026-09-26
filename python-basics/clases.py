# clases

# class: blueprint for creating new objects
# object: instance of a class


# class: Human
# object: jack, mary, jan


class Point:
    default_color = 'red'

    @classmethod
    def zero(cls):
        return cls(0, 0)

    def __str__(self):
        return f"({self.x} {self.y})"

    def __eq__(self, value):
        return self.x == value.x and self.y == value.y

    def __gt__(self, other):
        return self.x > other.x and self.y > other.y

    def __add__(self, other):
        return Point(self.x + other.x, self.y + other.y)

    def __init__(self, x, y):
        self.x = x
        self.y = y

    def draw(self):
        print(f'draw ({self.x} {self.y})')


point = Point(1, 2)

point.draw()

print(type(point))
print(isinstance(point, Point))
print(point.x)
print(point.default_color)
print(Point.default_color)


# Consturctors

# we define constructor with __init__

# we use

# Instance vs class attributes

# instance attributes are shared among all the attributes
# for example in above class Point, x and y are instance attributs which are shared by all he instances

# class attributes

# class level instances are shared amoing all the instances of the class.
# in above example we have default_color as the class attribute, which can be accessed by an object or class


# insance vs class methods

# zero is an example of class emthod, whuch is called via the class, this is also called as the factory method

# point = Point.zero()

# point.draw()

# Magic methods

# earlier we were getting a address pronetd when we tried to print the obejct , but after this __str__magic methd we get proper details
# print(point)


# comaring objects

point2 = Point(1, 3)

print(point == point2)
print(point > point2)
print(point + point2)


# making custom container
class TagCloud:
    def __init__(self):
        self.tags = {}

    def add(self, tag):
        self.tags[tag.lower()] = self.tags.get(tag.lower(), 0) + 1

    def __getitem__(self, tag):
        return self.tags.get(tag, 0)

    def __setitem__(self, tag, value):
        self.tags[tag] = value

    def __len__(self):
        return len(self.tags)


cloud = TagCloud()
cloud.add('python')
cloud.add('java')

print(cloud.tags)
print(cloud['java'])

# private members

# to make an prvate we have to add __ in fornt of an instance variable, for example
#      self.__tags = {} // this is now private


# Properties

# normally we set value in constuctor, but suppose someone sets an invalid value then its an problem
# to solve it we can use the getter asnd setters funciton, whil emaking the instance member as private
# and we inside setter we cna have any validatins to get the right value as an input
# also there is still a inbuilt properrty function which takes setters and getters as input


class Product:
    def __init__(self, price):
        self.price = price

    @property
    def price(self):
        return self.__price

    @price.setter
    def price(self, value):
        if value < 0:
            raise ValueError('price cannot be nagative')
        self.__price = value


product = Product(10)
print(product.price)

# Inheritance
