import N3, { DataFactory, Store } from "n3";
import { Term } from "@rdfjs/types";
import { HTTP } from "./namespace.ts";
import { renderHTML } from "./html.ts";
import { writeN3 } from "./utils.ts";

interface ResponseBody {
  content: string;
  contentType: string;
}

export async function processResponseBody(
  store: Store,
  response: Term,
): Promise<ResponseBody> {
  const bodyQuads = store.getQuads(response, HTTP("body"), null, null);
  
  if (bodyQuads.length === 0) {
    return { content: "", contentType: "text/plain" };
  }

  const bodyStore = new N3.Store();
  
  // Try to find literal or HTML content first
  for (const bodyQuad of bodyQuads) {
    if (bodyQuad.object.termType === "Literal") {
      return {
        content: bodyQuad.object.value,
        contentType: "text/plain"
      };
    }

    if (bodyQuad.object.termType === "BlankNode" || 
        bodyQuad.object.termType === "NamedNode") {
      // Check if this is an HTML page
      const isHtmlPage = store.getQuads(
        bodyQuad.object,
        DataFactory.namedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
        DataFactory.namedNode("http://www.w3.org/1999/xhtml#element"),
        null
      ).length > 0;

      if (isHtmlPage) {
        return {
          content: await renderHTML(store, bodyQuad.object),
          contentType: "text/html"
        };
      }

      // Add to N3 store for potential later serialization
      const graphId = bodyQuad.object.termType === "BlankNode"
        ? `_:${bodyQuad.object.value}`
        : bodyQuad.object.value;
      const subgraph = store.getQuads(null, null, null, graphId);
      bodyStore.addQuads(subgraph);
    } else if (bodyQuad.object.termType === "Quad") {
      bodyStore.addQuad(bodyQuad.object);
    }
  }

  // If we got here, serialize the N3 content
  if (bodyStore.size > 0) {
    return {
      content: await writeN3(bodyStore.getQuads()),
      contentType: "text/turtle"
    };
  }

  return { content: "", contentType: "text/plain" };
}

export function getContentType(store: Store, response: Term): string {
  const contentTypeQuads = store.getQuads(
    response,
    HTTP("contentType"),
    null,
    null
  );
  
  return contentTypeQuads.length > 0
    ? contentTypeQuads[0].object.value
    : "text/plain";
}
