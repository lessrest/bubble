import N3, { Store } from "n3";
import { Quad } from "@rdfjs/types";
import { renderHTML } from "./html.ts";
import { CommandLineReasoner } from "./reasoning.ts";
import { writeN3 } from "./utils.ts";
import { requestToStore } from "./requestToStore.ts";
import { findSubject, getResponseData } from "./rdfUtils.ts";

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

  // Parse the results
  if (!resultStore) {
    resultStore = new N3.Store();
  }

  const parser = new N3.Parser({ format: "text/n3" });
  const resultQuads = parser.parse(result) as Quad[];
  resultStore.addQuads(resultQuads);

  const requestNode = findSubject(resultStore, "http://www.w3.org/2011/http#Request");
  if (!requestNode) {
    return new Response("Request not found in result", { status: 500 });
  }

  const { response, statusCode, body: initialBody, contentType } = getResponseData(resultStore, requestNode);
  
  if (!response) {
    return new Response("Not Found", { status: 404 });
  }

  if (!statusCode) {
    return new Response("Response missing status code", { status: 500 });
  }

  let body = initialBody;

  if (bodyQuads.length > 0) {
    const bodyStore = new N3.Store();

    for (const bodyQuad of bodyQuads) {
      if (bodyQuad.object.termType === "Quad") {
        bodyStore.addQuad(bodyQuad.object);
      } else if (bodyQuad.object.termType === "Literal") {
        // For literals, concatenate their values
        body = (body ?? "") + bodyQuad.object.value;
      } else if (
        bodyQuad.object.termType === "BlankNode" ||
        bodyQuad.object.termType === "NamedNode"
      ) {
        // Check if this is an HTML page
        const isHtmlPage = resultStore.getQuads(
          bodyQuad.object,
          DataFactory.namedNode(
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
          ),
          DataFactory.namedNode("http://www.w3.org/1999/xhtml#element"),
          null,
        ).length > 0;

        if (isHtmlPage) {
          // console.log(
          //   `Before rendering HTML: ${await writeN3(resultStore.getQuads())}`,
          // );
          body = await renderHTML(resultStore, bodyQuad.object);
        } else {
          const graphId = bodyQuad.object.termType === "BlankNode"
            ? `_:${bodyQuad.object.value}`
            : bodyQuad.object.value;
          const subgraph = resultStore.getQuads(
            null,
            null,
            null,
            graphId,
          ) as Quad[];
          for (const quad of subgraph) {
            bodyStore.addQuad(quad.subject, quad.predicate, quad.object);
          }
        }
      } else {
        console.log(
          await writeN3(resultQuads),
        );
        throw new Error(`Unsupported body type: ${bodyQuad.object.termType}`);
      }
    }

    // If we collected any quads, serialize them
    if (bodyStore.size > 0) {
      body = (body ?? "") + await writeN3(bodyStore.getQuads());
    }
  }

  // Content-Type
  const contentTypeQuads = resultStore.getQuads(
    responseQuads[0].subject,
    DataFactory.namedNode("http://www.w3.org/2011/http#contentType"),
    null,
    null,
  );

  const contentType = contentTypeQuads.length > 0
    ? contentTypeQuads[0].object.value
    : "text/plain";

  return new Response(body, {
    status: statusCode,
    headers: { "Content-Type": contentType },
  });
}
