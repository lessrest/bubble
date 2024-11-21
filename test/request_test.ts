import { assertEquals } from "@std/assert";
import { assertTurtleGraph, writeN3 } from "./utils.ts";
import { Schema } from "./namespace.ts";
import N3 from "n3";
import { n3reasoner } from "eyereasoner";

import { HTTP, RDF } from "./namespace.ts";
import { DataFactory } from "n3";
const { literal, blankNode } = DataFactory;

async function requestToStore(request: Request): Promise<N3.Store> {
  const store = new N3.Store();
  const url = new URL(request.url);
  
  const requestNode = blankNode();
  store.addQuad(
    requestNode,
    RDF('type'),
    HTTP('Request')
  );

  store.addQuad(
    requestNode,
    HTTP('requestURI'),
    literal(url.pathname)
  );

  return store;
}

Deno.test("HTTP Request to RDF", async (t) => {
  await t.step("converts URL path to RDF list", async () => {
    const request = new Request("http://example.com/api/users/123");
    const store = await requestToStore(request);
    
    // Query to check if there exists a request with the expected URI
    const query = `
      @prefix http: <http://www.w3.org/2011/http#> .
      @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
      
      {
        ?request a http:Request ;
                http:requestURI "/api/users/123" .
      } => {
        ?request a http:Request .
      } .
    `;
    
    const result = await n3reasoner(store.getQuads(), query);
    assertEquals(result.length > 0, true, 
      "Expected to find a request matching the pattern:\n" + query + 
      "\nActual store contents:\n" + await writeN3(store.getQuads()));
  });
});
