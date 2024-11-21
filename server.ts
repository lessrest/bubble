import { handleWithRules, withGroundFacts } from "./src/utils.ts";

// Initial ActivityPub data
const groundFacts = `
  @base <http://localhost:8000/>.
  @prefix ap: <http://www.w3.org/ns/activitystreams#>.
  
  </users/alice> a ap:Person;
    ap:inbox </users/alice/inbox>.

  </users/alice/inbox> a ap:Collection.
`;

// Rules for handling requests
const rules = `
  @prefix http: <http://www.w3.org/2011/http#>.
  @prefix ap: <http://www.w3.org/ns/activitystreams#>.
  @prefix string: <http://www.w3.org/2000/10/swap/string#>.
  
  # Handle root path
  {
    ?request http:path "/" .
  } => {
    ?response a http:Response;
      http:respondsTo ?request;
      http:responseCode 200;
      http:body "ActivityPub Test Server - Try POST to /users/alice/inbox" .
  }.

  # Handle inbox GET
  {
    ?request http:path ?path;
            http:method "GET" .
    
    ?collection a ap:Collection;
              http:path ?path .
  } => {
    ?response a http:Response;
      http:respondsTo ?request;
      http:responseCode 200;
      http:contentType "text/turtle";
      http:body ?n3 .

    # Get all items in the collection
    ?collection ap:items ?items .
    
    # Convert to N3 string
    (?collection ?items) log:n3String ?n3 .
  }.

  # Handle inbox POST
  {
    ?request http:path ?path;
            http:method "POST" .
    
    ?collection a ap:Collection;
              http:path ?path .
    
    ?object a ap:Note .
  } => {
    ?response a http:Response;
      http:respondsTo ?request;
      http:responseCode 201;
      http:body "Activity accepted" .

    ?collection ap:items ?object .
  }.
`;

export async function handler(req: Request): Promise<Response> {
  return handleWithRules(req, rules, withGroundFacts(groundFacts));
}

if (import.meta.main) {
  await Deno.serve({ port: 8000 }, handler);
}
