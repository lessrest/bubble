import { assertEquals } from "@std/assert";
import { Quad, Term } from "@rdfjs/types";
import N3 from "n3";
import { Readable } from "node:stream";
import { n3reasoner } from "eyereasoner";
import { Schema } from "./namespace.ts";
import { Store } from "n3";

export async function parseRDF(input: string): Promise<Quad[]> {
  const parser = new N3.StreamParser();
  const stream = Readable.from([input]);
  const quads: Quad[] = [];
  
  for await (const quad of stream.pipe(parser)) {
    quads.push(quad);
  }
  
  return quads;
}

export function writeN3(quads: Quad[]): Promise<string> {
  const writer = new N3.Writer({ format: 'text/n3', prefixes: { schema: Schema("").value } });
  quads.forEach(quad => writer.addQuad(quad));
  return new Promise<string>((resolve, reject) => {
    writer.end((error: Error | null, result: string) => error ? reject(error) : resolve(result));
  });
}

export async function applyRules(data: Quad[], rules: string): Promise<N3.Store> {
  const store = new N3.Store();
  store.addQuads(data);
  
  const n3Data = await writeN3(data);
  const combinedInput = n3Data + '\n' + rules;
  const result = await n3reasoner(combinedInput, undefined);
  
  const parser = new N3.Parser({ format: 'text/n3' });
  const resultQuads = parser.parse(result) as Quad[];
  store.addQuads(resultQuads);
  
  return store;
}

export function assertTriple(store: Store, subject: Term, predicate: Term, object: Term) {
  const matches = store.getQuads(subject, predicate, object, null);
  assertEquals(matches.length, 1, 
    `Expected triple: <${subject.value}> <${predicate.value}> <${object.value}>`);
}

export function assertTriples(store: Store, triples: [Term, Term, Term][]) {
  triples.forEach(([subject, predicate, object]) => {
    assertTriple(store, subject, predicate, object);
  });
}

function getStandardPrefixes(): string {
  return `
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix schema: <http://schema.org/> .
`;
}

export async function assertN3Query(store: Store, query: string) {
  const result = await n3reasoner(await writeN3(store.getQuads()), query);
  
  // Query to find success messages
  const messageQuery = `
    @prefix test: <http://example.org/test#> .
    {
      ?x a test:Success;
         test:message ?message.
    } => {
      ?x test:foundMessage ?message.
    }.
  `;
  
  const messages = await n3reasoner(result, messageQuery);
  
  assertEquals(messages.length > 0, true,
    `N3 query failed to match expected pattern.\nActual graph contents:\n${await writeN3(store.getQuads())}`);

  console.log("\nTest successes:");
  const messageRegex = /test:foundMessage "([^"]+)"/g;
  for (const match of messages.matchAll(messageRegex)) {
    console.log(`✓ ${match[1]}`);
  }
}
