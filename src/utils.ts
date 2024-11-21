import { assertEquals } from "@std/assert";
import { Quad, Term } from "@rdfjs/types";
import N3, { DataFactory } from "n3";
import { n3reasoner } from "eyereasoner";
import { Schema } from "./namespace.ts";
import { Store } from "n3";

export async function parseRDF(input: string): Promise<Quad[]> {
  const parser = new N3.Parser();
  return parser.parse(input);
}

export function writeN3(quads: Quad[]): Promise<string> {
  const writer = new N3.Writer({
    format: "text/n3",
    prefixes: { schema: Schema("").value },
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

export function requestToStore(request: Request): Store {
  const store = new N3.Store();
  const url = new URL(request.url);
  
  // Create a blank node for the request
  const requestNode = DataFactory.blankNode();
  
  // Add basic request triples
  store.addQuad(
    requestNode,
    DataFactory.namedNode('http://www.w3.org/1999/02/22-rdf-syntax-ns#type'),
    DataFactory.namedNode('http://www.w3.org/2011/http#Request')
  );
  
  // Add path
  store.addQuad(
    requestNode,
    DataFactory.namedNode('http://www.w3.org/2011/http#path'),
    DataFactory.literal(url.pathname)
  );

  return store;
}

export async function handleWithRules(
  request: Request,
  rules: string
): Promise<Response> {
  // Convert request to RDF store
  const store = requestToStore(request);
  
  // Apply the rules
  const result = await n3reasoner(
    await writeN3(store.getQuads()) + "\n" + rules,
    undefined,
    { output: "deductive_closure" }
  );

  // Parse the results
  const resultStore = new N3.Store();
  const parser = new N3.Parser({ format: "text/n3" });
  const resultQuads = parser.parse(result);
  resultStore.addQuads(resultQuads);

  // Look for response triples
  const responseQuads = resultStore.getQuads(
    null,
    DataFactory.namedNode("http://www.w3.org/2011/http#responseCode"),
    null,
    null
  );

  if (responseQuads.length === 0) {
    return new Response("No response derived", { status: 404 });
  }

  const statusCode = parseInt(responseQuads[0].object.value);
  const bodyQuads = resultStore.getQuads(
    responseQuads[0].subject,
    DataFactory.namedNode("http://www.w3.org/2011/http#body"),
    null,
    null
  );

  const body = bodyQuads.length > 0 ? bodyQuads[0].object.value : "";
  
  return new Response(body, { status: statusCode });
}
