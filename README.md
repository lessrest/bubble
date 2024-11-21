# N3 Web Framework

A semantic web framework that uses N3 rules to handle HTTP requests and implement ActivityPub nodes. Built with Deno, N3.js, and the EYE reasoner.

## Features

- 🌐 **Declarative HTTP Routing** - Define routes using N3 rules
- 🔍 **Semantic Processing** - Handle requests through RDF and logical inference  
- 🤝 **ActivityPub Support** - Build federated social applications
- 🧪 **Test Driven** - Comprehensive test suite using Deno's testing framework

## Quick Start

```bash
# Install dependencies
deno task cache

# Run the tests
deno task test

# Start the server
deno task serve
```

## Example: ActivityPub Inbox

Define an ActivityPub-compatible inbox using N3 rules:

```n3
@prefix http: <http://www.w3.org/2011/http#>.
@prefix as: <http://www.w3.org/ns/activitystreams#>.

# GET inbox - return collection and its items
{
  ?request http:href ?collection;
          http:method "GET" .
  
  ?collection a as:Collection.
} => {
  ?response a http:Response;
    http:respondsTo ?request;
    http:responseCode 200;
    http:contentType "application/turtle";
    http:body { ?collection a as:Collection } .
}.

# Return any items in the collection
{
  ?request http:href ?collection;
    http:method "GET" .
  
  ?response a http:Response ;
    http:respondsTo ?request .

  ?collection ap:items ?item .
} => {
  ?response http:body { ?collection ap:items ?item } .
}.

# POST note to inbox
{
  ?request http:href ?collection;
          http:method "POST";
          http:body ?object .
  
  ?collection a as:Collection .    
  ?object a as:Note .
} => {
  ?response a http:Response;
    http:respondsTo ?request;
    http:responseCode 201;
    http:body "Activity accepted" .

  ?collection as:items ?object .
}.
```

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

This project is licensed under the [GNU Aferro GPL v3.0 or later](LICENSE.md).

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
