First you need to import the library:

import capnp Then you can load the Cap’n Proto schema with:

import addressbook_capnp This will look all through all the directories in
your sys.path/PYTHONPATH, and try to find a file of the form
‘addressbook.capnp’. If you want to disable the import hook magic that import
capnp adds, and load manually, here’s how:

capnp.remove_import_hook() addressbook_capnp = capnp.load('addressbook.capnp')
For future reference, here is the Cap’n Proto schema. Also available in the
github repository under examples/addressbook.capnp:

# addressbook.capnp

@0x934efea7f017fff0;

const qux :UInt32 = 123;

struct Person { id @0 :UInt32; name @1 :Text; email @2 :Text; phones @3
:List(PhoneNumber);

struct PhoneNumber { number @0 :Text; type @1 :Type;

    enum Type {
      mobile @0;
      home @1;
      work @2;
    }

}

employment :union { unemployed @4 :Void; employer @5 :Text; school @6 :Text;
selfEmployed @7 :Void; # We assume that a person is only one of these. } }

struct AddressBook { people @0 :List(Person); } Const values Const values show
up just as you’d expect under the loaded schema. For example:

print addressbook_capnp.qux

# 123

Build a message Initialize a New Cap’n Proto Object Now that you’ve imported
your schema, you need to allocate an actual struct from that schema. In this
case, we will allocate an AddressBook:

addresses = addressbook_capnp.AddressBook.new_message() Notice that we used
addressbook_capnp from the previous section: Load a Cap’n Proto Schema.

Also as a shortcut, you can pass keyword arguments to the new_message
function, and those fields will be set in the new message:

person = addressbook_capnp.Person.new_message(name='alice')

# is equivalent to:

person = addressbook_capnp.Person.new_message() person.name = 'alice' List
Allocating a list inside of an object requires use of the init function:

people = addresses.init('people', 2) For now, let’s grab the first element out
of this list and assign it to a variable named alice:

alice = people[0] Note It is a very bad idea to call init more than once on a
single field. Every call to init allocates new memory inside your Cap’n Proto
message, and if you call it more than once, the previous memory is left as
dead space in the message. See Tips and Best Practices for more details.
Primitive Types For all primitive types, from the Cap’n Proto docs:

Boolean: Bool

Integers: Int8, Int16, Int32, Int64

Unsigned integers: UInt8, UInt16, UInt32, UInt64

Floating-point: Float32, Float64

Blobs: Text, Data

You can assign straight to the variable with the corresponding Python type.
For Blobs, you use strings. Assignment happens just by using the . syntax on
the object you contstructed above:

alice.id = 123 alice.name = 'Alice' alice.email = 'alice@example.com' Note
Text fields will behave differently depending on your version of Python. In
Python 2.x, Text fields will expect and return a bytes string, while in Python
3.x, they will expect and return a unicode string. Data fields will always a
return bytes string. Enums First we’ll allocate a length one list of
phonenumbers for alice:

alicePhone = alice.init('phones', 1)[0] Note that even though it was a length
1 list, it was still a list that was returned, and we extracted the first (and
only) element with [0].

Enums are treated like strings, and you assign to them like they were a Text
field:

alicePhone.type = 'mobile' If you assign an invalid value to one, you will get
a ValueError:

## alicePhone.type = 'foo'

ValueError Traceback (most recent call last) ... ValueError:
src/capnp/schema.c++:326: requirement not met: enum has no such enumerant;
name = foo Unions For the most part, you just treat them like structs:

alice.employment.school = "MIT" Now the school field is the active part of the
union, and we’ve assigned ‘MIT’ to it. You can query which field is set in a
union with which(), shown in Reading Unions

Also, one weird case is for Void types in Unions (and in general, but Void is
really only used in Unions). For these, you will have to assign None to them:

bob.employment.unemployed = None Note One caveat for unions is having structs
as union members. Let us assume employment.school was actually a struct with a
field of type Text called name: alice.employment.school.name = "MIT"

# Raises a ValueError

The problem is that a struct within a union isn’t initialized automatically.
You have to do the following:

school = alice.employment.init('school') school.name = "MIT" Note that this is
similar to init for lists, but you don’t pass a size. Requiring the init makes
it more clear that a memory allocation is occurring, and will hopefully make
you mindful that you shouldn’t set more than 1 field inside of a union, else
you risk a memory leak

Writing to a File Once you’re done assigning to all the fields in a message,
you can write it to a file like so:

f = open('example.bin', 'w+b') addresses.write(f) There is also a write_packed
function, that writes out the message more space-efficientally. If you use
write_packed, make sure to use read_packed when reading the message.

Read a message Reading from a file Much like before, you will have to
de-serialize the message from a file descriptor:

f = open('example.bin', 'rb') addresses =
addressbook_capnp.AddressBook.read(f) Note that this very much needs to match
the type you wrote out. In general, you will always be sending the same
message types out over a given channel or you should wrap all your types in an
unnamed union. Unnamed unions are defined in the .capnp file like so:

struct Message { union { person @0 :Person; addressbook @1 :AddressBook; } }
Reading Fields Fields are very easy to read. You just use the . syntax as
before. Lists behave just like normal Python lists:

for person in addresses.people: print(person.name, ':', person.email) for
phone in person.phones: print(phone.type, ':', phone.number) Reading Unions
The only tricky one is unions, where you need to call .which() to determine
the union type. The .which() call returns an enum, ie. a string, corresponding
to the field name:

which = person.employment.which() print(which)

if which == 'unemployed': print('unemployed') elif which == 'employer':
print('employer:', person.employment.employer) elif which == 'school':
print('student at:', person.employment.school) elif which == 'selfEmployed':
print('self employed') print() Serializing/Deserializing Files As shown in the
examples above, there is file serialization with write():

addresses = addressbook_capnp.AddressBook.new_message() ... f =
open('example.bin', 'w+b') addresses.write(f) And similarly for reading:

f = open('example.bin', 'rb') addresses =
addressbook_capnp.AddressBook.read(f) There are packed versions as well:

addresses.write_packed(f) f.seek(0) addresses =
addressbook_capnp.AddressBook.read_packed(f) Multi-message files The above
methods only guaranteed to work if your file contains a single message. If you
have more than 1 message serialized sequentially in your file, then you need
to use these convenience functions:

addresses = addressbook_capnp.AddressBook.new_message() ... f =
open('example.bin', 'w+b') addresses.write(f) addresses.write(f)
addresses.write(f) # write 3 messages f.seek(0)

for addresses in addressbook_capnp.AddressBook.read_multiple(f): print
addresses There is also a packed version:

for addresses in addressbook_capnp.AddressBook.read_multiple_packed(f): print
addresses Dictionaries There is a convenience method for converting Cap’n
Proto messages to a dictionary. This works for both Builder and Reader type
messages:

alice.to_dict() For the reverse, all you have to do is pass keyword arguments
to the new_message constructor:

my_dict = {'name' : 'alice'} alice =
addressbook_capnp.Person.new_message(\*\*my_dict)

# equivalent to: alice = addressbook_capnp.Person.new_message(name='alice')

It’s also worth noting, you can use python lists/dictionaries interchangably
with their Cap’n Proto equivalent types:

book = addressbook_capnp.AddressBook.new_message(people=[{'name': 'Alice'}])
... book = addressbook_capnp.AddressBook.new_message() book.init('people', 1)
book.people[0] = {'name': 'Bob'} Byte Strings/Buffers There is serialization
to a byte string available:

encoded_message = alice.to_bytes() And a corresponding from_bytes function:

alice = addressbook_capnp.Person.from_bytes(encoded_message) There are also
packed versions:

alice2 = addressbook_capnp.Person.from_bytes_packed(alice.to_bytes_packed())
Byte Segments Note This feature is not supported in PyPy at the moment,
pending investigation. Cap’n Proto supports a serialization mode which
minimizes object copies. In the C++ interface,
capnp::MessageBuilder::getSegmentsForOutput() returns an array of pointers to
segments of the message’s content without copying.
capnp::SegmentArrayMessageReader performs the reverse operation, i.e., takes
an array of pointers to segments and uses the underlying data, again without
copying. This produces a different wire serialization format from to_bytes()
serialization, which uses capnp::messageToFlatArray() and
capnp::FlatArrayMessageReader (both of which use segments internally, but
write them in an incompatible way).

For compatibility on the Python side, use the to_segments() and
from_segments() functions:

segments = alice.to_segments() This returns a list of segments, each a byte
buffer. Each segment can be, e.g., turned into a ZeroMQ message frame. The
list of segments can also be turned back into an object:

alice = addressbook_capnp.Person.from_segments(segments)
