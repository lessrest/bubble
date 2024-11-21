import N3, { DataFactory, Store } from "n3";
import { HTTP, RDF } from "./namespace.ts";

export async function requestToStore(
  request: Request,
  requestIri: string,
): Promise<Store> {
  const store = new N3.Store();
  const url = new URL(request.url);

  const requestNode = DataFactory.namedNode(requestIri);

  // Add basic request triples
  store.addQuad(requestNode, RDF("type"), HTTP("Request"));
  store.addQuad(requestNode, HTTP("path"), N3.DataFactory.literal(url.pathname));
  store.addQuad(requestNode, HTTP("href"), N3.DataFactory.namedNode(url.href));
  store.addQuad(requestNode, HTTP("method"), N3.DataFactory.literal(request.method));
  store.addQuad(
    requestNode,
    HTTP("contentType"),
    N3.DataFactory.literal(request.headers.get("Content-Type") ?? "")
  );

  // Check if content type is Turtle
  if (request.headers.get("Content-Type")?.includes("turtle")) {
    const source = await request.text();
    const parser = new N3.Parser({ baseIRI: requestNode.value });
    const quads = parser.parse(source);
    store.addQuads(quads);

    store.addQuad(
      requestNode,
      DataFactory.namedNode("http://www.w3.org/2011/http#body"),
      DataFactory.namedNode(requestNode.value + "#body"),
    );
  }

  return store;
}
