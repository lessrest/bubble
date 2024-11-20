import { assertEquals } from "@std/assert";
import { Quad } from "@rdfjs/types";
import N3 from "n3";
import { Readable } from "node:stream";
import { n3reasoner } from "eyereasoner";
import { Schema, RDF } from "./namespace.ts";
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
  
  const writer = new N3.Writer({ format: 'text/n3', prefixes: { schema: Schema("").value } });
  data.forEach(quad => writer.addQuad(quad));
  
  const n3Data = await new Promise<string>((resolve, reject) => {
    writer.end((error: Error | null, result: string) => error ? reject(error) : resolve(result));
  });

  const result = await n3reasoner(n3Data, rules);
  
  const parser = new N3.Parser({ format: 'text/n3' });
  const resultQuads = parser.parse(result);
  store.addQuads(resultQuads);
  
  return store;
}

export function assertTriple(store: Store, subject: string, predicate: string, object: string) {
  const matches = store.getQuads(
    Schema(subject),
    predicate.startsWith("http://") ? namedNode(predicate) : Schema(predicate),
    object.startsWith("http://") ? namedNode(object) : Schema(object),
    null
  );
  assertEquals(matches.length, 1, 
    `Expected triple: ${subject} ${predicate} ${object}`);
}
