# Bubble - N3 Processing Framework

A semantic web framework that uses N3 rules to process data and generate content. Built with Python, RDFLib, and the EYE reasoner.

## Features

- 🔍 **N3 Processing** - Process N3 files with logical inference
- 🐚 **Shell Integration** - Execute shell commands through N3 rules
- 🎨 **Art Generation** - Generate images using AI models
- 🧪 **Test Driven** - Comprehensive pytest test suite

## Quick Start

This repository includes a GitHub Dev Container configuration that automatically
sets up:

- Python
- SWI-Prolog
- EYE Reasoner

Just open in GitHub Codespaces or VS Code with Dev Containers to get started
immediately!

```bash
# Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Run the tests
pytest

# Process an N3 file
python -m bubble < input.n3
```

## Running with Docker

```bash
make docker-build
make docker-run
```

## Feature Progress

### Implemented ✅

- HTTP Request to RDF conversion
- N3 rule-based request handling
- Declarative routing with N3 patterns
- Basic ActivityPub inbox (GET/POST)
- RDFS reasoning and type inference
- Comprehensive test suite with RDF assertions

### Coming Soon 🚧

- Server Identity & Profile
- HTML/HTMX Interface
- Activity validation
- Outbox implementation
- Federation support

When you start the server, it exposes a simple ActivityPub inbox implementation
at `http://localhost:8000/users/alice/inbox`. The configuration is split into
two files:

1. `ground-facts.ttl` - Defines the basic ActivityPub structure:

```n3
@base <http://localhost:8000/>.
@prefix ap: <http://www.w3.org/ns/activitystreams#>.

</users/alice> a ap:Person;
  ap:inbox </users/alice/inbox>.

</users/alice/inbox> a ap:Collection.
```

2. `rules/inbox.n3` - Contains the N3 rules for handling requests

The `@base` directive in the ground facts sets the base IRI to resolve relative
paths, so `/users/alice/inbox` becomes
`http://localhost:8000/users/alice/inbox`. The inbox implementation can:

- Accept POST requests with new ActivityPub Notes
- Return the collection contents via GET requests
- Maintain the collection items between requests

You can test it with curl:

```bash
# Get the inbox contents
curl http://localhost:8000/users/alice/inbox

# Post a new Note
curl -X POST -H "Content-Type: application/turtle" \
  -d '@prefix as: <http://www.w3.org/ns/activitystreams#>.
      <#body> a as:Note; as:content "Hello Alice!".' \
  http://localhost:8000/users/alice/inbox
```

## Example: ActivityPub Inbox with N3 Rules

This example shows how to implement an ActivityPub inbox using N3 rules. N3
rules are logical implications of the form: `{ condition } => { conclusion }`
where both sides are RDF graph patterns.

The framework:

1. Converts HTTP requests into RDF graphs
2. Applies N3 rules to match patterns and generate responses
3. Converts response graphs back to HTTP responses

When the response includes RDF graphs in the `http:body` predicate, they are
automatically serialized as Turtle in the HTTP response body.

```n3
# First, declare our namespaces
@prefix http: <http://www.w3.org/2011/http#>.
@prefix as: <http://www.w3.org/ns/activitystreams#>.

# Rule 1: GET request to an inbox
# When we match:
{
  # An HTTP request...
  ?request http:href ?collection;  # ...to some URL
          http:method "GET" .      # ...using GET method

  # And that URL identifies a Collection
  ?collection a as:Collection.
} => {
  # Then generate a response...
  ?response a http:Response;
    http:respondsTo ?request;     # ...for this request
    http:responseCode 200;        # ...with 200 OK status
    http:contentType "application/turtle";  # ...as Turtle
    # Include a graph in the response body
    http:body {
      ?collection a as:Collection
    } .
}.

# Rule 2: Include collection items in GET response
# This rule adds to the previous response
{
  ?request http:href ?collection;
    http:method "GET" .

  # Find the existing response
  ?response a http:Response ;
    http:respondsTo ?request .

  # Match any items in the collection
  ?collection ap:items ?item .
} => {
  # Add those items to the response body
  ?response http:body {
    ?collection ap:items ?item
  } .
}.

# Rule 3: POST new items to the inbox
{
  # Match POST request
  ?request http:href ?collection;
          http:method "POST";
          http:body ?object .     # Extract posted content

  # Verify collection exists
  ?collection a as:Collection .
  # Verify posted content is a Note
  ?object a as:Note .
} => {
  # Create success response
  ?response a http:Response;
    http:respondsTo ?request;
    http:responseCode 201;
    http:body "Activity accepted" .

  # Add the Note to the collection
  ?collection as:items ?object .
}.
```

The framework handles all the RDF conversion:

- Incoming requests become RDF graphs with `http:Request` type
- Posted content in Turtle format is parsed into the request graph
- Response graphs are converted back to HTTP responses
- RDF graphs in `http:body` are serialized as Turtle

This declarative approach lets us focus on the logic of what should happen
rather than how to implement it. The rules engine handles matching patterns and
generating the appropriate responses.

## Example: HTML Pages in RDF

The framework includes a way to represent HTML pages in RDF/Turtle format. This
allows us to generate HTML responses using N3 rules and semantic data:

```turtle
# Define an HTML page
[] a html:page;
   html:title "Welcome";
   html:body [
     a html:p;
     html:content "Hello World!"
   ].
```

The framework automatically converts this RDF representation into proper HTML:

```html
<!DOCTYPE html>
<html>
  <head>
    <title>Welcome</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
  </head>
  <body>
    <p>Hello World!</p>
  </body>
</html>
```

This approach allows us to:

- Generate HTML pages from RDF data
- Use semantic rules to determine page content
- Keep HTML generation declarative
- Mix HTML with other RDF responses

HTTP requests are represented as RDF:

```turtle
_:request a http:Request;
    http:path "/api/users/123";
    http:method "GET".
```

## Key Features

- Clean separation between routing logic and handlers
- Pattern matching on URLs through N3 rules
- Content negotiation via semantic rules
- ActivityPub inbox/outbox handling
- Session-based request contexts

## Development

```bash
# Run tests
deno task test

# Start dev server
deno task dev

# Run specific test suites
deno task test:server
deno task test:rules
```

## License

This project is licensed under the [GNU Affero GPL v3.0 or later](LICENSE.md),
so watch out.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
