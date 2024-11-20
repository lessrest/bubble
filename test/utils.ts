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
  
  console.log("\nInitial quads:");
  for (const quad of store) {
    console.log(quad);
  }
  
  const writer = new N3.Writer({ format: 'text/n3', prefixes: { schema: Schema("").value } });
  data.forEach(quad => writer.addQuad(quad));
  
  const n3Data = await new Promise<string>((resolve, reject) => {
    writer.end((error: Error | null, result: string) => error ? reject(error) : resolve(result));
  });

  const result = await n3reasoner(n3Data, rules);
  
  const parser = new N3.Parser({ format: 'text/n3' });
  const resultQuads = parser.parse(result) as Quad[];
  store.addQuads(resultQuads);

  console.log("\nFinal quads after applying rules:");
  for (const quad of store) {
    console.log(quad);
  }
  
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
