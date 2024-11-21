# Project Journal

## November 21, 2024

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
