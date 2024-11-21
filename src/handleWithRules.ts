import N3, { DataFactory, Store } from "n3";
import { Quad } from "@rdfjs/types";
import { HTTP } from "./namespace.ts";
import { renderHTML } from "./html.ts";
import { CommandLineReasoner } from "./reasoning.ts";
import { writeN3 } from "./utils.ts";
import { requestToStore } from "./requestToStore.ts";
import { getResponseData } from "./rdfUtils.ts";

export async function handleWithRules(
  request: Request,
  rules: string[],
  groundFacts?: Store,
  resultStore?: Store,
): Promise<Response> {
  const uuid = crypto.randomUUID();
  const requestIri = `urn:request:${uuid}`;
  const store = await requestToStore(request, requestIri);

  // Add ground facts if provided
  if (groundFacts) {
    store.addQuads(groundFacts.getQuads());
  }

  // Apply the rules
  const reasoner = new CommandLineReasoner();
  const n3Input = await writeN3(store.getQuads());
  const result = await reasoner.reason([n3Input, ...rules]);

  console.log(result);

  // Parse the results
  if (!resultStore) {
    resultStore = new N3.Store();
  }

  const parser = new N3.Parser({ format: "text/n3" });
  const resultQuads = parser.parse(result) as Quad[];
  resultStore.addQuads(resultQuads);

  const requestNode = DataFactory.namedNode(requestIri);
  const {
    response,
    statusCode,
    body: initialBody,
    contentType: responseContentType,
  } = getResponseData(resultStore, requestNode);

  if (!response) {
    return new Response("Not Found", { status: 404 });
  }

  if (!statusCode) {
    return new Response("Response missing status code", { status: 500 });
  }

  // Handle response body
  const bodyQuads = resultStore.getQuads(response, HTTP("body"), null, null);
  let body = "";
  let contentType = finalContentType;
  
  if (bodyQuads.length > 0) {
    const bodyStore = new N3.Store();
    let isHtmlContent = false;
    let isLiteralContent = false;

    for (const bodyQuad of bodyQuads) {
      if (isLiteralContent || isHtmlContent) {
        break; // Stop processing once we have literal/HTML content
      }

      if (bodyQuad.object.termType === "Literal") {
        if (bodyStore.size > 0) {
          throw new Error("Cannot mix N3 and literal content in response body");
        }
        body = bodyQuad.object.value;
        isLiteralContent = true;
        contentType = "text/plain";
      } else if (bodyQuad.object.termType === "Quad") {
        bodyStore.addQuad(bodyQuad.object);
      } else if (
        bodyQuad.object.termType === "BlankNode" ||
        bodyQuad.object.termType === "NamedNode"
      ) {
        // Check if this is an HTML page
        const isHtmlPage = resultStore.getQuads(
          bodyQuad.object,
          DataFactory.namedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
          DataFactory.namedNode("http://www.w3.org/1999/xhtml#element"),
          null
        ).length > 0;

        if (isHtmlPage) {
          if (bodyStore.size > 0) {
            throw new Error("Cannot mix N3 and HTML content in response body");
          }
          body = await renderHTML(resultStore, bodyQuad.object);
          isHtmlContent = true;
          contentType = "text/html";
        } else {
          const graphId = bodyQuad.object.termType === "BlankNode"
            ? `_:${bodyQuad.object.value}`
            : bodyQuad.object.value;
          const subgraph = resultStore.getQuads(null, null, null, graphId) as Quad[];
          bodyStore.addQuads(subgraph);
        }
      }
    }

    // Only serialize N3 if we haven't found literal or HTML content
    if (!isLiteralContent && !isHtmlContent && bodyStore.size > 0) {
      body = await writeN3(bodyStore.getQuads());
      contentType = "text/turtle";
    }
  }

  // Content-Type
  const contentTypeQuads = resultStore.getQuads(
    response,
    DataFactory.namedNode("http://www.w3.org/2011/http#contentType"),
    null,
    null,
  );

  const finalContentType = contentTypeQuads.length > 0
    ? contentTypeQuads[0].object.value
    : "text/plain";

  return new Response(body || null, {
    status: statusCode,
    headers: { "Content-Type": contentType },
  });
}
