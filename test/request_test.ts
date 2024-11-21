import { assertQuery } from "./utils.ts";
import { requestToStore } from "./request.ts";

Deno.test("HTTP Request to RDF", async (t) => {
  const request = new Request("http://example.com/api/users/123");
  const store = requestToStore(request);

  await assertQuery(t, store, `
    @prefix http: <http://www.w3.org/2011/http#> .
    
    {
      ?request a http:Request;
        http:requestURI "/api/users/123" .
    }`, 
    "converts URL path to RDF request"
  );
});
