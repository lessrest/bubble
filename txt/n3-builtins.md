Title: Notation3 Builtin Functions

URL Source: https://w3c-cg.github.io/n3Builtins/

Markdown Content:
1\. Builtin namespaces[](https://w3c-cg.github.io/n3Builtins/#builtinnamespaces)
--------------------------------------------------------------------------------

N3 defines a core set of [builtins](https://w3c-cg.github.io/n3Builtins/#builtins): Builtins are grouped into distinct vocabularies depending on the N3 triple elements they operate on (e.g., string, list), or their particular topic (e.g., time, cryptography, log). Builtins are denoted by a controlled IRI defined in one of the core builtin namespaces:

*   [Crypto](http://www.w3.org/2000/10/swap/crypto#) – [http://www.w3.org/2000/10/swap/crypto#](http://www.w3.org/2000/10/swap/crypto#),
*   [List](http://www.w3.org/2000/10/swap/list#) – [http://www.w3.org/2000/10/swap/list#](http://www.w3.org/2000/10/swap/list#),
*   [Log](http://www.w3.org/2000/10/swap/log#) – [http://www.w3.org/2000/10/swap/log#](http://www.w3.org/2000/10/swap/log#),
*   [Math](http://www.w3.org/2000/10/swap/math#) – [http://www.w3.org/2000/10/swap/math#](http://www.w3.org/2000/10/swap/math#),
*   [String](http://www.w3.org/2000/10/swap/string#) – [http://www.w3.org/2000/10/swap/string#](http://www.w3.org/2000/10/swap/string#)
*   [Time](http://www.w3.org/2000/10/swap/time#) – [http://www.w3.org/2000/10/swap/time#](http://www.w3.org/2000/10/swap/time#).

2\. Builtin arguments[](https://w3c-cg.github.io/n3Builtins/#builtinarguments)
------------------------------------------------------------------------------

An N3 [builtin](https://w3c-cg.github.io/n3Builtins/#builtins) operates on its arguments. An argument[](https://w3c-cg.github.io/n3Builtins/#argument) is a placeholder that refers to an N3 triple element from the [builtin statement](https://w3c-cg.github.io/n3Builtins/#builtin-statement), i.e., the N3 statement where the builtin acts as a predicate.

In the simplest case, there are two arguments that respectively refer to the subject and object of the builtin statement. For instance, statements such as `1 math:lessThan 2` have two arguments `$s` and `$o`, which is written as `$s math:lessThan $o`.

Arguments can be also represent a "deconstruction" of the subject or object in case of lists. For instance, `(1 2 3) math:sum 6` will have arguments `$s.1` .. `$s.n` and `$o`, which is written as `($s.1 .. $s.n) math:sum $o`.

### 2.1. Argument modes[](https://w3c-cg.github.io/n3Builtins/#argumentmodes)

For a given builtin, an argument will have a defined argument mode that stipulates whether it should be bound or not in the builtin statement. This binding requirement determines whether the argument can serve as builtin input, output, or both. Note that these modes are mostly based on [Prolog argument modes](https://www.swi-prolog.org/pldoc/man?section=argmode).

*   `++`: input argument (bound, fully grounded)
*   `+`: input argument (bound, possibly not fully grounded)
*   `-`: output argument (bounded or not bounded)
*   `--`: output argument (not bounded)
*   `?`: either providing input or accepting output, or both.
*   `[*]`: modifier indicating that an argument can have multiple solutions.

### 2.2. Argument domains[](https://w3c-cg.github.io/n3Builtins/#arg_domains)

An N3 builtin often has an expected datatype for its arguments, called the domain datatype. If the datatype of an argument value, called the value datatype, does not match the domain datatype, it may be possible to cast the value’s datatype to, or substitute it for, the domain datatype.

The expected datatypes of arguments, i.e., domain datatypes, are defined per N3 builtin.

If the [value datatype](https://w3c-cg.github.io/n3Builtins/#value-datatype) and [domain datatype](https://w3c-cg.github.io/n3Builtins/#domain-datatype) do not match, and no casting or substitution is possible, the builtin statement will be considered false. (We point out that this is in line with the concept of the [builtin theory box](https://w3c-cg.github.io/n3Builtins/#builtintheorybox): a BPG search using the builtin statement will not match any statement in the theory box when literal datatypes do not match.)

Below, we elaborate on the type casting, promotion or substitution that may be applied to align [domain datatypes](https://w3c-cg.github.io/n3Builtins/#domain-datatype) with [value datatypes](https://w3c-cg.github.io/n3Builtins/#value-datatype).

#### 2.2.1. Numeric datatype promotion and substitution[](https://w3c-cg.github.io/n3Builtins/#numericdatatypepromotion)

If the numeric [value datatype](https://w3c-cg.github.io/n3Builtins/#value-datatype) does not match the [domain datatype](https://w3c-cg.github.io/n3Builtins/#domain-datatype), it may be possible to promote or substitute the numeric value datatype:

**Numeric type promotion**: A numeric value datatype that [is derived from](https://www.w3.org/TR/xmlschema-2/#dt-derived) the domain datatype can be promoted to the latter (e.g., `xs:integer` is derived from `xs:decimal`). This is done by casting the original value to the required datatype. Refer to [XML Schema Part 2](https://www.w3.org/TR/xmlschema-2/#built-in-datatypes) for details on these datatypes.

If there is no direct derivation relation between the value and domain datatype, the following numeric type promotions can take place:

*   A value of type `xs:float` (or any type derived from `xs:float`) can be promoted to type `xs:double`. The result is an `xs:double` value that is the same as the original value.
*   A value of type `xs:decimal` (or any type derived from `xs:decimal`) can be promoted to either of the types `xs:float` or `xs:double`.

**Numeric type substitution**: if _all values_ have the same numeric datatype, and this datatype [is derived from](https://www.w3.org/TR/xmlschema-2/#dt-derived) the domain datatype (e.g., `xs:integer` is derived from `xs:decimal`), then the values can be used without any casting. For example, if two `xs:integer` values are used for input where `xs:decimal` domains are expected, then the values retain their datatype as `xs:integer`. The substituted numeric datatype (in this case, `xs:integer`) will also apply to the builtin’s output, if any.

**Builtins operating on any numeric type**: some N3 builtins (e.g., `math:sum`) operate on values of any numeric type (i.e., `xs:numeric`, the union of `xs:double`, `xs:float`, and `xs:decimal`). I.e., their concrete input values may present any combination of numeric types. In that case, the builtin can only be applied if all value datatypes can be promoted into _a common numeric datatype_ in the ordered list `(xs:integer, xs:decimal, xs:float, xs:double)`. If so, at that point, we rely on numeric type substitution. For instance:

*   For a builtin with `xs:numeric` domain datatypes, given two value datatypes `xs:integer` and `xs:decimal`, the `xs:integer` value will be promoted to `xs:decimal` as the common numeric datatype. At that point, the two `xs:decimal` datatypes can be substituted for `xs:numeric` (numeric type substitution). If the builtin has an output, then the calculated value for this output will also have datatype `xs:decimal`.
*   For a builtin with `xs:numeric` domain datatypes, given two values with datatype `xs:integer`, the `xs:integer` datatype will simply be substituted for `xs:numeric`. If the builtin has an output, then the calculated value for the output will also have datatype `xs:integer`.

#### 2.2.2. Other kinds of datatype casting[](https://w3c-cg.github.io/n3Builtins/#typesofdatatypecasting)

If the non-numeric [value datatype](https://w3c-cg.github.io/n3Builtins/#value-datatype) does not match the [domain datatype](https://w3c-cg.github.io/n3Builtins/#domain-datatype), it may be possible to cast the value datatype to the domain datatype:

**String**: A literal will be considered a "string" when it has an `xs:string` datatype, a `rdf:langString` datatype due to the presence of a language tag, or when it lacks a datatype.

*   _Casting from string_: if an input value has an `xs:string` datatype that does not match the domain, it may be possible to cast the string to the domain datatype, as [defined in XPath](https://www.w3.org/TR/xpath-functions/#casting-from-strings). The resulting value representation must be a valid lexical form for the domain datatype.
*   _Casting to string_: if an input value is an IRI, or any kind of literal (incl. type `xs:anyUri` or its derivations), and the domain is `xs:string`, then the value will be cast to a string as [defined in XPath](https://www.w3.org/TR/xpath-functions/#casting-to-string) along with additional rules defined for [SPARQL 1.1](https://www.w3.org/TR/sparql11-query/#FunctionMapping).

**Other datatypes**: other types of datatype casting may take place as [defined in XPath](https://www.w3.org/TR/xpath-functions/#casting).

**Editors' Note:**

There is a useful chart for casting primitive types to primitive types in [XPath](https://www.w3.org/TR/xpath-functions/#casting-from-primitive-to-primitive), a subset of which is defined for [SPARQL 1.1](https://www.w3.org/TR/sparql11-query/#FunctionMapping).

#### 2.2.3. Scopes[](https://w3c-cg.github.io/n3Builtins/#scope)

Some N3 builtins have a scope as an argument (e.g., [log:collectAllIn](https://w3c-cg.github.io/n3Builtins/#log:collectAllIn)). A scope is either a concretely stated N3 graph, or the reasoning scope, that is, the deductive closure of the whole N3 graph included in the reasoning run, with the exception of the concrete application of the rule the built-in occurs in. If the scope is left open (that is, there is an unbound variable in the scope position), the reasoning scope is assumed.

3\. Builtin Evaluation[](https://w3c-cg.github.io/n3Builtins/#builtinevaluation)
--------------------------------------------------------------------------------

### 3.1. Builtin theory box[](https://w3c-cg.github.io/n3Builtins/#builtintheorybox)

A builtin statement can be seen as a _constrained_ basic graph pattern (BGP) search on the N3 [builtin theory box](https://w3c-cg.github.io/n3Builtins/#builtin-theory-box). This builtin theory box is defined to include all truthful builtin statements for the N3 builtin. In case this BGP search matches one or more statements in the theory box, taking into account options for datatype casting, promotion, or substitution (see [Argument domains](https://w3c-cg.github.io/n3Builtins/#arg_domains)) the N3 [builtin statement](https://w3c-cg.github.io/n3Builtins/#builtin-statement) will be considered true.

For example, for the `math:sum` builtin, the [builtin theory box](https://w3c-cg.github.io/n3Builtins/#builtin-theory-box) includes all grounded builtin statements of the form `($s.1 .. $s.n) math:sum $o .`, where argument values have datatype `xs:numeric` and, for each statement, the sum of `$s.1 .. $s.n` equals `$o`. Below, we give several examples of how this theory box is used to evaluate builtin statements.

*   Using the builtin statement `(1 2 3) math:sum ?x .` as a BGP search on the theory box will return exactly one result where `?x` has value `6`.
*   Using the concrete builtin statement `(1 2 3) math:sum 6 .` as a BGP search on the theory box will similarly match exactly 1 statement.

Hence, in both cases, the builtin statement will be considered true, and the set of matching triples from the theory box will be used to instantiate the [builtin statement](https://w3c-cg.github.io/n3Builtins/#builtin-statement). In the first case, this will lead to a single instance of the builtin statement, where variable `?x` will be bound to value `6`. In the second case, the grounded builtin statement will itself serve as such an instance.

**Editors' Note:**

Note that there can be multiple matching triples, thus leading to multiple instances of the builtin statement. Consider the following example for the `list:member` builtin:

`( 1 2 3 ) list:member ?x .`  
This will yield the following matching triples from the [builtin theory box](https://w3c-cg.github.io/n3Builtins/#builtin-theory-box):

`( 1 2 3 ) list:member 1 .`  
`( 1 2 3 ) list:member 2 .`  
`( 1 2 3 ) list:member 3 .`

The BGP search is _constrained_ in order to avoid infinite numbers of results and intractable calculations; in other cases, constraints weigh utility vs. difficulty of implementation. For example, the [builtin statement](https://w3c-cg.github.io/n3Builtins/#builtin-statement) `(?a ?b) math:sum 2` would match an infinite number of grounded builtin statements. In other cases, the BGP search is restricted due to practical considerations. For instance, [builtin statement](https://w3c-cg.github.io/n3Builtins/#builtin-statement) `(1 ?x) math:sum 6` would match only a single grounded builtin statement in the theory box, but this would complicate the implementation of the builtin for only limited utility (as other builtins can be used instead to subtract 1 from 6).

These constraints are encoded in terms of [argument modes](https://w3c-cg.github.io/n3Builtins/#argument-mode) and [domain datatypes](https://w3c-cg.github.io/n3Builtins/#domain-datatype) in the respective builtin definitions. In case these constraints are not met, the [builtin statement](https://w3c-cg.github.io/n3Builtins/#builtin-statement) will evaluate to false.

4\. Builtins[](https://w3c-cg.github.io/n3Builtins/#builtins)
-------------------------------------------------------------

### 4.1. crypto[](https://w3c-cg.github.io/n3Builtins/#crypto)

#### 4.1.1. crypto:sha[](https://w3c-cg.github.io/n3Builtins/#crypto:sha)

Gets as object the [SHA-1 hash](https://en.wikipedia.org/wiki/SHA-1) of the subject.`true` if and only if `$o` is the [SHA-1 hash](https://en.wikipedia.org/wiki/SHA-1) of `$s`.

**Schema**  
`$s+ crypto:sha $o-`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E+.%0A%40prefix+crypto%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fcrypto%23%3E+.%0A%0A%7B+%22hello+world%22+crypto%3Asha+%3Fsha+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%3Fsha+.+%7D+.)

Calculate the SHA-1 of the string "hello world".

**Formula:**

@prefix : <http://example.org/\> .
@prefix crypto: <http://www.w3.org/2000/10/swap/crypto#\> .

{ "hello world" crypto:sha ?sha . } =\> { :result :is ?sha . } .

**Result:**

@prefix : <http://example.org/\>.
:result :is "2aae6c35c94fcfb415dbe95f408b9ce91ee846ed" .

### 4.2. math[](https://w3c-cg.github.io/n3Builtins/#math)

#### 4.2.1. math:absoluteValue[](https://w3c-cg.github.io/n3Builtins/#math:absoluteValue)

Calculates as object the absolute value of the subject.`true` if and only if `$o` is the absolute value of `$s`.

**Schema**  
`$s+ math:absoluteValue $o-`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+-2+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3AabsoluteValue+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the absolute value of the value -2.

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param -2 .

{
    :Let :param ?param .
    ?param math:absoluteValue ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 2. 

#### 4.2.2. math:acos[](https://w3c-cg.github.io/n3Builtins/#math:acos)

Calculates the object as the arc cosine value of the subject.`true` if and only if `$o` is the arc cosine value of `$s`.

**See also**  
[math:cos](https://w3c-cg.github.io/n3Builtins/#math:cos)  
[math:cosh](https://w3c-cg.github.io/n3Builtins/#math:cosh)

**Schema**  
`$s? math:acos $o?`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+1+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Aacos+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the arc cosine of the value 1.

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param 1 .

{
    :Let :param ?param .
    ?param math:acos ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 0.0 .

#### 4.2.3. math:asin[](https://w3c-cg.github.io/n3Builtins/#math:asin)

Calculates the object as the arc sine value of the subject.`true` if and only if `$o` is the arc sine value of `$s`.

**See also**  
[math:sin](https://w3c-cg.github.io/n3Builtins/#math:sin)  
[math:sinh](https://w3c-cg.github.io/n3Builtins/#math:sinh)

**Schema**  
`$s? math:asin $o?`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+1+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Aasin+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the arc sine of the value 1.

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param 1 .

{
    :Let :param ?param .
    ?param math:asin ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 1.5707963267948966 .

#### 4.2.4. math:atan[](https://w3c-cg.github.io/n3Builtins/#math:atan)

Calculates the object as the arc tangent value of the subject.`true` if and only if `$o` is the arc tangent value of `$s`.

**See also**  
[math:tan](https://w3c-cg.github.io/n3Builtins/#math:tan)  
[math:tanh](https://w3c-cg.github.io/n3Builtins/#math:tanh)

**Schema**  
`$s? math:atan $o?`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+1+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Aatan+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the arc tangent of the value 1.

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param 1 .

{
    :Let :param ?param .
    ?param math:atan ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 0.7853981633974483 .

#### 4.2.5. math:cos[](https://w3c-cg.github.io/n3Builtins/#math:cos)

Calculates the object as the cosine value of the subject.`true` if and only if `$o` is the cosine value of `$s`.

**See also**  
[math:acos](https://w3c-cg.github.io/n3Builtins/#math:acos)  
[math:cosh](https://w3c-cg.github.io/n3Builtins/#math:cosh)

**Schema**  
`$s? math:cos $o?`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+0+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Acos+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the cosine of the value 0.

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param 0 .

{
    :Let :param ?param .
    ?param math:cos ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 1.0 .

#### 4.2.6. math:cosh[](https://w3c-cg.github.io/n3Builtins/#math:cosh)

Calculates the object as the hyperbolic cosine value of the subject.`true` if and only if `$o` is the hyperbolic cosine value of `$s`.

**See also**  
[math:cos](https://w3c-cg.github.io/n3Builtins/#math:cos)  
[math:acos](https://w3c-cg.github.io/n3Builtins/#math:acos)

**Schema**  
`$s? math:cosh $o?`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+0+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Acosh+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the hyperbolic cosine of the value 0.

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param 0 .

{
    :Let :param ?param .
    ?param math:cosh ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 1.0 .

#### 4.2.7. math:degrees[](https://w3c-cg.github.io/n3Builtins/#math:degrees)

Calculates the object as the value in degrees corresponding to the radians value of the subject.`true` if and only if `$o` is the value in degrees corresponding to the radians value of `$s`.

**Schema**  
`$s? math:degrees $o?`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+1.57079632679+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Adegrees+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the degrees of the radians value 1.57079632679.

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param 1.57079632679 .

{
    :Let :param ?param .
    ?param math:degrees ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 89.99999999971946 .

#### 4.2.8. math:difference[](https://w3c-cg.github.io/n3Builtins/#math:difference)

Calculates the object by subtracting the second number from the first number given in the subject list.`true` if and only if `$o` is the result of subtracting `$s.2` from `$s.1`.

**Schema**  
`( $s.1+ $s.2+ )+ math:difference $o-`

where:

`$s.1`: (`xsd:decimal` | `xsd:double` | `xsd:float`), `$s.2`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+%287+2%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Adifference+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the value of 7 minus 2.

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param (7 2) .

{
    :Let :param ?param .
    ?param math:difference ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 5.

#### 4.2.9. math:equalTo[](https://w3c-cg.github.io/n3Builtins/#math:equalTo)

Checks whether the subject and object are the same number.`true` if and only if `$s` is the same number as `$o`.

**See also**  
[math:notEqualTo](https://w3c-cg.github.io/n3Builtins/#math:notEqualTo)

**Schema**  
`$s? math:equalTo $o?`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+%2842+42%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%28%3FX+%3FY%29+.%0A++++%3FX+math%3AequalTo+%3FY+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Check if the numbers 42 and 42 are equal .

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param (42 42) .

{
    :Let :param (?X ?Y) .
    ?X math:equalTo ?Y .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true . 

#### 4.2.10. math:exponentiation[](https://w3c-cg.github.io/n3Builtins/#math:exponentiation)

Calculates the object as the result of raising the first number to the power of the second number in the subject list. You can also use this to calculate the logarithm of the object, with as base the first number of the subject list (see examples).`true` if and only if `$o` is the result of raising `$s.1` to the power of `$s.2`

**Schema**  
`( $s.1+ $s.2? )+ math:exponentiation $o?`

where:

`$s.1`: (`xsd:decimal` | `xsd:double` | `xsd:float`), `$s.2`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%7B%0A++++%287+%3Fresult%29+math%3Aexponentiation+49+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the logarithm of 49 base 2 .

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

{
    (7 ?result) math:exponentiation 49 .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 2.0 .

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+%287+2%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Aexponentiation+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the value of 7 raised to the power of 2 .

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param (7 2) .

{
    :Let :param ?param .
    ?param math:exponentiation ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 49 .

#### 4.2.11. math:greaterThan[](https://w3c-cg.github.io/n3Builtins/#math:greaterThan)

Checks whether the subject is a number that is greater than the object.`true` if and only if `$s` is a number that is greater than `$o`.

**See also**  
[math:notGreaterThan](https://w3c-cg.github.io/n3Builtins/#math:notGreaterThan)

**Schema**  
`$s+ math:greaterThan $o+`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+%2842+41%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%28%3FX+%3FY%29+.%0A++++%3FX+math%3AgreaterThan+%3FY+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Check if 42 is greater than 41 .

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param (42 41) .

{
    :Let :param (?X ?Y) .
    ?X math:greaterThan ?Y .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true .

#### 4.2.12. math:lessThan[](https://w3c-cg.github.io/n3Builtins/#math:lessThan)

Checks whether the subject is a number that is less than the object.`true` if and only if `$s` is a number that is less than `$o`.

**See also**  
[math:notLessThan](https://w3c-cg.github.io/n3Builtins/#math:notLessThan)

**Schema**  
`$s+ math:lessThan $o+`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+%2841+42%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%28%3FX+%3FY%29+.%0A++++%3FX+math%3AlessThan+%3FY+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Check if 41 is less than 42 .

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param (41 42) .

{
    :Let :param (?X ?Y) .
    ?X math:lessThan ?Y .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true .

#### 4.2.13. math:negation[](https://w3c-cg.github.io/n3Builtins/#math:negation)

Calculates the object as the negation of the subject.`true` if and only if `$o` is the negation of `$s`.

**Schema**  
`$s? math:negation $o?`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+42+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Anegation+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the negation of the value 42 .

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param 42 .

{
    :Let :param ?param .
    ?param math:negation ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is -42 .

#### 4.2.14. math:notEqualTo[](https://w3c-cg.github.io/n3Builtins/#math:notEqualTo)

Checks whether the subject and object are not the same number.`true` if and only if `$s` is the not same number as `$o`.

**See also**  
[math:equalTo](https://w3c-cg.github.io/n3Builtins/#math:equalTo)

**Schema**  
`$s+ math:notEqualTo $o+`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+%2841+42%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%28%3FX+%3FY%29+.%0A++++%3FX+math%3AnotEqualTo+%3FY+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Check if the numbers 41 and 42 are not equal .

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param (41 42) .

{
    :Let :param (?X ?Y) .
    ?X math:notEqualTo ?Y .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true .

#### 4.2.15. math:notGreaterThan[](https://w3c-cg.github.io/n3Builtins/#math:notGreaterThan)

Checks whether the subject is a number that is not greater than the object. You can use this as an equivalent of a lessThanOrEqual operator.`true` if and only if `$s` is a number that is not greater than `$o`.

**See also**  
[math:greaterThan](https://w3c-cg.github.io/n3Builtins/#math:greaterThan)

**Schema**  
`$s+ math:notGreaterThan $o+`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+%2841+42%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%28%3FX+%3FY%29+.%0A++++%3FX+math%3AnotGreaterThan+%3FY+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Check if 41 is not greater than 42 .

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param (41 42) .

{
    :Let :param (?X ?Y) .
    ?X math:notGreaterThan ?Y .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true .

#### 4.2.16. math:notLessThan[](https://w3c-cg.github.io/n3Builtins/#math:notLessThan)

Checks whether the subject is a number that is not less than the object. You can use this as an equivalent of a greaterThanOrEqual operator.`true` if and only if `$s` is a number that is not less than `$o`.

**See also**  
[math:lessThan](https://w3c-cg.github.io/n3Builtins/#math:lessThan)

**Schema**  
`$s+ math:notLessThan $o+`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+%2842+41%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%28%3FX+%3FY%29+.%0A++++%3FX+math%3AnotLessThan+%3FY+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Check if 42 is not less than 41 .

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param (42 41) .

{
    :Let :param (?X ?Y) .
    ?X math:notLessThan ?Y .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true .

#### 4.2.17. math:product[](https://w3c-cg.github.io/n3Builtins/#math:product)

Calculates the object as the product of the numbers given in the subject list.`true` if and only if `$o` is the arithmetic product of all numbers `$s.i`

**Schema**  
`( $s.i+ )+ math:product $o-`

where:

`$s.i`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+%282+4+6+8%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Aproduct+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the product of 2,4,6, and 8 .

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param (2 4 6 8) .

{
    :Let :param ?param .
    ?param math:product ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 384.

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+%282+21%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Aproduct+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the product of 2 and 21.

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param (2 21) .

{
    :Let :param ?param .
    ?param math:product ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 42.

#### 4.2.18. math:quotient[](https://w3c-cg.github.io/n3Builtins/#math:quotient)

Calculates the object by dividing the first number by the second number given in the subject list.`true` if and only if `$o` is the result of dividing `$s.1` by `$s.2`.

**Schema**  
`( $s.1+ $s.2+ )+ math:quotient $o-`

where:

`$s.1`: (`xsd:decimal` | `xsd:double` | `xsd:float`), `$s.2`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+%2842+2%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Aquotient+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the quotient of 42 and 2.

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param (42 2) .

{
    :Let :param ?param .
    ?param math:quotient ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 21. 

#### 4.2.19. math:remainder[](https://w3c-cg.github.io/n3Builtins/#math:remainder)

Calculates the object as the remainder of the division of the first integer by the second integer given in the subject list.`true` if and only if `$o` is the remainder of dividing `$s.1` by `$s.2`.

**Schema**  
`( $s.1+ $s.2+ )+ math:remainder $o-`

where:

`$s.1`: `xsd:integer`, `$s.2`: `xsd:integer`  
`$o`: `xsd:integer`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+%2810+3%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Aremainder+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the remainder of 10 divided by 3.

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param (10 3) .

{
    :Let :param ?param .
    ?param math:remainder ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 1.

#### 4.2.20. math:rounded[](https://w3c-cg.github.io/n3Builtins/#math:rounded)

Calculates the object as the integer that is closest to the subject number.`true` if and only if `$o` is the integer that is closest to `$s`. If there are two such numbers, then the one closest to positive infinity is returned.

**Schema**  
`$s+ math:rounded $o-`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: `xsd:integer`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%40prefix+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E+.%0A%0A%3ALet+%3Aparam+%223.3%22%5E%5Exsd%3Adouble+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Arounded+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the rounded version of 3.3.

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\> .

:Let :param "3.3"^^xsd:double .

{
    :Let :param ?param .
    ?param math:rounded ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 3. 

#### 4.2.21. math:sin[](https://w3c-cg.github.io/n3Builtins/#math:sin)

Calculates the object as the sine value of the subject.`true` if and only if `$o` is the sine value of `$s`.

**See also**  
[math:sinh](https://w3c-cg.github.io/n3Builtins/#math:sinh)  
[math:asin](https://w3c-cg.github.io/n3Builtins/#math:asin)

**Schema**  
`$s? math:sin $o?`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%40prefix+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E+.%0A%0A%3ALet+%3Aparam+%221.57079632679%22%5E%5Exsd%3Adouble+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Asin+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the sin of pi/2 (1.57079632679) .

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\> .

:Let :param "1.57079632679"^^xsd:double .

{
    :Let :param ?param .
    ?param math:sin ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\> .
:result :is "1.0"^^xsd:double . 

#### 4.2.22. math:sinh[](https://w3c-cg.github.io/n3Builtins/#math:sinh)

Calculates the object as the hyperbolic sine value of the subject.`true` if and only if `$o` is the hyperbolic sine value of `$s`.

**See also**  
[math:sin](https://w3c-cg.github.io/n3Builtins/#math:sin)  
[math:asin](https://w3c-cg.github.io/n3Builtins/#math:asin)

**Schema**  
`$s? math:sinh $o?`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%40prefix+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E+.%0A%0A%3ALet+%3Aparam+%220.88137358701954302%22%5E%5Exsd%3Adouble.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Asinh+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the sinh of log(1 + sqrt(2)) (0.88137358701954302).

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\> .

:Let :param "0.88137358701954302"^^xsd:double.

{
    :Let :param ?param .
    ?param math:sinh ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 1.0.

#### 4.2.23. math:sum[](https://w3c-cg.github.io/n3Builtins/#math:sum)

Calculates the object as the sum of the numbers given in the subject list.`true` if and only if `$o` is the arithmetic sum of all numbers `$s.i`

**Schema**  
`( $s.i+ )+ math:sum $o-`

where:

`$s.i`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%0A%3ALet+%3Aparam+%281+2+3+4+5+6+7+8+9+10%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Asum+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the sum of 1,2,3,4,5,6,7,8,9,10.

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .

:Let :param (1 2 3 4 5 6 7 8 9 10) .

{
    :Let :param ?param .
    ?param math:sum ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 55.

#### 4.2.24. math:tan[](https://w3c-cg.github.io/n3Builtins/#math:tan)

Calculates the object as the tangent value of the subject.`true` if and only if `$o` is the tangent value of `$s`.

**See also**  
[math:tanh](https://w3c-cg.github.io/n3Builtins/#math:tanh)  
[math:atan](https://w3c-cg.github.io/n3Builtins/#math:atan)

**Schema**  
`$s? math:tan $o?`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%40prefix+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E+.%0A%0A%3ALet+%3Aparam+%220.7853981633974483%22%5E%5Exsd%3Adouble+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Atan+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the tangent of the value 0.7853981633974483 .

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\> .

:Let :param "0.7853981633974483"^^xsd:double .

{
    :Let :param ?param .
    ?param math:tan ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\> .
:result :is "0.9999999999999999"^^xsd:double. 

#### 4.2.25. math:tanh[](https://w3c-cg.github.io/n3Builtins/#math:tanh)

Calculates the object as the hyperbolic tangent value of the subject.`true` if and only if `$o` is the hyperbolic tangent value of `$s`.

**See also**  
[math:tan](https://w3c-cg.github.io/n3Builtins/#math:tan)  
[math:atan](https://w3c-cg.github.io/n3Builtins/#math:atan)

**Schema**  
`$s? math:tanh $o?`

where:

`$s`: (`xsd:decimal` | `xsd:double` | `xsd:float`)  
`$o`: (`xsd:decimal` | `xsd:double` | `xsd:float`)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+math%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fmath%23%3E+.%0A%40prefix+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E+.%0A%0A%3ALet+%3Aparam+%220.549306%22%5E%5Exsd%3Adouble+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+math%3Atanh+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the hyperbolic tanget of 0.549306 .

**Formula:**

@prefix : <http://example.org/\>.
@prefix math: <http://www.w3.org/2000/10/swap/math#\> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\> .

:Let :param "0.549306"^^xsd:double .

{
    :Let :param ?param .
    ?param math:tanh ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\> .
:result :is "0.49999989174945103"^^xsd:double. 

### 4.3. time[](https://w3c-cg.github.io/n3Builtins/#time)

#### 4.3.1. time:day[](https://w3c-cg.github.io/n3Builtins/#time:day)

Gets as object the integer day component of the subject xsd:dateTime.`true` if and only if `$o` is the integer day component of `$s`.

**Schema**  
`$s+ time:day $o-`

where:

`$s`: `xsd:dateTime`  
`$o`: `xsd:integer`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E.%0A%40prefix+time%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Ftime%23%3E+.%0A%0A%3ALet+%3Aparam+%222023-04-01T18%3A06%3A04Z%22%5E%5Exsd%3AdateTime+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+time%3Aday+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Return the day component of the date "2023-04-01T18:06:04Z" .

**Formula:**

@prefix : <http://example.org/\>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\>.
@prefix time: <http://www.w3.org/2000/10/swap/time#\> .

:Let :param "2023-04-01T18:06:04Z"^^xsd:dateTime .

{
    :Let :param ?param .
    ?param time:day ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 1. 

#### 4.3.2. time:minute[](https://w3c-cg.github.io/n3Builtins/#time:minute)

Gets as object the integer minutes component of the subject xsd:dateTime.`true` if and only if `$o` is the integer minutes component of `$s`.

**Schema**  
`$s+ time:minute $o-`

where:

`$s`: `xsd:dateTime`  
`$o`: `xsd:integer`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E.%0A%40prefix+time%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Ftime%23%3E+.%0A%0A%3ALet+%3Aparam+%222023-04-01T18%3A06%3A04Z%22%5E%5Exsd%3AdateTime+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+time%3Aminute+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Return the minute component of the date "2023-04-01T18:06:04Z" .

**Formula:**

@prefix : <http://example.org/\>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\>.
@prefix time: <http://www.w3.org/2000/10/swap/time#\> .

:Let :param "2023-04-01T18:06:04Z"^^xsd:dateTime .

{
    :Let :param ?param .
    ?param time:minute ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 6. 

#### 4.3.3. time:month[](https://w3c-cg.github.io/n3Builtins/#time:month)

Gets as object the integer month component of the subject xsd:dateTime.`true` if and only if `$o` is the integer month component of `$s`.

**Schema**  
`$s+ time:month $o-`

where:

`$s`: `xsd:dateTime`  
`$o`: `xsd:integer`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E.%0A%40prefix+time%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Ftime%23%3E+.%0A%0A%3ALet+%3Aparam+%222023-04-01T18%3A06%3A04Z%22%5E%5Exsd%3AdateTime+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+time%3Amonth+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Return the month component of the date "2023-04-01T18:06:04Z" .

**Formula:**

@prefix : <http://example.org/\>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\>.
@prefix time: <http://www.w3.org/2000/10/swap/time#\> .

:Let :param "2023-04-01T18:06:04Z"^^xsd:dateTime .

{
    :Let :param ?param .
    ?param time:month ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 4. 

#### 4.3.4. time:second[](https://w3c-cg.github.io/n3Builtins/#time:second)

Gets as object the integer seconds component of the subject xsd:dateTime.`true` if and only if `$o` is the integer seconds component of `$s`.

**Schema**  
`$s+ time:second $o-`

where:

`$s`: `xsd:dateTime`  
`$o`: `xsd:integer`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E.%0A%40prefix+time%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Ftime%23%3E+.%0A%0A%3ALet+%3Aparam+%222023-04-01T18%3A06%3A04Z%22%5E%5Exsd%3AdateTime+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+time%3Asecond+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Return the seconds component of the date "2023-04-01T18:06:04Z" .

**Formula:**

@prefix : <http://example.org/\>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\>.
@prefix time: <http://www.w3.org/2000/10/swap/time#\> .

:Let :param "2023-04-01T18:06:04Z"^^xsd:dateTime .

{
    :Let :param ?param .
    ?param time:second ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 4. 

#### 4.3.5. time:timeZone[](https://w3c-cg.github.io/n3Builtins/#time:timeZone)

Gets as object the trailing timezone offset of the subject xsd:dateTime (e.g., "-05:00").`true` if and only if `$o` is the timezone offset of `$s`.

**Schema**  
`$s+ time:timeZone $o-`

where:

`$s`: `xsd:dateTime`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E.%0A%40prefix+time%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Ftime%23%3E+.%0A%0A%3ALet+%3Aparam+%222023-04-01T18%3A06%3A04Z%22%5E%5Exsd%3AdateTime+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+time%3Aminute+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Return the time zone component of the date "2023-04-01T18:06:04Z" .

**Formula:**

@prefix : <http://example.org/\>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\>.
@prefix time: <http://www.w3.org/2000/10/swap/time#\> .

:Let :param "2023-04-01T18:06:04Z"^^xsd:dateTime .

{
    :Let :param ?param .
    ?param time:minute ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is "Z". 

#### 4.3.6. time:year[](https://w3c-cg.github.io/n3Builtins/#time:year)

Gets as object the integer year component of the subject xsd:dateTime.`true` if and only if `$o` is the integer year component of `$s`.

**Schema**  
`$s+ time:year $o-`

where:

`$s`: `xsd:dateTime`  
`$o`: `xsd:integer`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E.%0A%40prefix+time%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Ftime%23%3E+.%0A%0A%3ALet+%3Aparam+%222023-04-01T18%3A06%3A04Z%22%5E%5Exsd%3AdateTime+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+time%3Ayear+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Return the minute component of the date "2023-04-01T18:06:04Z" .

**Formula:**

@prefix : <http://example.org/\>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\>.
@prefix time: <http://www.w3.org/2000/10/swap/time#\> .

:Let :param "2023-04-01T18:06:04Z"^^xsd:dateTime .

{
    :Let :param ?param .
    ?param time:year ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 2023. 

### 4.4. list[](https://w3c-cg.github.io/n3Builtins/#list)

#### 4.4.1. list:append[](https://w3c-cg.github.io/n3Builtins/#list:append)

Appends the lists from the subject list into a single list as object.`true` if and only if `$o` is the concatenation of all lists `$s.i`.

**See also**  
[list:remove](https://w3c-cg.github.io/n3Builtins/#list:remove)

**Schema**  
`( $s.i?[*] )+ list:append $o?`

where:

`$s.i`: `rdf:List`  
`$o`: `rdf:List`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%7B+%28+%281%29+%282+3%29+%284%29+%29+list%3Aappend+%281+2+3+4%29+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+true+.+%7D+.)

Is the list (1 2 3 4) equal to appending (1), (2 3) , (4)?

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

{ ( (1) (2 3) (4) ) list:append (1 2 3 4) . } =\> { :result :is true . } .

**Result:**

@prefix : <http://example.org/\>.
:result :is true. 

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%7B+%28+%281+2%29+%3Fwhat+%29+list%3Aappend+%281+2+3+4%29+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%3Fwhat+.+%7D+.)

What do we need to append to (1 2) to get (1 2 3 4)?

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

{ ( (1 2) ?what ) list:append (1 2 3 4) . } =\> { :result :is ?what . } .

**Result:**

@prefix : <http://example.org/\>.
:result :is (3 4). 

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%7B+%28+%3Fwhat+%283+4%29+%29+list%3Aappend+%281+2+3+4%29+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%3Fwhat+.+%7D+.)

What do we need to prepend to (3 4) to get (1 2 3 4)?

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

{ ( ?what (3 4) ) list:append (1 2 3 4) . } =\> { :result :is ?what . } .

**Result:**

@prefix : <http://example.org/\>.
:result :is (1 2). 

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%7B+%28+%281+2%29+%283+4%29+%29+list%3Aappend+%3Flist+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%3Flist+.+%7D+.)

Append (3 4) to the list (1 2).

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

{ ( (1 2) (3 4) ) list:append ?list . } =\> { :result :is ?list . } .

**Result:**

@prefix : <http://example.org/\>.
:result :is (1 2 3 4). 

#### 4.4.2. list:first[](https://w3c-cg.github.io/n3Builtins/#list:first)

Gets the first element of the subject list as object.`true` if and only if `$s` is a list and `$o` is the first member of that list.

**See also**  
[list:last](https://w3c-cg.github.io/n3Builtins/#list:last)

**Schema**  
`$s+ list:first $o-`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%7B+%28+%28%27a%27%29+%7B+%3Aa+%3Ab+%3Ac+%7D+42+%29+list%3Afirst+%3Fwhat+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%3Fwhat+.+%7D+.)

What is the first element of ( (a) { :a :b :c } 42 )?

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

{ ( ('a') { :a :b :c } 42 ) list:first ?what . } =\> { :result :is ?what . } .

**Result:**

@prefix : <http://example.org/\>.
:result :is ('a'). 

#### 4.4.3. list:in[](https://w3c-cg.github.io/n3Builtins/#list:in)

Checks whether the subject is a member of the object list.`true` if and only if `$o` is a list and `$s` is a member of that list.

**See also**  
[list:member](https://w3c-cg.github.io/n3Builtins/#list:member)

**Schema**  
`$s-[*] list:in $o+`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%7B+%3Fwhat+list%3Ain+%28+%22dog%22+%22penguin%22+%22cat%22+%29+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%3Fwhat+.+%7D+.)

What are the members of ( "dog" "penguin" "cat" )?

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

{ ?what list:in ( "dog" "penguin" "cat" ) . } =\> { :result :is ?what . } .

**Result:**

@prefix : <http://example.org/\>.
:result :is "dog" .
:result :is "penguin" . 
:result :is "cat" .

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%7B+%22cat%22+list%3Ain+%28+%22dog%22+%22penguin%22+%22cat%22+%29+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+true+.+%7D+.)

Does ( "dog" "penguin" "cat" ) contain a "cat"?

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

{ "cat" list:in ( "dog" "penguin" "cat" ) . } =\> { :result :is true . } .

**Result:**

@prefix : <http://example.org/\>.
:result :is true. 

#### 4.4.4. list:iterate[](https://w3c-cg.github.io/n3Builtins/#list:iterate)

Iterates over each member of the subject list, getting their index/value pairs as the object.`true` if and only if `$s` is a list and `$o` is a list with two elements: `$o.1` is a valid index in list `$s` (index starts at 0), and `$o.2` is found at that index in list `$s`.

**Schema**  
`$s+ list:iterate ( $o.1?[*] $o.2?[*] )?[*]`

where:

`$s`: `rdf:List`  
`$o.1`: `xsd:integer`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%3Alet+%3Aparam+%28%22dog%22+%22penguin%22+%22cat%22%29+.%0A%7B%0A++++%3Alet+%3Aparam+%3Fparam+.+%0A++++%3Fparam+list%3Aiterate+%282+%22cat%22%29+.++%0A%7D%0A%3D%3E+%0A%7B+%0A++++%3Aresult+%3Ais+true+.+%0A%7D+.)

Is "cat" the third item in the list ("dog" "penguin" "cat")?

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

:let :param ("dog" "penguin" "cat") .
{
    :let :param ?param . 
    ?param list:iterate (2 "cat") .  
}
=\> 
{ 
    :result :is true . 
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true .

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%7B+%28%22dog%22+%22penguin%22+%22cat%22%29+list%3Aiterate+%28%3Findex+%3Fmember%29+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%28%3Findex+%3Fmember%29+.+%7D+.)

Iterate over the list ("dog" "penguin" "cat").

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

{ ("dog" "penguin" "cat") list:iterate (?index ?member) . } =\> { :result :is (?index ?member) . } .

**Result:**

@prefix : <http://example.org/\>.
:result :is (0 "dog") .
:result :is (1 "penguin") .
:result :is (2 "cat") .

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%3Alet+%3Aparam+%28%22dog%22+%22penguin%22+%22cat%22%29+.%0A%7B%0A++++%3Alet+%3Aparam+%3Fparam+.+%0A++++%3Fparam+list%3Aiterate+%28%3Findex+%22cat%22%29+.++%0A%7D%0A%3D%3E+%0A%7B+%0A++++%3Aresult+%3Ais+%3Findex+.+%0A%7D+.)

What is the index of "cat" in the list ("dog" "penguin" "cat")?

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

:let :param ("dog" "penguin" "cat") .
{
    :let :param ?param . 
    ?param list:iterate (?index "cat") .  
}
=\> 
{ 
    :result :is ?index . 
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 2 .

#### 4.4.5. list:last[](https://w3c-cg.github.io/n3Builtins/#list:last)

Gets the last element of the subject list as object.`true` if and only if `$s` is a list and `$o` is the last member of that list.

**See also**  
[list:first](https://w3c-cg.github.io/n3Builtins/#list:first)

**Schema**  
`$s+ list:last $o-`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%7B+%281+2+3+4%29+list%3Alast+%3Flast+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%3Flast+.+%7D+.)

Extract the last element of the list (1 2 3 4).

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

{ (1 2 3 4) list:last ?last . } =\> { :result :is ?last . } .

**Result:**

@prefix : <http://example.org/\>.
:result :is 4. 

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%3Alet+%3Aparam+%281+2+3+4%29.%0A%0A%7B+%0A++++%3Alet+%3Aparam+%3Fparam+.%0A++++%3Fparam+list%3Alast+4+.+%0A%7D+%0A%3D%3E+%0A%7B+%0A++++%3Aresult+%3Ais+true+.+%0A%7D+.)

Test if the last element of the list (1 2 3 4) is 4.

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

:let :param (1 2 3 4).

{ 
    :let :param ?param .
    ?param list:last 4 . 
} 
=\> 
{ 
    :result :is true . 
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true. 

#### 4.4.6. list:length[](https://w3c-cg.github.io/n3Builtins/#list:length)

Gets the length of the subject list as object.`true` if and only if `$s` is a list and `$o` is the integer length of that list.

**Schema**  
`$s+ list:length $o-`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%7B+%281+2+3+4%29+list%3Alength+%3Flength+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%3Flength+.+%7D+.)

Calculate the length of the list (1 2 3 4).

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

{ (1 2 3 4) list:length ?length . } =\> { :result :is ?length . } .

**Result:**

@prefix : <http://example.org/\>.
:result :is 4. 

#### 4.4.7. list:member[](https://w3c-cg.github.io/n3Builtins/#list:member)

Checks whether the subject list contains the object.`true` if and only if `$s` is a list and `$o` is a member of that list.

**See also**  
[list:memberAt](https://w3c-cg.github.io/n3Builtins/#list:memberAt)  
[list:in](https://w3c-cg.github.io/n3Builtins/#list:in)

**Schema**  
`$s+ list:member $o-[*]`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%3Alet+%3Aparam+%28%22dog%22+%22penguin%22+%22cat%22%29+.%0A%0A%7B+%0A++++%3Alet+%3Aparam+%3Fparam+.%0A++++%3Fparam+list%3Amember+%22cat%22+.+%0A%7D+%0A%3D%3E+%0A%7B+%0A++++%3Aresult+%3Ais+true+.+%0A%7D+.)

Is "cat" a member of the list ("dog" "penguin" "cat")?

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

:let :param ("dog" "penguin" "cat") .

{ 
    :let :param ?param .
    ?param list:member "cat" . 
} 
=\> 
{ 
    :result :is true . 
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true.

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%7B+%28%22dog%22+%22penguin%22+%22cat%22%29+list%3Amember+%3Fmember+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%3Fmember+.+%7D+.)

Determine the members of the list ("dog" "penguin" "cat").

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

{ ("dog" "penguin" "cat") list:member ?member . } =\> { :result :is ?member . } .

**Result:**

@prefix : <http://example.org/\>.
:result :is "dog".
:result :is "penguin".
:result :is "cat".

#### 4.4.8. list:memberAt[](https://w3c-cg.github.io/n3Builtins/#list:memberAt)

Gets the member of the subject list at the given subject index as object (index starts at 0).`true` if and only if `$s.1` is a list, `$s.2` is a valid index in list `$s.1`, and `$o` is found at that index in the list.

**Schema**  
`( $s.1+ $s.2?[*] )+ list:memberAt $o?[*]`

where:

`$s.1`: `rdf:List`, `$s.2`: `xsd:integer`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%3Alet+%3Aparam+%28%22dog%22+%22penguin%22+%22cat%22%29.%0A%0A%7B%0A++++%3Alet+%3Aparam+%3Fparam+.%0A++++%28+%3Fparam+2+%29+list%3AmemberAt+%3Fthird+.%0A%7D+%0A%3D%3E+%0A%7B+%0A++++%3Aresult+%3Ais+%3Fthird+.+%0A%7D+.)

Get the third member of the list ("dog" "penguin" "cat").

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

:let :param ("dog" "penguin" "cat").

{
    :let :param ?param .
    ( ?param 2 ) list:memberAt ?third .
} 
=\> 
{ 
    :result :is ?third . 
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is "cat" .

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%3Alet+%3Aparam+%28%22dog%22+%22cat%22+%22penguin%22+%22cat%22%29.%0A%0A%7B%0A++++%3Alet+%3Aparam+%3Fparam+.%0A++++%28+%3Fparam+%3Findex+%29+list%3AmemberAt+%22cat%22+.%0A%7D+%0A%3D%3E+%0A%7B+%0A++++%3Aresult+%3Ais+%3Findex+.+%0A%7D+.)

Find the index of "cat" in the list ("dog" "cat" "penguin" "cat").

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

:let :param ("dog" "cat" "penguin" "cat").

{
    :let :param ?param .
    ( ?param ?index ) list:memberAt "cat" .
} 
=\> 
{ 
    :result :is ?index . 
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is 1 .
:result :is 3 .

#### 4.4.9. list:remove[](https://w3c-cg.github.io/n3Builtins/#list:remove)

Removes each occurrence of the subject member from the subject list, and returns the resulting list as object.`true` if and only if `$s.1` is a list, and `$o` is a list composed of the members of `$s.1` with all occurrences of `$s.2` removed (if it was present; else, `$o` will be the same list).

**See also**  
[list:append](https://w3c-cg.github.io/n3Builtins/#list:append)

**Schema**  
`( $s.1+ $s.2+ )+ list:remove $o-`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%3Alet+%3Aparam+%28%22dog%22+%22penguin%22+%22cat%22+%22penguin%22%29+.%0A%7B+%0A++++%3Alet+%3Aparam+%3Fparam+.+%0A++++%28+%3Fparam+%22parakeet%22+%29+list%3Aremove+%3Flist+.%0A%7D+%0A%3D%3E+%0A%7B+%0A++++%3Aresult+%3Ais+%3Flist+.+%0A%7D+.)

Remove non-existent "parakeet" from the list ("dog" "penguin" "cat" "penguin").

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

:let :param ("dog" "penguin" "cat" "penguin") .
{ 
    :let :param ?param . 
    ( ?param "parakeet" ) list:remove ?list .
} 
=\> 
{ 
    :result :is ?list . 
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is ("dog" "penguin" "cat" "penguin").

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+list%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flist%23%3E+.%0A%0A%3Alet+%3Aparam+%28%22dog%22+%22penguin%22+%22cat%22+%22penguin%22%29+.%0A%7B+%0A++++%3Alet+%3Aparam+%3Fparam+.+%0A++++%28+%3Fparam+%22penguin%22+%29+list%3Aremove+%3Flist+.%0A%7D+%0A%3D%3E+%0A%7B+%0A++++%3Aresult+%3Ais+%3Flist+.+%0A%7D+.)

Remove "penguin" from the list ("dog" "penguin" "cat" "penguin").

**Formula:**

@prefix : <http://example.org/\>.
@prefix list: <http://www.w3.org/2000/10/swap/list#\> .

:let :param ("dog" "penguin" "cat" "penguin") .
{ 
    :let :param ?param . 
    ( ?param "penguin" ) list:remove ?list .
} 
=\> 
{ 
    :result :is ?list . 
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is ("dog" "cat").

### 4.5. log[](https://w3c-cg.github.io/n3Builtins/#log)

#### 4.5.1. log:collectAllIn[](https://w3c-cg.github.io/n3Builtins/#log:collectAllIn)

Collects all values matching a given clause and adds them to a list.`true` if and only if, for every valid substitution of clause `$s.2`, i.e., a substitution of variables with terms that generates an instance of `$s.2` that is contained in the scope, the instance of `$s.1` generated by the same substitution is a member of list `$s.3`. This applies scoped quantification.

**Schema**  
`( $s.1- $s.2+ $s.3- )+ log:collectAllIn $o?`

where:

`$s.2`: `log:Formula`, `$s.3`: `rdf:List`  
`$o`: (Scope of the builtin. Leave as a variable to use current N3 document as scope.)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam+%22Huey%22+.%0A%3ALet+%3Aparam+%22Dewey%22+.%0A%3ALet+%3Aparam+%22Louie%22+.%0A%0A%7B%0A++++%28+%3Fparam+%7B+%3ALet+%3Aparam+%3Fparam+%7D+%28%22Huey%22+%22Dewey%22+%22Louie%22%29+%29+log%3AcollectAllIn+_%3Ax+.%0A%7D%0A%3D%3E+%0A%7B+++%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Example where the list is already given; in that case, the collected list will be compared with the given list.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param "Huey" .
:Let :param "Dewey" .
:Let :param "Louie" .

{
    ( ?param { :Let :param ?param } ("Huey" "Dewey" "Louie") ) log:collectAllIn \_:x .
}
=\> 
{   
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.

:result :is true

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam+%22Huey%22+.%0A%3ALet+%3Aparam+%22Dewey%22+.%0A%3ALet+%3Aparam+%22Louie%22+.%0A%0A%7B%0A++++%28+%3Fparam+%7B+%3ALet+%3Aparam+%3Fparam+%7D+%3FallParams+%29+log%3AcollectAllIn+_%3Ax+.%0A%0A++++%23+Variable+to+be+collected+can+also+be+part+of+a+list+or+graph+term%0A++++%28+%28%3Fparam%29+%7B+%3ALet+%3Aparam+%3Fparam+%7D+%3FnestedParams+%29+log%3AcollectAllIn+_%3Ax+.%0A%0A++++%23+Add+some+extra+criteria+on+variable+values+to+be+collected%0A++++%28+%3Fparam%0A++++++++%7B+%0A++++++++++++%3ALet+%3Aparam+%3Fparam+.%0A++++++++++++%3Fparam+string%3AlessThan+%22Louie%22++.%0A++++++++%7D+%0A++++++%3FfilteredParams+%29+log%3AcollectAllIn+_%3Ax+.%0A%7D%0A%3D%3E+%0A%7B+++%0A++++%3Aresult1+%3Ais+%3FallParams+.%0A++++%3Aresult2+%3Ais+%3FnestedParams+.%0A++++%3Aresult3+%3Ais+%3FfilteredParams+.%0A%7D+.)

Set of basic examples for log:collectAllIn.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param "Huey" .
:Let :param "Dewey" .
:Let :param "Louie" .

{
    ( ?param { :Let :param ?param } ?allParams ) log:collectAllIn \_:x .

    # Variable to be collected can also be part of a list or graph term
    ( (?param) { :Let :param ?param } ?nestedParams ) log:collectAllIn \_:x .

    # Add some extra criteria on variable values to be collected
    ( ?param
        { 
            :Let :param ?param .
            ?param string:lessThan "Louie"  .
        } 
      ?filteredParams ) log:collectAllIn \_:x .
}
=\> 
{   
    :result1 :is ?allParams .
    :result2 :is ?nestedParams .
    :result3 :is ?filteredParams .
} .

**Result:**

@prefix : <http://example.org/\>.

:result1 :is ("Huey" "Dewey" "Louie").
:result2 :is (("Huey") ("Dewey") ("Louie")).
:result3 :is ("Huey" "Dewey").

#### 4.5.2. log:conclusion[](https://w3c-cg.github.io/n3Builtins/#log:conclusion)

Gets all possible conclusions from the subject graph term, including rule inferences (deductive closure), as the object graph term.`true` if and only if `$o` is the set of conclusions which can be drawn from `$s` (deductive closure), by applying any rules it contains to the data it contains.

**Schema**  
`$s+ log:conclusion $o?`

where:

`$s`: `log:Formula`  
`$o`: `log:Formula`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%3Alet+%3Aparam+%7B+%0A++++%3AFelix+a+%3ACat+.+%0A++++%7B+%3FX+a+%3ACat+.+%7D+%3D%3E+%7B+%3FX+%3Asays+%22Meow%22+.+%7D+.%0A%7D+.%0A%0A%7B+%0A++++%3Alet+%3Aparam+%3Fparam+.%0A++++%3Fparam+log%3Aconclusion+%3Fconclusion+.%0A%7D+%0A%3D%3E+%0A%7B+%0A++++%3Aresult+%3Ais+%3Fconclusion+.+%0A%7D+.)

Draw all conclusions from the formula ":Felix a :Cat . { ?X a :Cat } =\> { ?X :says "Meow" . }".

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

:let :param { 
    :Felix a :Cat . 
    { ?X a :Cat . } =\> { ?X :says "Meow" . } .
} .

{ 
    :let :param ?param .
    ?param log:conclusion ?conclusion .
} 
=\> 
{ 
    :result :is ?conclusion . 
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is {
    :Felix a :Cat. 
    :Felix :says "Meow". 
    { ?S a :Cat . } =\> { ?S :says "Meow" . } .
} .

#### 4.5.3. log:conjunction[](https://w3c-cg.github.io/n3Builtins/#log:conjunction)

Merges the graph terms from the subject list into a single graph term as object.`true` if and only if `$o` is a graph term that is the logical conjunction of each of the graph terms `$s.i` (i.e., includes all their triples, removing any duplicates) .

**Schema**  
`( $s.i+ )+ log:conjunction $o?`

where:

`$s.i`: `log:Formula`  
`$o`: `log:Formula`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B+%0A++++%28+%7B+%3AFelix+a+%3ACat+.+%7D%0A++++++%7B+%3APluto+a+%3ADog+.+%7D++%0A++++++%7B+%3APingu+a+%3APenguin+.+%7D%0A++++%29+log%3Aconjunction+%3Fmerged+.%0A%7D+%0A%3D%3E+%0A%7B+%0A++++%3Aresult+%3Ais+%3Fmerged+.+%0A%7D+.)

Merge the formulas "{ :Felix a :Cat . }" , "{ :Pluto a :Dog . }", "{ :Pingu a :Penguin . }" .

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{ 
    ( { :Felix a :Cat . }
      { :Pluto a :Dog . }  
      { :Pingu a :Penguin . }
    ) log:conjunction ?merged .
} 
=\> 
{ 
    :result :is ?merged . 
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is { 
    :Felix a :Cat . 
    :Pingu a :Penguin . 
    :Pluto a :Dog . 
} .

#### 4.5.4. log:content[](https://w3c-cg.github.io/n3Builtins/#log:content)

Dereferences the subject IRI and retrieves the online resource as the object string.`true` if and only if `$o` is a string that represents the online resource to which `$s` is dereferenced.

**Schema**  
`$s+ log:content $o?`

where:

`$s`: `log:Uri`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B+%0A++++%3Chttps%3A%2F%2Fwww.w3.org%2FPeople%2FBerners-Lee%2Fcard%3E+log%3Acontent+%3Fcontent+.%0A%7D+%0A%3D%3E+%0A%7B+%0A++++%3Aresult+%3Ais+%3Fcontent+.+%0A%7D+.)

Fetch the content of https://www.w3.org/People/Berners-Lee/card.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{ 
    <https://www.w3.org/People/Berners-Lee/card\> log:content ?content .
} 
=\> 
{ 
    :result :is ?content . 
} .

**Result:**

:result :is "...the content of https://www.w3.org/People/Berners-Lee/card ...". 

#### 4.5.5. log:dtlit[](https://w3c-cg.github.io/n3Builtins/#log:dtlit)

Creates a datatyped literal as object, based on the string value and datatype IRI in the subject list.`true` if and only if `$o` is a datatyped literal with string value corresponding to `$s.1` and datatype IRI corresponding to `$s.2`.

**See also**  
[log:langlit](https://w3c-cg.github.io/n3Builtins/#log:langlit)

**Schema**  
`( $s.1? $s.2? )? log:dtlit $o?`

where:

`$s.1`: `xsd:string`, `$s.2`: `log:Uri`  
`$o`: `log:Literal`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E+.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B+%28+%221971-05-05%22+xsd%3Adate+%29+log%3Adtlit+%3Ftyped+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%3Ftyped+.+%7D+.)

Create a datatyped literal from the string "1971-05-05" and the type xsd:date.

**Formula:**

@prefix : <http://example.org/\>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\> .
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{ ( "1971-05-05" xsd:date ) log:dtlit ?typed } =\> { :result :is ?typed . } .

**Result:**

@prefix : <http://example.org/\>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\> .
:result :is "1971-05-05"^^xsd:date.

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+xsd%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2001%2FXMLSchema%23%3E+.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B+%0A++++%28+%3Fstring+%3Ftype+%29+log%3Adtlit+%221971-05-05%22%5E%5Exsd%3Adate+.%0A%7D+%0A%3D%3E+%0A%7B+%0A++++%3Aresult+%3Ais+%28+%3Fstring+%3Ftype+%29+.+%0A%7D+.)

Parse the datatyped literal "1971-05-05"^^xsd:date into a string and data type IRI.

**Formula:**

@prefix : <http://example.org/\>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\> .
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{ 
    ( ?string ?type ) log:dtlit "1971-05-05"^^xsd:date .
} 
=\> 
{ 
    :result :is ( ?string ?type ) . 
} .

**Result:**

@prefix : <http://example.org/\>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#\> .
:result :is ("1971-05-05" xsd:date).

#### 4.5.6. log:equalTo[](https://w3c-cg.github.io/n3Builtins/#log:equalTo)

Checks whether the subject and object N3 terms are the same (comparison occurs on the syntax level). Can also be used to bind values to variables (see examples).`true` if and only if `$s` and `$o` are the same N3 term. Not to be confused with owl:sameAs. Literals will be compared exactly: their datatypes must be identical (in case of strings, language tags must be identical).

**See also**  
[log:notEqualTo](https://w3c-cg.github.io/n3Builtins/#log:notEqualTo)

**Schema**  
`$s? log:equalTo $o?`

**Examples**

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B%0A++++_%3Ax+log%3AequalTo+42+.%0A++++%3Fq++log%3AequalTo+%22Cat%22%40en+.%0A%0A++++%23+This+will+fail+because+_%3Ax+is+already+assigned+to+42+.%0A++++%23+_%3Ax+log%3AequalTo+17+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fq+.%0A%7D+.)

Assign a value to an existential or universal variable.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{
    \_:x log:equalTo 42 .
    ?q  log:equalTo "Cat"@en .

    # This will fail because \_:x is already assigned to 42 .
    # \_:x log:equalTo 17 .
}
=\>
{
    :result :is ?q .
} . 

**Result:**

@prefix : <http://example.org/\>.
:result :is "Cat"@en .

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B%0A++++%28+%3Fx+%3Fy+%3Fz+%29+log%3AequalTo+%28+1+2+3+%29%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fx+%2C+%3Fy+%2C+%3Fz+.%0A%7D+.)

Assign values from the object list to universal variables given in the subject list. This can be compared to "destructuring" or "unpacking" in programming languages such as JavaScript or Python. In contrast to those languages, however, it works in either direction in N3. This mechanism works because an effort is made to ensure the truth of builtin statements in N3.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{
    ( ?x ?y ?z ) log:equalTo ( 1 2 3 )
}
=\>
{
    :result :is ?x , ?y , ?z .
} . 

**Result:**

@prefix : <http://example.org/\>.
:result :is 1 , 2 , 3 . # objects can be in any order

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%40prefix+owl%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2002%2F07%2Fowl%23%3E+.%0A%0A%3Chttp%3A%2F%2Ffamous.web.site%3E+owl%3AsameAs+%3Chttp%3A%2F%2Fmirror.famous.web.site%3E+.%0A%0A%7B%0A++++%3Chttp%3A%2F%2Ffamous.web.site%3E+log%3AequalTo+%3Chttp%3A%2F%2Ffamous.web.site%3E+.%0A%0A++++%23+But+not%0A++++%23%0A++++%23+%3Chttp%3A%2F%2Ffamous.web.site%3E+log%3AequalTo+%3Chttp%3A%2F%2Fmirror.famous.web.site%3E+.%0A++++%23%0A++++%23+and+not%0A++++%23%0A++++%23+%3Chttp%3A%2F%2Ffamous.web.site%23123%3E+log%3AequalTo+%3Chttp%3A%2F%2Ffamous.web.site%3E+.%0A++++%23%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Determine is equal to itself .

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .
@prefix owl: <http://www.w3.org/2002/07/owl#\> .

<http://famous.web.site\> owl:sameAs <http://mirror.famous.web.site\> .

{
    <http://famous.web.site\> log:equalTo <http://famous.web.site\> .

    # But not
    #
    # <http://famous.web.site\> log:equalTo <http://mirror.famous.web.site\> .
    #
    # and not
    #
    # <http://famous.web.site#123\> log:equalTo <http://famous.web.site\> .
    #
}
=\>
{
    :result :is true .
} . 

**Result:**

@prefix : <http://example.org/\>.
:result :is true. 

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B%0A++++1+log%3AequalTo+1+.%0A++++%22Cat%22+log%3AequalTo+%22Cat%22+.%0A++++%7B+%3AA+%3AB+%3AC+.+%3AD+%3AE+%3AF+.+%7D+log%3AequalTo+%7B+%3AD+%3AE+%3AF+.+%3AA+%3AB+%3AC+.+%7D+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Determine if 1 is equal to 1 and "Cat" is equal to "Cat" and { :A :B :C . :D :E :F } is equal to { :D :E :F . :A :B :C }.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{
    1 log:equalTo 1 .
    "Cat" log:equalTo "Cat" .
    { :A :B :C . :D :E :F . } log:equalTo { :D :E :F . :A :B :C . } .
}
=\>
{
    :result :is true .
} . 

**Result:**

@prefix : <http://example.org/\>.
:result :is true. 

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B%0A++++%28+%22War+and+Peace%22+%22Leo+Tolstoy%22+1225+%29+log%3AequalTo+%28+%3Ftitle+%3Fauthor+%3FnumPages+%29+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Ftitle+%2C+%3Fauthor+%2C+%3FnumPages+.%0A%7D+.)

Assign values from the object list to universal variables given in the subject list. This can be compared to "destructuring" or "unpacking" in programming languages such as JavaScript or Python. In contrast to those languages, however, it works in either direction in N3. This mechanism works because an effort is made to ensure the truthfulness of builtin statements in N3.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{
    ( "War and Peace" "Leo Tolstoy" 1225 ) log:equalTo ( ?title ?author ?numPages ) .
}
=\>
{
    :result :is ?title , ?author , ?numPages .
} . 

**Result:**

@prefix : <http://example.org/\>.
:result :is "War and Peace" , "Leo Tolstoy" , 1225 . # objects can be in any order

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B%0A++++%23+This+will+fail%0A++++%22Cat%22+log%3AequalTo+%22Cat%22%40en+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Determine if "Cat" is equal to "Cat"@en .

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{
    # This will fail
    "Cat" log:equalTo "Cat"@en .
}
=\>
{
    :result :is true .
} . 

**Result:**

@prefix : <http://example.org/\>.
# no results

#### 4.5.7. log:forAllIn[](https://w3c-cg.github.io/n3Builtins/#log:forAllIn)

Two clauses are given in the subject list: for every match of the first clause, the builtin checks whether the second clause also holds for that match.`true` if and only if, for every valid substitution of clause `$s.1`, i.e., a substitution of variables with terms that generates an instance of `$s.1` that is contained in the scope, the instance of `$s.2` generated by the same substitution is also contained in the scope. This applies a scoped quantification.

**Schema**  
`( $s.1+ $s.2+ )+ log:forAllIn $o?`

where:

`$s.1`: `log:Formula`, `$s.2`: `log:Formula`  
`$o`: (Scope of the builtin. Leave as a variable to use current N3 document as scope.)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%3Ac+a+%3ACompositeTask+%3B%0A++++%3AsubTask+%3As1+%2C+%3As2+%2C+%3As3+.%0A%3As1+%3Astate+%3ACompleted+.%0A%3As2+%3Astate+%3ACompleted+.+%0A%3As3+%3Astate+%3ACompleted+.%0A%0A%7B%0A++++%3Fc+a+%3ACompositeTask+.%0A++++%28+%7B+%3Fc+%3AsubTask+%3Fs+%7D+%7B+%3Fs+%3Astate+%3ACompleted+%7D+%29+log%3AforAllIn+_%3At+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

For each subtask of a composite task, check whether the subtask is completed.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

:c a :CompositeTask ;
    :subTask :s1 , :s2 , :s3 .
:s1 :state :Completed .
:s2 :state :Completed . 
:s3 :state :Completed .

{
    ?c a :CompositeTask .
    ( { ?c :subTask ?s } { ?s :state :Completed } ) log:forAllIn \_:t .
}
=\>
{
    :result :is true .
} . 

**Result:**

@prefix : <http://example.org/\>.
:result :is true. 

#### 4.5.8. log:includes[](https://w3c-cg.github.io/n3Builtins/#log:includes)

Checks whether the subject graph term includes the object graph term (taking into account variables). Can also be used to bind variables to values within the graph contents (see examples).`true` if and only if there exists some substitution which, when applied to `$s` and `$o`, creates graph terms `$s`' and `$o`' such that every statement in `$o`' is also in `$s`''. Variable substitution is applied recursively to nested compound terms such as graph terms and lists.

**See also**  
[log:notIncludes](https://w3c-cg.github.io/n3Builtins/#log:notIncludes)

**Schema**  
`$s+ log:includes $o+`

where:

`$s`: `log:Formula`  
(Can also be left as a variable to use current N3 document as scope.)  
`$o`: `log:Formula`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B+%0A++++%7B+%3AFelix+a+%3ACat+%7D+log%3Aincludes+%7B+%3FX+a+%3ACat+%7D+.%0A%7D+%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3FX+.%0A%7D+.)

Check whether the formula { :Felix a :Cat } includes { ?X a :Cat }.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{ 
    { :Felix a :Cat } log:includes { ?X a :Cat } .
} 
=\>
{
    :result :is ?X .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is :Felix .

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%3AFelix+a+%3ACat+.%0A%3ATom+a+%3ACat+.%0A%3ARex+a+%3ADog+.%0A%0A%7B+%0A++++_%3At+log%3Aincludes+%7B+%3FX+a+%3ACat+%7D+.%0A%7D+%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3FX+.%0A%7D+.)

Check whether the current N3 document includes { ?X a :Cat }.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

:Felix a :Cat .
:Tom a :Cat .
:Rex a :Dog .

{ 
    \_:t log:includes { ?X a :Cat } .
} 
=\>
{
    :result :is ?X .
} .

**Result:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\>.

:result :is :Felix.
:result :is :Tom.

#### 4.5.9. log:langlit[](https://w3c-cg.github.io/n3Builtins/#log:langlit)

Creates a language-tagged literal as object, based on the string value and language tag (see BCP47) in the subject list.`true` if and only if `$o` is a language-tagged literal with string value corresponding to `$s.1` and language tag corresponding to `$s.2`. `$s.2` should be a string in the form of a BCP47 language tag.

**See also**  
[log:dtlit](https://w3c-cg.github.io/n3Builtins/#log:dtlit)

**Schema**  
`( $s.1? $s.2? )? log:langlit $o?`

where:

`$s.1`: `xsd:string`, `$s.2`: `xsd:string`  
`$o`: `log:Literal`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%7B+%28%22hello%22+%22en%22%29+log%3Alanglit+%3FX+%7D+%3D%3E+%7B+%3FX+a+%3AResult+%7D+.)

Create a language-tagged literal from the string "hello" and language tag "en".

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .
{ ("hello" "en") log:langlit ?X } =\> { ?X a :Result } .

**Result:**

@prefix : <http://example.org/\>.
"hello"@en a :Result .

#### 4.5.10. log:notEqualTo[](https://w3c-cg.github.io/n3Builtins/#log:notEqualTo)

Checks whether the subject and object N3 terms are \_not\_ the same (comparison occurs on the syntax level).`true` if and only if `$s` and `$o` are \_not\_ the same N3 term.

**See also**  
[log:equalTo](https://w3c-cg.github.io/n3Builtins/#log:equalTo)

**Schema**  
`$s+ log:notEqualTo $o+`

**Examples**

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B%0A++++1+log%3AnotEqualTo+2+.%0A++++%22Cat%22+log%3AnotEqualTo+%22CAT%22+.%0A++++%7B+%3AA+%3AB+%3AC+.+%7D+log%3AnotEqualTo+%7B+%3AC+%3AB+%3AA+.+%7D+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Determine if 1 is not equal to 2 and "Cat" is not equal to "CAT" and { :A :B :C . } is not equal to { :C :B :A }.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{
    1 log:notEqualTo 2 .
    "Cat" log:notEqualTo "CAT" .
    { :A :B :C . } log:notEqualTo { :C :B :A . } .
}
=\>
{
    :result :is true .
} . 

**Result:**

@prefix : <http://example.org/\>.
:result :is true .

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B%0A+++%0A++++%7B+%3AA+%3AB+%3AC+.+%7D+log%3AnotEqualTo+%7B+%3AA+%3AB+%3Fc+%7D+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Check whether two graph terms, one containing a universal variable, are not equal.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{
   
    { :A :B :C . } log:notEqualTo { :A :B ?c } .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
# no result (?c can be unified with :C)

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B%0A++++%22Cat%22+log%3AnotEqualTo+%22Cat%22%40en+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Determine if "Cat" is not equal to "Cat"@en .

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{
    "Cat" log:notEqualTo "Cat"@en .
}
=\>
{
    :result :is true .
} . 

**Result:**

@prefix : <http://example.org/\>.
:result :is true .

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B%0A++++_%3Ax+log%3AnotEqualTo+42+.%0A++++%3Fq++log%3AnotEqualTo+%22Cat%22%40en+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Check if an existential or universal variable is not equal to a value.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{
    \_:x log:notEqualTo 42 .
    ?q  log:notEqualTo "Cat"@en .
}
=\>
{
    :result :is true .
} . 

**Result:**

@prefix : <http://example.org/\>.
# no result (the variables \_:x and ?q are not bounded) 

#### 4.5.11. log:notIncludes[](https://w3c-cg.github.io/n3Builtins/#log:notIncludes)

Checks whether the subject graph term \_does not\_ include the object graph term (taking into account variables)`true` if and only if `$s log:includes $o` is `false`.

**See also**  
[log:includes](https://w3c-cg.github.io/n3Builtins/#log:includes)

**Schema**  
`$s+ log:notIncludes $o+`

where:

`$s`: `log:Formula`  
`$o`: `log:Formula`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B+%0A++++%23+Dynamic+evaluation+of+%3FX+and+%3FY%0A++++%3FX+log%3AnotIncludes+%3FY+.%0A++++%3FX+log%3AequalTo+%7B+%3Aa+%3Ab+%3Ac+%7D.%0A++++%3FY+log%3AequalTo+%7B+%3Aa+%3Ab+%3Ad+%7D.%0A%7D+%0A%3D%3E++++++++++++++%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Check whether the formula { :a :b :c } does not include { :a :b :d }.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{ 
    # Dynamic evaluation of ?X and ?Y
    ?X log:notIncludes ?Y .
    ?X log:equalTo { :a :b :c }.
    ?Y log:equalTo { :a :b :d }.
} 
=\>              
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true.

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B+%0A++++%7B+%3AFelix+a+%3ACat+%7D+log%3AnotIncludes+%7B+%3FX+%3Aeats+%3FY+%7D+.%0A%7D+%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Check whether the formula { :Felix a :Cat } does not include { ?X :eats ?Y }.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{ 
    { :Felix a :Cat } log:notIncludes { ?X :eats ?Y } .
} 
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true.

#### 4.5.12. log:outputString[](https://w3c-cg.github.io/n3Builtins/#log:outputString)

The N3 reasoner will print the object strings in the order of the subject keys, instead of printing the derivations or deductive closure. This may require a reasoner flag to be set.The concrete semantics of this builtin (e.g., which N3 resource types are supported) will depend on the N3 reasoner.

**Schema**  
`$s+ log:outputString $o+`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A_%3A2+log%3AoutputString+%22This+is+the+second+line%5Cn%22+.%0A_%3A1+log%3AoutputString+%22This+is+the+first+line%5Cn%22+.)

Print the two string "This is the first line " , "This is the second line " to the output.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

\_:2 log:outputString "This is the second line\\n" .
\_:1 log:outputString "This is the first line\\n" .

**Result:**

\# If the reasoner support the outputString options
This is the first line
This is the second line

#### 4.5.13. log:parsedAsN3[](https://w3c-cg.github.io/n3Builtins/#log:parsedAsN3)

Parses the subject string into an object graph term.`true` if and only if `$s`, when parsed as N3, gives `$o`. `$s` should be a syntactically valid string in N3 format.

**See also**  
[log:semantics](https://w3c-cg.github.io/n3Builtins/#log:semantics)

**Schema**  
`$s+ log:parsedAsN3 $o-`

where:

`$s`: `xsd:string`  
(should be a syntactically valid string in N3 format)  
`$o`: `log:Formula`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%3ALet+%3Aparam+%22%22%22%0A%40prefix+%3A+%3Curn%3Aexample%3A%3E+.%0A%3ASocrates+a+%3AHuman+.%0A%22%22%22+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3FX+.%0A++++%3FX+log%3AparsedAsN3+%3FY+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3FY+.%0A%7D+.)

Parse the string ':Socrates a :Human .' as N3.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

:Let :param """
@prefix : <urn:example:\> .
:Socrates a :Human .
""" .

{
    :Let :param ?X .
    ?X log:parsedAsN3 ?Y .
}
=\>
{
    :result :is ?Y .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is { <urn:example:Socrates\> a <urn:example:Human\> . } .

#### 4.5.14. log:rawType[](https://w3c-cg.github.io/n3Builtins/#log:rawType)

Gets the type of the N3 resource.`true` if and only if the N3 resource type of `$s` is `$o`. N3 resource types include `log:Formula`, `log:Literal`, `rdf:List` or `log:Other`.

**Schema**  
`$s+ log:rawType $o-`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B%0A++++%281+2+3+4%29+log%3ArawType+%3FlistType+.%0A++++%7B+%3As+%3Ap+%3Ao+%7D+log%3ArawType+%3FgraphType+.%0A%7D+%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%28+%3FlistType+%3FgraphType+%29+.%0A%7D+.)

Get the type of lists and graph terms.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{
    (1 2 3 4) log:rawType ?listType .
    { :s :p :o } log:rawType ?graphType .
} 
=\>
{
    :result :is ( ?listType ?graphType ) .
} .

**Result:**

@prefix : <http://example.org/\>.
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .
:result :is ( rdf:List log:Formula ) .

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B%0A++++%3Chttp%3A%2F%2Fwww.w3c.org%3E+log%3ArawType+%3FresourceType+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3FresourceType+.%0A%7D+.)

Get the type of resources.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{
    <http://www.w3c.org\> log:rawType ?resourceType .
}
=\>
{
    :result :is ?resourceType .
} .

**Result:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .
:result :is log:Other.

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B%0A++++%22Hello%22+log%3ArawType+%3FstringType+.%0A++++42+log%3ArawType+%3FintegerType+.%0A++++true+log%3ArawType+%3FtrueType+.%0A++++false+log%3ArawType+%3FfalseType+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%28+%3FstringType+%3FintegerType+%3FtrueType+%3FfalseType+%29+.%0A%7D+.)

Get the type of literal resources.

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{
    "Hello" log:rawType ?stringType .
    42 log:rawType ?integerType .
    true log:rawType ?trueType .
    false log:rawType ?falseType .
}
=\>
{
    :result :is ( ?stringType ?integerType ?trueType ?falseType ) .
} .

**Result:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .
:result :is ( log:Literal log:Literal log:Literal log:Literal ) .

#### 4.5.15. log:semantics[](https://w3c-cg.github.io/n3Builtins/#log:semantics)

Gets as object the graph term that results from parsing an online (N3) string, found by dereferencing the subject IRI.`true` if and only if `$o` is a graph term that results from parsing the string that results from dereferencing `$s`.

**Schema**  
`$s+ log:semantics $o?`

where:

`$s`: `log:Uri`  
`$o`: `log:Formula`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B+%3Csemantics.data%3E+log%3Asemantics+%3Fsemantics+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%3Fsemantics+%7D+.)

Read the contents of the file `<semantics.data>` and parse it as Notation3. We assume `<semantics.data>` contains the text:

@prefix : <http://example.org/\>.
:Socrates a :Human .

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{ <semantics.data\> log:semantics ?semantics . } =\> { :result :is ?semantics } .

**Result:**

@prefix : <http://example.org/\>.
:result :is { :Socrates a :Human . } .

#### 4.5.16. log:semanticsOrError[](https://w3c-cg.github.io/n3Builtins/#log:semanticsOrError)

Either gets as object the graph term that results from parsing an online (N3) string, found by dereferencing the subject IRI; or an error message that explains what went wrong.`true` if and only if (a) `$o` is a graph term that results from parsing the string that results from dereferencing `$s`; or (b) an error message explaining what went wrong.

**Schema**  
`$s+ log:semanticsOrError $o?`

where:

`$s`: `log:Uri`  
`$o`: (either a log:Formula or xsd:string)

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B+%3Cerror.data%3E+log%3Asemantics+%3Fsemantics+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%3Fsemantics+%7D+.)

Read the contents a non existing `<error.data>` and parse it as Notation3 (which of course will fail).

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{ <error.data\> log:semantics ?semantics . } =\> { :result :is ?semantics } .

**Result:**

@prefix : <http://example.org/\>.
:result :is """Unable to access document <file:////tmp/error.data\>, because:
    <urlopen error \[Errno 2\] No such file or directory: '//tmp/error.data'\>""" .

#### 4.5.17. log:skolem[](https://w3c-cg.github.io/n3Builtins/#log:skolem)

Gets as object a skolem IRI that is a function of the subject (commonly a list) and a concrete reasoning run (implicit); for one reasoning run, the same subject will always result in the same skolem IRI.`true` if and only if `$o` is a skolem IRI that is produced by applying a skolem function to the subject.

**Schema**  
`$s+ log:skolem $o-`

**Examples**

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B+%28%3Aabc+77+%22xyz%22%29+log%3Askolem+%3Fskolem+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%3Fskolem+%7D+.)

Generate a unique Skolem IRI from the list (:abc 77 "xyz") .

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{ (:abc 77 "xyz") log:skolem ?skolem . } =\> { :result :is ?skolem } .

**Result:**

@prefix : <http://example.org/\>.
:result :is <http://www.w3.org/2000/10/swap/genid#zmgk3Vt\_z\_u7FQlk1NmqIw\> . 

#### 4.5.18. log:uri[](https://w3c-cg.github.io/n3Builtins/#log:uri)

Gets as object the string representation of the subject URI.`true` if and only if `$o` is the string representation of `$s`.

**Schema**  
`$s? log:uri $o?`

where:

`$s`: (a URI)  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+log%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Flog%23%3E+.%0A%0A%7B+%3Chttps%3A%2F%2Fwww.w3.org%3E+log%3Auri+%3Furi+.+%7D+%3D%3E+%7B+%3Aresult+%3Ais+%3Furi+.+%7D+.)

Parse the URI into a string .

**Formula:**

@prefix : <http://example.org/\>.
@prefix log: <http://www.w3.org/2000/10/swap/log#\> .

{ <https://www.w3.org\> log:uri ?uri . } =\> { :result :is ?uri . } .

**Result:**

@prefix : <http://example.org/\>.
:result :is "https://www.w3.org" .

### 4.6. string[](https://w3c-cg.github.io/n3Builtins/#string)

#### 4.6.1. string:concatenation[](https://w3c-cg.github.io/n3Builtins/#string:concatenation)

Concatenates the strings from the subject list into a single string as object.`true` if and only if the string concatenation of `$s.i` equals `$o`.

**Schema**  
`( $s.i+ )+ string:concatenation $o-`

where:

`$s.i`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam+%28+%22hello%22+%22+%22+%22world%21%22+%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+string%3Aconcatenation+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Concatenates the string "hello", " " and "world!".

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param ( "hello" " " "world!" ) .

{
    :Let :param ?param .
    ?param string:concatenation ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is "hello world!". 

#### 4.6.2. string:contains[](https://w3c-cg.github.io/n3Builtins/#string:contains)

Checks whether the subject string contains the object string.`true` if and only if `$s` contains `$o`.

**See also**  
[string:containsIgnoringCase](https://w3c-cg.github.io/n3Builtins/#string:containsIgnoringCase)

**Schema**  
`$s+ string:contains $o+`

where:

`$s`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam1+%22hello+world%21%22+.%0A%3ALet+%3Aparam2+%22llo+worl%22.%0A%7B%0A++++%3ALet+%3Aparam1+%3Fparam1+.%0A++++%3ALet+%3Aparam2+%3Fparam2+.%0A++++%3Fparam1+string%3Acontains+%3Fparam2+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Checks whether the string "hello world!" contains the string "llo worl".

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param1 "hello world!" .
:Let :param2 "llo worl".
{
    :Let :param1 ?param1 .
    :Let :param2 ?param2 .
    ?param1 string:contains ?param2 .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true . 

#### 4.6.3. string:containsIgnoringCase[](https://w3c-cg.github.io/n3Builtins/#string:containsIgnoringCase)

Checks whether the subject string contains the object string, ignoring differences between lowercase and uppercase.`true` if and only if `$s` contains `$o` when ignoring case differences.

**See also**  
[string:contains](https://w3c-cg.github.io/n3Builtins/#string:contains)

**Schema**  
`$s+ string:containsIgnoringCase $o+`

where:

`$s`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam1+%22hello+world%21%22+.%0A%3ALet+%3Aparam2+%22lLO+woRl%22.%0A%7B%0A++++%3ALet+%3Aparam1+%3Fparam1+.%0A++++%3ALet+%3Aparam2+%3Fparam2+.%0A++++%3Fparam1+string%3AcontainsIgnoringCase+%3Fparam2+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Checks whether the string "hello world!" contains the string "lLO woRl".

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param1 "hello world!" .
:Let :param2 "lLO woRl".
{
    :Let :param1 ?param1 .
    :Let :param2 ?param2 .
    ?param1 string:containsIgnoringCase ?param2 .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true . 

#### 4.6.4. string:endsWith[](https://w3c-cg.github.io/n3Builtins/#string:endsWith)

Checks whether the subject string ends with the object string.`true` if and only if `$s` ends with `$o`.

**Schema**  
`$s+ string:endsWith $o+`

where:

`$s`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam1+%22hello+world%21%22+.%0A%3ALet+%3Aparam2+%22orld%21%22.%0A%7B%0A++++%3ALet+%3Aparam1+%3Fparam1+.%0A++++%3ALet+%3Aparam2+%3Fparam2+.%0A++++%3Fparam1+string%3AendsWith+%3Fparam2+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Checks whether the string "hello world!" ends with "orld!".

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param1 "hello world!" .
:Let :param2 "orld!".
{
    :Let :param1 ?param1 .
    :Let :param2 ?param2 .
    ?param1 string:endsWith ?param2 .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true . 

#### 4.6.5. string:equalIgnoringCase[](https://w3c-cg.github.io/n3Builtins/#string:equalIgnoringCase)

Checks whether the subject string is the same as the object string, ignoring differences between lowercase and uppercase.`true` if and only if `$s` is the same string as `$o` when ignoring case differences.

**Schema**  
`$s+ string:equalIgnoringCase $o+`

where:

`$s`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam1+%22hello+world%21%22+.%0A%3ALet+%3Aparam2+%22hELLo+wORld%21%22+.%0A%7B%0A++++%3ALet+%3Aparam1+%3Fparam1+.%0A++++%3ALet+%3Aparam2+%3Fparam2+.%0A++++%3Fparam1+string%3AequalIgnoringCase+%3Fparam2+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Checks whether the string "hello world!" is equal to "hELLo wORld!" ignoring the case .

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param1 "hello world!" .
:Let :param2 "hELLo wORld!" .
{
    :Let :param1 ?param1 .
    :Let :param2 ?param2 .
    ?param1 string:equalIgnoringCase ?param2 .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true . 

#### 4.6.6. string:format[](https://w3c-cg.github.io/n3Builtins/#string:format)

Calculates the object as the result of replacing the tags in the first string from the subject list with the remaining strings from the subject list. See C’s sprintf function for details on these tags.`true` if and only if `$o` is the result of replacing the tags found in `$s.(i=1)` with the strings `$s.(i>1)`

**Schema**  
`( $s.i+ )+ string:format $o-`

where:

`$s.i`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam+%28+%22%25s%3A%2F%2F%25s%2F%25s%22+%22https%22+%22w3c.github.io%22+%22N3%2Fspec%2F%22+%29+.%0A%0A%7B%0A++++%3ALet+%3Aparam+%3Fparam+.%0A++++%3Fparam+string%3Aformat+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Calculate the result of applying the format "%s://%s/%s" to the strings "https", "w3c.github.io" and "N3/spec" .

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param ( "%s://%s/%s" "https" "w3c.github.io" "N3/spec/" ) .

{
    :Let :param ?param .
    ?param string:format ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is "https://w3c.github.io/N3/spec/". 

#### 4.6.7. string:greaterThan[](https://w3c-cg.github.io/n3Builtins/#string:greaterThan)

Checks whether the subject string is greater than the object string, according to Unicode code order.`true` if and only if `$s` is greater than `$o` as per the Unicode code order.

**See also**  
[string:notGreaterThan](https://w3c-cg.github.io/n3Builtins/#string:notGreaterThan)

**Schema**  
`$s+ string:greaterThan $o+`

where:

`$s`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam1+%22Penguin%22+.%0A%3ALet+%3Aparam2+%22Cat%22.%0A%7B%0A++++%3ALet+%3Aparam1+%3Fparam1+.%0A++++%3ALet+%3Aparam2+%3Fparam2+.%0A++++%3Fparam1+string%3AgreaterThan+%3Fparam2+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Checks whether the string "Pengiun" is greater than the string "Cat" .

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param1 "Penguin" .
:Let :param2 "Cat".
{
    :Let :param1 ?param1 .
    :Let :param2 ?param2 .
    ?param1 string:greaterThan ?param2 .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true . 

#### 4.6.8. string:lessThan[](https://w3c-cg.github.io/n3Builtins/#string:lessThan)

Checks whether the subject string is less than the object string, according to Unicode code order.`true` if and only if `$s` is less than `$o` as per the Unicode code order.

**See also**  
[string:notLessThan](https://w3c-cg.github.io/n3Builtins/#string:notLessThan)

**Schema**  
`$s+ string:lessThan $o+`

where:

`$s`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam1+%22Cat%22+.%0A%3ALet+%3Aparam2+%22Penguin%22.%0A%7B%0A++++%3ALet+%3Aparam1+%3Fparam1+.%0A++++%3ALet+%3Aparam2+%3Fparam2+.%0A++++%3Fparam1+string%3AlessThan+%3Fparam2+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Checks whether the string "Cat" is less than the string "Penguin" .

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param1 "Cat" .
:Let :param2 "Penguin".
{
    :Let :param1 ?param1 .
    :Let :param2 ?param2 .
    ?param1 string:lessThan ?param2 .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true . 

#### 4.6.9. string:matches[](https://w3c-cg.github.io/n3Builtins/#string:matches)

Checks whether the subject string matches the object regular expression. The regular expression follows the perl, python style.`true` if and only if string `$s` matches the regular expression `$o`

**See also**  
[string:notMatches](https://w3c-cg.github.io/n3Builtins/#string:notMatches)

**Schema**  
`$s+ string:matches $o+`

where:

`$s`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam1+%22hello+world%21%22+.%0A%3ALet+%3Aparam2+%22.%2A%28l%29%2Bo+wo.%2A%22.%0A%7B%0A++++%3ALet+%3Aparam1+%3Fparam1+.%0A++++%3ALet+%3Aparam2+%3Fparam2+.%0A++++%3Fparam1+string%3Amatches+%3Fparam2+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Checks whether the string "hello world!" matches the regular expression "._(l)+o wo._".

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param1 "hello world!" .
:Let :param2 ".\*(l)+o wo.\*".
{
    :Let :param1 ?param1 .
    :Let :param2 ?param2 .
    ?param1 string:matches ?param2 .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true . 

#### 4.6.10. string:notEqualIgnoringCase[](https://w3c-cg.github.io/n3Builtins/#string:notEqualIgnoringCase)

Checks whether the subject string is not the same as the object string, ignoring differences between lowercase and uppercase.`true` if and only if `$s` is not the same string as `$o` when ignoring case differences.

**Schema**  
`$s+ string:notEqualIgnoringCase $o+`

where:

`$s`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam1+%22hello+world%21%22+.%0A%3ALet+%3Aparam2+%22hELLo+dunia%21%22+.%0A%7B%0A++++%3ALet+%3Aparam1+%3Fparam1+.%0A++++%3ALet+%3Aparam2+%3Fparam2+.%0A++++%3Fparam1+string%3AnotEqualIgnoringCase+%3Fparam2+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Checks whether the string "hello world!" is not equal to "hELLo dunia!" ignorning the case .

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param1 "hello world!" .
:Let :param2 "hELLo dunia!" .
{
    :Let :param1 ?param1 .
    :Let :param2 ?param2 .
    ?param1 string:notEqualIgnoringCase ?param2 .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true . 

#### 4.6.11. string:notGreaterThan[](https://w3c-cg.github.io/n3Builtins/#string:notGreaterThan)

Checks whether the subject string is not greater than the object string, according to Unicode code order. You can use this as an equivalent of a lessThanOrEqual operator.`true` if and only if `$s` is not greater than `$o` as per the Unicode code order.

**See also**  
[string:greaterThan](https://w3c-cg.github.io/n3Builtins/#string:greaterThan)

**Schema**  
`$s+ string:notGreaterThan $o+`

where:

`$s`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam1+%22Cat%22+.%0A%3ALet+%3Aparam2+%22Penguin%22.%0A%7B%0A++++%3ALet+%3Aparam1+%3Fparam1+.%0A++++%3ALet+%3Aparam2+%3Fparam2+.%0A++++%3Fparam1+string%3AnotGreaterThan+%3Fparam2+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Checks whether the string "Cat" is not greater than the string "Penguin" .

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param1 "Cat" .
:Let :param2 "Penguin".
{
    :Let :param1 ?param1 .
    :Let :param2 ?param2 .
    ?param1 string:notGreaterThan ?param2 .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true . 

#### 4.6.12. string:notLessThan[](https://w3c-cg.github.io/n3Builtins/#string:notLessThan)

Checks whether the subject string is not less than the object string, according to Unicode code order. You can use this as an equivalent of a greaterThanOrEqual operator.`true` if and only if `$s` is not less than `$o` as per the Unicode code order.

**See also**  
[string:lessThan](https://w3c-cg.github.io/n3Builtins/#string:lessThan)

**Schema**  
`$s+ string:notLessThan $o+`

where:

`$s`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam1+%22Penguin%22.%0A%3ALet+%3Aparam2+%22Cat%22+.%0A%7B%0A++++%3ALet+%3Aparam1+%3Fparam1+.%0A++++%3ALet+%3Aparam2+%3Fparam2+.%0A++++%3Fparam1+string%3AnotLessThan+%3Fparam2+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Checks whether the string "Penguin" is not less than the string "Cat" .

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param1 "Penguin".
:Let :param2 "Cat" .
{
    :Let :param1 ?param1 .
    :Let :param2 ?param2 .
    ?param1 string:notLessThan ?param2 .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true . 

#### 4.6.13. string:notMatches[](https://w3c-cg.github.io/n3Builtins/#string:notMatches)

Checks whether the subject string does not match the object regular expression. The regular expression follows the perl, python style.`true` if and only if string `$s` does not match the regular expression `$o`

**See also**  
[string:matches](https://w3c-cg.github.io/n3Builtins/#string:matches)

**Schema**  
`$s+ string:notMatches $o+`

where:

`$s`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam1+%22hello+world%21%22+.%0A%3ALet+%3Aparam2+%22.%2A%28l%29%2Bo+dunia.%2A%22.%0A%7B%0A++++%3ALet+%3Aparam1+%3Fparam1+.%0A++++%3ALet+%3Aparam2+%3Fparam2+.%0A++++%3Fparam1+string%3AnotMatches+%3Fparam2+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Checks whether the string "hello world!" no matches the regular expression "._(l)+o dunia._".

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param1 "hello world!" .
:Let :param2 ".\*(l)+o dunia.\*".
{
    :Let :param1 ?param1 .
    :Let :param2 ?param2 .
    ?param1 string:notMatches ?param2 .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true . 

#### 4.6.14. string:replace[](https://w3c-cg.github.io/n3Builtins/#string:replace)

Calculates the object as the result of, given the strings in the subject list, replacing all occurrences of the second string in the first string with the third string.`true` if and only if `$o` is the result of replacing all occurrences of `$s.2` in `$s.1` with `$s.3`

**Schema**  
`( $s.1+ $s.2+ $s.3+ )+ string:replace $o-`

where:

`$s.1`: `xsd:string`, `$s.2`: `xsd:string`, `$s.3`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Adata+%22hello+world%21%22+.%0A%3ALet+%3Asearch+%22%28l%29%22+.%0A%3ALet+%3Areplace+%22%5B%241%5D%22+.%0A%7B%0A++++%3ALet+%3Adata+%3Fdata+.%0A++++%3ALet+%3Asearch+%3Fsearch+.%0A++++%3ALet+%3Areplace+%3Freplace+.%0A++++%28%3Fdata+%3Fsearch+%3Freplace%29+string%3Areplace+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Replace all "l"-s in the string "hello world!" with the bracket version "\[l\]" .

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :data "hello world!" .
:Let :search "(l)" .
:Let :replace "\[$1\]" .
{
    :Let :data ?data .
    :Let :search ?search .
    :Let :replace ?replace .
    (?data ?search ?replace) string:replace ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is "he\[l\]\[l\]o wor\[l\]d!". 

#### 4.6.15. string:scrape[](https://w3c-cg.github.io/n3Builtins/#string:scrape)

Calculates the object as the first matching group when, given the subject list, matching the second string as regular expression (with exactly 1 group) against the first string.`true` if and only if `$o` is the first matching group when matching `$s.2` as a regular expression against `$s.1`

**Schema**  
`( $s.1+ $s.2+ )+ string:scrape $o-`

where:

`$s.1`: `xsd:string`, `$s.2`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam1+%22https%3A%2F%2Fw3c.github.io%2FN3%2Fspec%2F%22+.+%0A%3ALet+%3Aparam2+%22.%2A%2F%28%5B%5E%2F%5D%2B%2F%29%24%22+.%0A%7B%0A++++%3ALet+%3Aparam1+%3Fparam1+.%0A++++%3ALet+%3Aparam2+%3Fparam2+.%0A++++%28%3Fparam1+%3Fparam2%29+string%3Ascrape+%3Fresult+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+%3Fresult+.%0A%7D+.)

Extract from the string "https://w3c.github.io/N3/spec/" the last path element using a regular expression .

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param1 "https://w3c.github.io/N3/spec/" . 
:Let :param2 ".\*/(\[^/\]+/)$" .
{
    :Let :param1 ?param1 .
    :Let :param2 ?param2 .
    (?param1 ?param2) string:scrape ?result .
}
=\>
{
    :result :is ?result .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is "spec/". 

#### 4.6.16. string:startsWith[](https://w3c-cg.github.io/n3Builtins/#string:startsWith)

Checks whether the subject string starts with the object string.`true` if and only if `$s` starts with `$o`.

**Schema**  
`$s+ string:startsWith $o+`

where:

`$s`: `xsd:string`  
`$o`: `xsd:string`

  
**Examples**  

[try in editor 🚀](https://n3-editor.herokuapp.com/n3/editor/?formula=%40prefix+%3A+%3Chttp%3A%2F%2Fexample.org%2F%3E.%0A%40prefix+string%3A+%3Chttp%3A%2F%2Fwww.w3.org%2F2000%2F10%2Fswap%2Fstring%23%3E+.%0A%0A%3ALet+%3Aparam1+%22hello+world%21%22+.%0A%3ALet+%3Aparam2+%22hello%22.%0A%7B%0A++++%3ALet+%3Aparam1+%3Fparam1+.%0A++++%3ALet+%3Aparam2+%3Fparam2+.%0A++++%3Fparam1+string%3AstartsWith+%3Fparam2+.%0A%7D%0A%3D%3E%0A%7B%0A++++%3Aresult+%3Ais+true+.%0A%7D+.)

Checks whether the string "hello world!" starts with "hello" .

**Formula:**

@prefix : <http://example.org/\>.
@prefix string: <http://www.w3.org/2000/10/swap/string#\> .

:Let :param1 "hello world!" .
:Let :param2 "hello".
{
    :Let :param1 ?param1 .
    :Let :param2 ?param2 .
    ?param1 string:startsWith ?param2 .
}
=\>
{
    :result :is true .
} .

**Result:**

@prefix : <http://example.org/\>.
:result :is true . 

5\. Acknowledgements[](https://w3c-cg.github.io/n3Builtins/#acknowledgements)
-----------------------------------------------------------------------------

In addition to the editors, the following people have contributed to this specification: Dörthe Arndt, Pierre-Antoine Champin, and Jos De Roo.