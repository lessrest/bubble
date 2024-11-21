import { assertEquals } from "@std/assert";
import { writeN3 } from "./utils.ts";
import { n3reasoner } from "eyereasoner";
import { requestToStore } from "./request.ts";

Deno.test("HTTP Request to RDF", async (t) => {
  await t.step("converts URL path to RDF request", async () => {
    const request = new Request("http://example.com/api/users/123");
    const store = requestToStore(request);
    
    const query = `
      @prefix http: <http://www.w3.org/2011/http#> .
      @prefix log: <http://www.w3.org/2000/10/swap/log#> .
      
      {
        ?request a http:Request;
          http:requestURI "/api/users/123" .
      } => {
        ?request a http:Request;
          http:requestURI "/api/users/123" .
      }.
    `;
    
    const result = await n3reasoner(await writeN3(store.getQuads()), query);
    assertEquals(result.length > 0, true, "Expected to find matching HTTP request");
  });
});
