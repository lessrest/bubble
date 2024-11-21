import { handleWithRules, withGroundFacts } from "./src/utils.ts";

// Initial ActivityPub data
const groundFacts = `
  @base <http://localhost:8000/>.
  @prefix ap: <http://www.w3.org/ns/activitystreams#>.
  
  </users/alice> a ap:Person;
    ap:inbox </users/alice/inbox>.

  </users/alice/inbox> a ap:Collection.
`;

// Sample data for Tom & Jerry dataset
const tomAndJerryData = `
@prefix schema: <http://schema.org/>.
@prefix ex: <http://example.org/>.

ex:Tom a schema:Character;
  schema:name "Tom";
  schema:description "A house cat who constantly chases Jerry".

ex:Jerry a schema:Character;
  schema:name "Jerry";
  schema:description "A clever mouse who outwits Tom".
`;

// Rules for handling requests
const rules = `
  @prefix http: <http://www.w3.org/2011/http#>.
  @prefix ap: <http://www.w3.org/ns/activitystreams#>.
  @prefix string: <http://www.w3.org/2000/10/swap/string#>.
  @prefix e: <http://eulersharp.sourceforge.net/2003/03swap/log-rules#>.
  @prefix log: <http://www.w3.org/2000/10/swap/log#>.
  
  # Handle root path
  {
    ?request http:path "/" .
  } => {
    ?response a http:Response;
      http:respondsTo ?request;
      http:responseCode 200;
      http:body "RDF Test Server - Try /data for the Tom & Jerry dataset" .
  }.

  # Handle /data path
  {
    ?request http:path "/data" .
  } => {
    ?response a http:Response;
      http:respondsTo ?request;
      http:responseCode 200;
      http:contentType "text/turtle";
      http:body """${tomAndJerryData}""" .
  }.
  
  # Handle inbox GET
  {
    ?request http:href ?collection;
            http:method "GET" .
    
    ?collection a ap:Collection.
  } => {
    ?response a http:Response;
      http:respondsTo ?request;
      http:responseCode 200;
      http:contentType "application/turtle";
      http:body ?n3 .

    # Get all items in the collection
    ?collection ap:items ?items .
    
    # Convert to N3 string
    (?collection) e:n3String ?n3 .
  }.

  # Handle inbox POST
  {
    ?request http:href ?collection;
            http:method "POST" ;
            http:body ?object .
    
    ?collection a ap:Collection .    
    ?object a ap:Note .
  } => {
    ?response a http:Response;
      http:respondsTo ?request;
      http:responseCode 201;
      http:body "Activity accepted" .

    ?collection ap:items ?object .
  }.
`;

const store = await withGroundFacts(groundFacts);

export async function handler(req: Request): Promise<Response> {
  return handleWithRules(req, rules, store, store);
}

if (import.meta.main) {
  await Deno.serve({ port: 8000 }, handler);
}
