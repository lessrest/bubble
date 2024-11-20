import { assertEquals } from "@std/assert";
import { Quad } from "@rdfjs/types";
import N3 from "n3";
import { Readable } from "node:stream";
import { n3reasoner } from "eyereasoner";
import { RDF } from "./data.ts";

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
  
  const writer = new N3.Writer({ format: 'text/n3', prefixes: { c: RDF.cartoons } });
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

export function assertTriple(quad: Quad, subject: string, predicate: string, object: string) {
  assertEquals(quad.subject.value, RDF.cartoons(subject).value);
  assertEquals(quad.predicate.value, predicate.startsWith("http") ? predicate : RDF.cartoons(predicate).value);
  assertEquals(quad.object.value, RDF.cartoons(object).value);
}
