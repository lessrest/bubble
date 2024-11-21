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
1. **Advanced HTML Generation**: Complete HTML document generation using RDF lists and semantic graphs:
```turtle
# Clean representation of nested HTML structure
?html html:children ( 
    [ html:tagName "head"
      html:children ( 
        [ html:tagName "title"
          html:children ( [ html:content "Test Site" ] )
        ]
        [ html:tagName "meta"
          html:attributes [
            html:name "viewport"
            html:value "width=device-width, initial-scale=1"
          ]
        ]
      )
    ]
) .
```

2. **HTML from RDF**: Basic HTML document generation:
```turtle
[] a html:element ;
   html:tagName "html" ;
   html:children ( 
     [ a html:element ;
       html:tagName "head" ;
       html:children ( 
         [ a html:element ;
           html:tagName "title" ;
           html:children ( [ a html:text ; html:content "Hello" ] )
         ]
       )
     ]
   ) .
```

2. **Declarative Routing**: HTTP routes are now defined purely in N3 rules:
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

### Latest Achievement: Advanced HTML Generation with RDF Lists

Successfully enhanced the HTML generation system with full RDF list support and proper attribute handling. Key improvements:

1. **Complete RDF List Support**: HTML elements are now properly represented using RDF lists for children:
```turtle
_:n3-0 rdf:first ?head ;
    rdf:rest _:n3-1 .
_:n3-1 rdf:first ?body ;
    rdf:rest rdf:nil .
```

2. **Attribute Handling**: Clean representation of HTML attributes:
```turtle
?meta html:attributes [
    html:name "viewport" ;
    html:value "width=device-width, initial-scale=1"
] .
```

3. **Proper Nesting**: Elements can be deeply nested while maintaining clean RDF structure:
```turtle
?html html:children ( 
    [ html:tagName "head"
      html:children ( 
        [ html:tagName "title"
          html:children ( [ html:content "Test Site" ] )
        ]
      )
    ]
) .
```

4. **Self-closing Tags**: Special handling for tags like meta, link, br:
```html
<meta name="viewport" content="width=device-width, initial-scale=1">
```

The system successfully generates complete HTML documents from semantic RDF graphs, as demonstrated by the passing test suite.

### Previous Achievement: HTML Generation from RDF Graph

Successfully implemented a complete HTML generation system using RDF graphs and N3 rules. The system can now:

1. **Represent HTML Structure in RDF**: Each HTML element is represented as a node in the RDF graph with:
   - Element type (element/text)
   - Tag name
   - Children as RDF lists
   - Attributes as nested objects

2. **Smart Tag Handling**: 
   - Proper handling of self-closing tags (meta, link, br, hr, img, input)
   - Correct DOCTYPE for html documents
   - Special handling for meta viewport tags

3. **Clean Integration**: HTML generation integrates seamlessly with HTTP response handling:
```n3
{
  ?response http:body [ html:element ?html ]
}
```

Example RDF representation of an HTML page:
```turtle
[] a html:element ;
   html:tagName "html" ;
   html:children ( 
     [ a html:element ;
       html:tagName "head" ;
       html:children ( 
         [ a html:element ;
           html:tagName "meta" ;
           html:attributes [
             html:name "viewport" ;
             html:value "width=device-width, initial-scale=1"
           ]
         ]
       )
     ]
   ) .
```

This is rendered correctly as:
```html
<!doctype html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head></html>
```

### Previous Achievement: HTML Rendering with String Concatenation

Successfully implemented basic HTML page generation using N3 rules and string concatenation. Key points:

1. **String Format Built-ins**: Using string:format for template substitution:
```n3
( """<!doctype html><title>%s</title>...""" ?title ) string:format ?html
```

2. **Clean Integration**: HTML generation integrates smoothly with HTTP response handling:
```n3
{
  ?response http:body [ html:outerHTML ?html ]
}
```

3. **Metadata Support**: Successfully passing site metadata into templates:
- Site name
- Description
- Other schema.org properties

Next Steps:
- Implement recursive HTML rendering for nested elements
- Add support for collections/lists of elements
- Create reusable HTML component rules
- Build more sophisticated page layouts

### Previous Achievement: Modular ActivityPub Implementation
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
