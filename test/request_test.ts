import { assertN3Query } from "./utils.ts";
import { requestToStore } from "./request.ts";

Deno.test("HTTP Request to RDF", async (t) => {
  await t.step("converts URL path to RDF request", async () => {
    const request = new Request("http://example.com/api/users/123");
    const store = requestToStore(request);
    
    const query = `
      @prefix test: <http://example.org/test#> .
      @prefix http: <http://www.w3.org/2011/http#> .
      
      {
        ?request a http:Request;
          http:requestURI "/api/users/123" .
      } => {
        [] a test:Success;
          test:message "Found expected HTTP request" .
      }.
    `;
    
    await assertN3Query(store, query);
  });
});
