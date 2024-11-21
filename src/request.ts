import N3 from "n3";
import { HTTP, RDF } from "./namespace.ts";
import { DataFactory } from "n3";
const { literal, blankNode } = DataFactory;

export function requestToStore(request: Request): N3.Store {
  const store = new N3.Store();
  const url = new URL(request.url);

  const requestNode = blankNode();
  store.addQuad(
    requestNode,
    RDF("type"),
    HTTP("Request"),
  );

  store.addQuad(
    requestNode,
    HTTP("path"),
    literal(url.pathname),
  );

  return store;
}
