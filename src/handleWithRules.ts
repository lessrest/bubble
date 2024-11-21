import N3, { DataFactory, Store } from "n3";
import { Quad } from "@rdfjs/types";
import { CommandLineReasoner } from "./reasoning.ts";
import { withGroundFacts, writeN3 } from "./utils.ts";
import { requestToStore } from "./requestToStore.ts";
import { getResponseData } from "./rdfUtils.ts";
import { getContentType, processResponseBody } from "./responseUtils.ts";

export async function handleWithRules(
  request: Request,
  rules: string[],
  groundFacts: Store,
): Promise<Response> {
  // Initialize stores and process request
  const uuid = crypto.randomUUID();
  const requestIri = `urn:request:${uuid.slice(0, 8)}`;
  const requestStore = await requestToStore(request, requestIri);
  requestStore.addQuads(groundFacts.getQuads());

  console.log("*** Request Quads ***");
  console.log(await writeN3(requestStore.getQuads()));

  console.log("*** Ground Facts ***");
  console.log(await writeN3(groundFacts.getQuads()));

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
  resultStore.addQuads(groundFacts.getQuads());

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

  return new Response(content || null, {
    status: statusCode,
    headers: {
      "Content-Type": explicitContentType || contentType,
    },
  });
}
