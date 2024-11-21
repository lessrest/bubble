import N3, { DataFactory, Store } from "n3";
import { Quad, Term } from "@rdfjs/types";
import { CommandLineReasoner } from "./reasoning.ts";
import { withGroundFacts, writeN3 } from "./utils.ts";
import { requestToStore } from "./requestToStore.ts";
import { findObject, getResponseData } from "./rdfUtils.ts";
import { getContentType, processResponseBody } from "./responseUtils.ts";
import { RDF } from "./namespace.ts";

export async function handleWithRules(
  request: Request,
  rules: string[],
  factStore: Store,
): Promise<Response> {
  // Initialize stores and process request
  const uuid = crypto.randomUUID();
  const requestIri = `urn:request:${uuid.slice(0, 8)}`;
  const requestStore = await requestToStore(request, requestIri);
  requestStore.addQuads(factStore.getQuads());

  console.log("*** Request Quads ***");
  console.log(await writeN3(requestStore.getQuads()));

  console.log("*** Ground Facts ***");
  console.log(await writeN3(factStore.getQuads()));

  console.log("*** Rules ***");
  console.log(rules);

  // Apply reasoning rules
  const reasoner = new CommandLineReasoner();
  const n3Input = await writeN3(requestStore.getQuads());
  const result = await reasoner.reason([...rules, n3Input]);

  // Process results
  const parser = new N3.Parser({ format: "text/n3", blankNodePrefix: "" });
  const resultQuads = parser.parse(result) as Quad[];
  console.log("*** Reasoner Result ***");
  console.log(await writeN3(resultQuads));

  const resultStore = new N3.Store();
  resultStore.addQuads(resultQuads);
  resultStore.addQuads(factStore.getQuads());

  // Get response data
  const requestNode = DataFactory.namedNode(requestIri);
  console.log(`Getting response data for ${requestIri}`);
  const { response, statusCode, asserts } = getResponseData(
    resultStore,
    requestNode,
  );
  console.log(`Response data`, response);
  console.log(`Asserts`, asserts);

  if (!response) {
    return new Response("Not Found", { status: 404 });
  }

  if (!statusCode) {
    return new Response("Response missing status code", { status: 500 });
  }

  // Process response body and content type
  const { content, contentType } = await processResponseBody(
    resultStore,
    response,
  );
  const explicitContentType = getContentType(resultStore, response);

  if (asserts) {
    // for now asserts is just one statement
    const assertedQuad = getQuadFromStatement(resultStore, asserts);
    console.log("*** Asserted Quad ***");
    console.log(assertedQuad);
    factStore.addQuads([assertedQuad]);
  }

  return new Response(content || null, {
    status: statusCode,
    headers: {
      "Content-Type": explicitContentType || contentType,
    },
  });
}

function getQuadFromStatement(store: Store, statement: Term): Quad {
  const subject = findObject(store, statement, RDF("subject").value);
  const predicate = findObject(store, statement, RDF("predicate").value);
  const object = findObject(store, statement, RDF("object").value);
  if (!subject || !predicate || !object) {
    throw new Error("Statement missing subject, predicate, or object");
  }
  return DataFactory.quad(subject, predicate, object, null);
}
