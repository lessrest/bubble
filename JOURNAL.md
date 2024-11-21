# Project Journal

## November 21, 2024 - Major Progress on RDF Web Framework

We've made significant strides in building a semantic web framework that uses N3 rules for HTTP request handling. Here's what we've accomplished:

### Core RDF Infrastructure
- Built a robust test suite using Deno, N3.js, and the EYE reasoner
- Implemented clean RDF parsing and serialization
- Created helper functions for RDF assertions and queries
- Demonstrated RDFS reasoning with type inference and transitive relationships

### HTTP Request Handler with N3 Rules
Successfully created a declarative web request handler that:
- Converts HTTP requests into RDF graphs
- Uses N3 rules to determine responses
- Supports pattern matching on paths
- Handles different response types and status codes

The system now uses session-based URNs to provide unique contexts for request processing, ensuring clean separation between different requests.

### ActivityPub Integration (In Progress)
Started work on ActivityPub support:
- Basic inbox POST handling with semantic rules
- Activity processing using RDF representations
- Currently debugging collection updates
- Working toward a fully semantic social network node

### Example Domain Model
Built a playful test domain using Tom & Jerry characters:
- Demonstrates class hierarchies (Pet -> Rat/Eel/Owl)
- Shows relationship inference
- Provides concrete examples for testing

### Technical Achievements
1. **Declarative Routing**: HTTP routes are now defined purely in N3 rules:
```n3
{
  ?request http:path "/hello".
} => {
  [] http:responseCode 200;
     http:body "Hello, World!".
}.
```

2. **Clean RDF Representations**: HTTP requests are cleanly modeled in RDF:
```turtle
_:request a http:Request;
    http:path "/api/users/123";
    http:method "GET".
```

3. **Semantic Processing**: Using N3 rules for request handling enables:
- Pattern matching on URLs
- Content negotiation
- Response generation
- All through declarative rules

### Next Steps
- Complete ActivityPub inbox implementation
- Add more sophisticated content negotiation
- Implement outbox and activity distribution
- Build more complex routing patterns
- Implement proper HTML user interface (removed temporary HTML fragment code)

### Latest Achievement: Modular ActivityPub Implementation
We've successfully refactored the ActivityPub implementation to be more modular by:
- Extracting ground facts into `ground-facts.ttl`
- Moving inbox rules to `rules/inbox.n3`
- Updating server.ts to load these files dynamically

The ground facts file (`ground-facts.ttl`) defines the basic ActivityPub structure:
```n3
@base <http://localhost:8000/>.
@prefix ap: <http://www.w3.org/ns/activitystreams#>.

</users/alice> a ap:Person;
  ap:inbox </users/alice/inbox>.

</users/alice/inbox> a ap:Collection.
```

The inbox rules (`rules/inbox.n3`) handle both GET and POST operations:
```n3
# GET returns the Collection and its items
{
  ?request http:href ?collection;
          http:method "GET" .
  ?collection a ap:Collection.
} => {
  # Return collection data
}.

# POST adds new items to the collection
{
  ?request http:href ?collection;
          http:method "POST" .
  ?collection a ap:Collection.
} => {
  # Store the new item
}.
```

This separation of concerns makes the codebase more maintainable and easier to extend. The server now:
1. Loads ground facts at startup
2. Reads rules from separate files
3. Applies them to incoming requests

Next steps:
- Add more specialized rules for different activity types
- Implement outbox functionality in separate rule files
- Add validation rules for incoming activities
- Create rules for federation and delivery
