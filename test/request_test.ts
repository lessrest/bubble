import { assertEquals } from "@std/assert";
import { assertTurtleGraph } from "./utils.ts";
import { Schema } from "./namespace.ts";
import N3 from "n3";

import { HTTP, RDF } from "./namespace.ts";
import { DataFactory } from "n3";
const { literal, blankNode } = DataFactory;

async function requestToStore(request: Request): Promise<N3.Store> {
  const store = new N3.Store();
  const url = new URL(request.url);
  const pathSegments = url.pathname.split('/').filter(Boolean);
  
  const requestNode = blankNode();
  store.addQuad(
    requestNode,
    RDF('type'),
    HTTP('Request')
  );

  // Create the path list
  let listHead = blankNode();
  const firstNode = listHead;
  
  pathSegments.forEach((segment, index) => {
    store.addQuad(
      listHead,
      RDF('first'),
      literal(segment)
    );
    
    if (index < pathSegments.length - 1) {
      const nextNode = blankNode();
      store.addQuad(
        listHead,
        RDF('rest'),
        nextNode
      );
      listHead = nextNode;
    } else {
      store.addQuad(
        listHead,
        RDF('rest'),
        RDF('nil')
      );
    }
  });

  store.addQuad(
    requestNode,
    HTTP('path'),
    firstNode
  );

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
