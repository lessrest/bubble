import { assertEquals } from "@std/assert";
import { Quad, Term } from "@rdfjs/types";
import N3, { DataFactory } from "n3";
import { n3reasoner } from "eyereasoner";
import { ACTIVITY_STREAMS, EXAMPLE, HTTP, Schema } from "./namespace.ts";
import { Store } from "n3";

export async function parseRDF(input: string): Promise<Quad[]> {
  const parser = new N3.Parser();
  return parser.parse(input);
}

export function writeN3(quads: Quad[]): Promise<string> {
  const writer = new N3.Writer({
    format: "text/n3",
    prefixes: {
      schema: Schema("").value,
      http: HTTP("").value,
      ex: EXAMPLE("").value,
      as: ACTIVITY_STREAMS("").value,
    },
  });

  for (const quad of quads) {
    writer.addQuad(quad);
  }

  return new Promise<string>((resolve, reject) => {
    writer.end((error: Error | null, result: string) =>
      error ? reject(error) : resolve(result)
    );
  });
}

export async function applyRules(
  data: Quad[],
  rules: string,
): Promise<N3.Store> {
  const store = new N3.Store();
  store.addQuads(data);

  const n3Data = await writeN3(data);
  const result = await n3reasoner(`${n3Data}\n${rules}`, undefined);

  const parser = new N3.Parser({ format: "text/n3" });
  const resultQuads = parser.parse(result) as Quad[];
  store.addQuads(resultQuads);

  return store;
}

export function assertTriple(
  store: Store,
  subject: Term,
  predicate: Term,
  object: Term,
): void {
  const matches = store.getQuads(subject, predicate, object, null);
  assertEquals(
    matches.length,
    1,
    `Expected triple: <${subject.value}> <${predicate.value}> <${object.value}>`,
  );
}

export function assertTriples(
  store: Store,
  triples: [Term, Term, Term][],
): void {
  for (const [subject, predicate, object] of triples) {
    assertTriple(store, subject, predicate, object);
  }
}

function getStandardPrefixes(): string {
  return `
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix schema: <http://schema.org/> .
@prefix http: <http://www.w3.org/2011/http#> .
@prefix string: <http://www.w3.org/2000/10/swap/string#> .
@prefix e: <http://eulersharp.sourceforge.net/2003/03swap/log-rules#> .
@prefix as: <http://www.w3.org/ns/activitystreams#> .
`;
}

export async function assertQuery(
  store: Store,
  query: string,
  message: string,
): Promise<void> {
  const fullQuery = `
      ${getStandardPrefixes()}
      @prefix test: <http://example.org/test#> .
      
      ${query}
      => {
        [] a test:Success;
          test:message "${message}" .
      }.
    `;

  await assertN3Query(store, fullQuery, message);
}

export async function assertN3Query(
  store: Store,
  query: string,
  expectedMessage: string,
): Promise<void> {
  const result = await n3reasoner(
    await writeN3(store.getQuads()) + "\n" + query,
    undefined,
    {
      output: "deductive_closure",
    },
  );
  const resultStore = new N3.Store();
  const parser = new N3.Parser({ format: "text/n3" });
  const resultQuads = parser.parse(result);
  resultStore.addQuads(resultQuads);

  const successQuads = resultStore.getQuads(
    null,
    DataFactory.namedNode("http://example.org/test#message"),
    DataFactory.literal(expectedMessage),
    null,
  );

  assertEquals(
    successQuads.length > 0,
    true,
    `N3 query failed to match expected pattern.
Actual graph contents:

${await writeN3(
      store.getQuads(),
    )}`,
  );
}

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

  // // Add body
  // store.addQuad(
  //   requestNode,
  //   DataFactory.namedNode("http://www.w3.org/2011/http#body"),
  //   DataFactory.literal(await request.text()),
  // );

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

export function withGroundFacts(facts: string): Store {
  const store = new N3.Store();
  const parser = new N3.Parser();
  store.addQuads(parser.parse(facts));
  return store;
}

export async function handleWithRules(
  request: Request,
  rules: string,
  groundFacts?: Store,
  resultStore?: Store,
): Promise<Response> {
  // Convert request to RDF store
  // Use request URL as the IRI
  const requestIri = request.url;
  const store = await requestToStore(request, requestIri);

  // Add ground facts if provided
  if (groundFacts) {
    store.addQuads(groundFacts.getQuads());
  }

  // Apply the rules
  const n3Input = await writeN3(store.getQuads()) + "\n" + rules;
  const result = await n3reasoner(
    n3Input,
    undefined,
    { output: "deductive_closure" },
  );
  // Parse the results
  if (!resultStore) {
    resultStore = new N3.Store();
  }

  const parser = new N3.Parser({ format: "text/n3" });

  const resultQuads = parser.parse(result) as Quad[];

  resultStore.addQuads(resultQuads);

  // Find request node
  const requestQuads = resultStore.getQuads(
    DataFactory.namedNode(requestIri),
    DataFactory.namedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
    DataFactory.namedNode("http://www.w3.org/2011/http#Request"),
    null,
  );

  if (requestQuads.length === 0) {
    return new Response("Request not found in result", { status: 500 });
  }

  // Look for response that responds to this request
  const responseQuads = resultStore.getQuads(
    null,
    DataFactory.namedNode("http://www.w3.org/2011/http#respondsTo"),
    requestQuads[0].subject,
    null,
  );

  if (responseQuads.length === 0) {
    return new Response("Not Found", { status: 404 });
  }

  // Get status code for the response
  const statusQuads = resultStore.getQuads(
    responseQuads[0].subject,
    DataFactory.namedNode("http://www.w3.org/2011/http#responseCode"),
    null,
    null,
  );

  if (statusQuads.length === 0) {
    return new Response("Response missing status code", { status: 500 });
  }

  const statusCode = parseInt(statusQuads[0].object.value);

  // Get response body
  const bodyQuads = resultStore.getQuads(
    responseQuads[0].subject,
    DataFactory.namedNode("http://www.w3.org/2011/http#body"),
    null,
    null,
  );

  let body: string | null = null;

  if (bodyQuads.length > 0) {
    // if the body object is a Quad, convert it to N3 string
    if (bodyQuads[0].object.termType === "Quad") {
      body = await writeN3([bodyQuads[0].object]);
    } else if (bodyQuads[0].object.termType === "Literal") {
      body = bodyQuads[0].object.value;
    } else if (bodyQuads[0].object.termType === "BlankNode") {
      const subgraph = resultStore.getQuads(
        null,
        null,
        null,
        `_:${bodyQuads[0].object.value}`,
      ) as Quad[];
      const bodyStore = new N3.Store();
      for (const quad of subgraph) {
        bodyStore.addQuad(quad.subject, quad.predicate, quad.object);
      }
      body = await writeN3(bodyStore.getQuads());
    } else {
      console.log(
        await writeN3(resultQuads),
      );
      throw new Error(`Unsupported body type: ${bodyQuads[0].object.termType}`);
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
