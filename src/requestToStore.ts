import N3, { DataFactory } from "n3";
import { Store } from "n3";

export async function requestToStore(
  request: Request,
  requestIri: string,
): Promise<Store> {
  const store = new N3.Store();
  const url = new URL(request.url);

  const requestNode = DataFactory.namedNode(requestIri);

  // Add basic request triples
  store.addQuad(
    requestNode,
    DataFactory.namedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
    DataFactory.namedNode("http://www.w3.org/2011/http#Request"),
  );

  // Add path
  store.addQuad(
    requestNode,
    DataFactory.namedNode("http://www.w3.org/2011/http#path"),
    DataFactory.literal(url.pathname),
  );

  // Add href
  store.addQuad(
    requestNode,
    DataFactory.namedNode("http://www.w3.org/2011/http#href"),
    DataFactory.namedNode(url.href),
  );

  // Add method
  store.addQuad(
    requestNode,
    DataFactory.namedNode("http://www.w3.org/2011/http#method"),
    DataFactory.literal(request.method),
  );

  // Add content type
  store.addQuad(
    requestNode,
    DataFactory.namedNode("http://www.w3.org/2011/http#contentType"),
    DataFactory.literal(request.headers.get("Content-Type") ?? ""),
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
