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

export async function applyRules(data: Quad[], rules: string): Promise<N3.Store> {
  const store = new N3.Store();
  store.addQuads(data);
  
  // Parse the rules into a separate store
  const parser = new N3.Parser({ format: 'text/n3' });
  const rulesQuads = parser.parse(rules);
  const rulesStore = new N3.Store(rulesQuads);

  // Create a reasoner and apply the rules
  const reasoner = new N3.Reasoner(store);
  reasoner.reason(rulesStore);

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
