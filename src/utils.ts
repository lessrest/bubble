import { assertEquals } from "@std/assert";
import { Quad, Term } from "@rdfjs/types";
import N3, { DataFactory } from "n3";
import { CommandLineReasoner } from "./reasoning.ts";
import {
  ACTIVITY_STREAMS,
  EXAMPLE,
  HTML,
  HTTP,
  LOCAL,
  RDF,
  Schema,
  SWAP,
} from "./namespace.ts";
import { Store } from "n3";

export async function parseRDF(input: string): Promise<Quad[]> {
  console.log("*** PARSING ***");
  console.log(input);
  const parser = new N3.Parser({ format: "application/trig" });
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
      rdf: RDF("").value,
      html: HTML("").value,
      swap: SWAP("").value,
      local: LOCAL("").value,
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
@prefix local: <http://localhost:8000/> .
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
  const reasoner = new CommandLineReasoner();
  const result = await reasoner.reason(
    [await writeN3(store.getQuads())],
    { query },
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

export function withGroundFacts(facts: string): Store {
  const store = new N3.Store();
  const parser = new N3.Parser({ format: "application/trig" });
  store.addQuads(parser.parse(facts));
  return store;
}
