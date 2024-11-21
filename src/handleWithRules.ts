import N3, { DataFactory, Store } from "n3";
import { Quad } from "@rdfjs/types";
import { CommandLineReasoner } from "./reasoning.ts";
import { writeN3 } from "./utils.ts";
import { requestToStore } from "./requestToStore.ts";
import { getResponseData } from "./rdfUtils.ts";
import { getContentType, processResponseBody } from "./responseUtils.ts";

export async function handleWithRules(
  request: Request,
  rules: string[],
  groundFacts?: Store,
  resultStore?: Store,
): Promise<Response> {
  // Initialize stores and process request
  const uuid = crypto.randomUUID();
  const requestIri = `urn:request:${uuid}`;
  const store = await requestToStore(request, requestIri);

  if (groundFacts) {
    store.addQuads(groundFacts.getQuads());
  }

  // Apply reasoning rules
  const reasoner = new CommandLineReasoner();
  const n3Input = await writeN3(store.getQuads());
  const result = await reasoner.reason([n3Input, ...rules]);

  // Process results
  if (!resultStore) {
    resultStore = new N3.Store();
  }

  const parser = new N3.Parser({ format: "text/n3" });
  const resultQuads = parser.parse(result) as Quad[];
  resultStore.addQuads(resultQuads);

  // Get response data
  const requestNode = DataFactory.namedNode(requestIri);
  const { response, statusCode } = getResponseData(resultStore, requestNode);

  if (!response) {
    return new Response("Not Found", { status: 404 });
  }

  if (!statusCode) {
    return new Response("Response missing status code", { status: 500 });
  }

  // Process response body and content type
  const { content, contentType } = await processResponseBody(resultStore, response);
  const explicitContentType = getContentType(resultStore, response);

  return new Response(content || null, {
    status: statusCode,
    headers: { 
      "Content-Type": explicitContentType || contentType
    },
  });
}
