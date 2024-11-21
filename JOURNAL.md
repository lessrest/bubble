# Project Journal

## November 21, 2024

Simplified HTTP request RDF representation:
- Changed from complex RDF list path representation to simple string literal
- Using http:requestURI predicate to store full URL pathname
- Updated tests to verify new representation format
- All tests passing with cleaner implementation

## November 21, 2024

Started development of HTTP request to RDF graph conversion:
- Creating test-driven approach for converting Deno HTTP requests to RDF
- Focusing on representing URL path segments as RDF lists
- Adding tests for request-to-triple conversion
- Planning REST request routing based on N3 rules

Earlier today:
Refactored test names and descriptions for clarity:
- Simplified test step names by removing "should" prefix
- Made test descriptions more concise and direct
- Maintained test behavior and assertions
- All tests passing after updates

Earlier today:
Updated the test suite to use three-letter animals (Rat, Eel, Owl) as the species for the characters:
- Changed Eve's type from Mouse to Rat
- Changed Bob's type from Dog to Eel  
- Changed Jim's type from Seal to Owl
- Updated all test assertions to match new species
- Maintained existing class hierarchy with all species being subclasses of Pet/Pal
- Fixed failing test that still expected Jim to be a Seal
- All tests passing after updates

## November 20, 2024

Initial setup of an RDF reasoning test suite using:
- Deno as the runtime and test framework
- N3.js for RDF parsing and manipulation
- EYE reasoner (via eyereasoner npm package) for inference
- JSR and npm packages managed through deno.json

The test suite demonstrates:
1. Basic RDF triple parsing and assertions
2. Type inference using RDFS subclass rules
3. Transitive relationship inference
4. Helper functions for RDF operations in test/utils.ts

The example domain models characters from Tom & Jerry cartoons, showing:
- Class hierarchy (Character -> Pet -> Cat/Mouse/Dog)
- Instance relationships (e.g., "knows" relationships between characters)
- Inference of derived facts through reasoning rules

All tests are passing, with clean output after removing debug logging.

Added a Deno web server that:
- Serves the Tom & Jerry dataset as Turtle-formatted RDF
- Uses N3.Writer for RDF serialization
- Runs on http://localhost:8000 with endpoints:
  - / - Welcome message
  - /data - The RDF dataset in Turtle format
# Development Journal

## 2024-11-21: ActivityPub Inbox Handler Development

Starting work on ActivityPub support:
- Planning inbox POST request handling using N3 rules
- Will implement basic Activity handling for a simple actor
- Using semantic rules to process incoming Activities
- Goal is to demonstrate ActivityPub server capabilities using N3 reasoning

## 2024-11-21: N3 Rules-Based Request Handler

Successfully implemented and tested a rules-based HTTP request handler that uses N3 reasoning to determine responses. The handler can:

- Match request paths using N3 rules
- Use string operations in rules to do pattern matching
- Return appropriate status codes and response bodies
- Fall back to 404 for unmatched paths

This is a significant milestone as it demonstrates using semantic web technologies (N3 rules and reasoning) to handle web requests in a declarative way. The implementation allows routing logic to be expressed as semantic rules rather than imperative code.

Example rule:
```n3
{
  ?request http:path "/hello".
} => {
  [] http:responseCode 200;
     http:body "Hello, World!".
}.
```

All tests are passing, showing the system works reliably for basic routing patterns.
