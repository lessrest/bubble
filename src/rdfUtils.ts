import N3, { DataFactory, Store } from "n3";
import { Quad, Term } from "@rdfjs/types";
import { HTTP, RDF } from "./namespace.ts";

export function findSubject(store: Store, type: string): Term | null {
  const matches = store.getQuads(
    null,
    RDF("type"),
    DataFactory.namedNode(type),
    null,
  );
  return matches.length > 0 ? matches[0].subject : null;
}

export function findObject(
  store: Store,
  subject: Term,
  predicate: string,
): Term | null {
  const matches = store.getQuads(
    subject,
    DataFactory.namedNode(predicate),
    null,
    null,
  );
  return matches.length > 0 ? matches[0].object : null;
}

export function findSubjects(
  store: Store,
  predicate: string,
  object: Term,
): Term[] {
  return store.getQuads(null, DataFactory.namedNode(predicate), object, null)
    .map((quad: Quad) => quad.subject);
}

export function getResponseData(store: Store, requestNode: Term): {
  response: Term | null;
  statusCode: number | null;
  body: string | null;
  contentType: string;
} {
  console.log(`... Getting response data for ${requestNode.value}`);
  const responses = findSubjects(store, HTTP("respondsTo").value, requestNode);
  console.log(`... Found ${responses.length} responses`);
  console.log(responses);

  if (responses.length === 0) {
    return {
      response: null,
      statusCode: null,
      body: null,
      contentType: "text/plain",
    };
  }

  const statusObj = findObject(store, responses[0], HTTP("responseCode").value);
  const statusCode = statusObj ? parseInt(statusObj.value) : null;

  const bodyObj = findObject(store, responses[0], HTTP("body").value);
  const body = bodyObj ? bodyObj.value : null;

  const contentTypeObj = findObject(
    store,
    responses[0],
    HTTP("contentType").value,
  );
  const contentType = contentTypeObj ? contentTypeObj.value : "text/plain";

  return { response: responses[0], statusCode, body, contentType };
}
