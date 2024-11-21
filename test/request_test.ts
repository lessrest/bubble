import { assertEquals } from "@std/assert";
import { assertTurtleGraph } from "./utils.ts";
import { Schema } from "./namespace.ts";
import N3 from "n3";

async function requestToStore(request: Request): Promise<N3.Store> {
  const store = new N3.Store();
  // TODO: Implement conversion of request to RDF triples
  return store;
}

Deno.test("HTTP Request to RDF", async (t) => {
  await t.step("converts URL path to RDF list", async () => {
    const request = new Request("http://example.com/api/users/123");
    const store = await requestToStore(request);
    
    assertTurtleGraph(store, `
      @prefix http: <http://www.w3.org/2011/http#> .
      
      [] a http:Request ;
         http:path ("api" "users" "123") .
    `);
  });
});
