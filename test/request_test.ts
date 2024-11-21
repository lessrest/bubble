import { assertTurtleGraph } from "./utils.ts";
import { requestToStore } from "./request.ts";

Deno.test("HTTP Request to RDF", async (t) => {
  await t.step("converts URL path to RDF request", async () => {
    const request = new Request("http://example.com/api/users/123");
    const store = requestToStore(request);
    
    assertTurtleGraph(store, `
      @prefix http: <http://www.w3.org/2011/http#> .
      
      [] a http:Request ;
         http:requestURI "/api/users/123" .
    `);
  });
});
