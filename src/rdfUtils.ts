import N3, { DataFactory, Store } from "n3";
import { Term } from "@rdfjs/types";
import { HTTP, RDF } from "./namespace.ts";

export function findSubject(store: Store, type: string): Term | null {
  const matches = store.getQuads(
    null,
    RDF("type"),
    DataFactory.namedNode(type),
    null
  );
  return matches.length > 0 ? matches[0].subject : null;
}

export function findObject(store: Store, subject: Term, predicate: string): Term | null {
  const matches = store.getQuads(
    subject,
    DataFactory.namedNode(predicate),
    null,
    null
  );
  return matches.length > 0 ? matches[0].object : null;
}

export function findSubjects(store: Store, predicate: string, object: Term): Term[] {
  return store.getQuads(null, DataFactory.namedNode(predicate), object, null)
    .map(quad => quad.subject);
}

export function getResponseData(store: Store, requestNode: Term): {
  response: Term | null;
  statusCode: number | null;
  body: string | null;
  contentType: string;
} {
  const response = findSubjects(store, HTTP("respondsTo").value, requestNode)[0] || null;
  
  if (!response) {
    return { response: null, statusCode: null, body: null, contentType: "text/plain" };
  }

  const statusObj = findObject(store, response, HTTP("responseCode").value);
  const statusCode = statusObj ? parseInt(statusObj.value) : null;
  
  const bodyObj = findObject(store, response, HTTP("body").value);
  const body = bodyObj ? bodyObj.value : null;
  
  const contentTypeObj = findObject(store, response, HTTP("contentType").value);
  const contentType = contentTypeObj ? contentTypeObj.value : "text/plain";

  return { response, statusCode, body, contentType };
}
