import { assertEquals } from "@std/assert";
import N3 from "n3";
import { Quad } from "@rdfjs/types";
import { Readable } from "node:stream";

// Add Store for inference
const { Store, StreamParser, DataFactory } = N3;
const { namedNode } = DataFactory;

const RDF = {
  type: "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
  cartoons: "http://example.org/cartoons#"
};

const tomAndJerry = `PREFIX c: <${RDF.cartoons}>
  c:Tom a c:Cat .
  c:Jerry a c:Mouse ;
    c:smarterThan c:Tom .
  c:Spike a c:Dog ;
    c:smarterThan c:Jerry .`;

const transitiveRule = `
  @prefix c: <${RDF.cartoons}> .
  {
    ?x c:smarterThan ?y.
    ?y c:smarterThan ?z.
  } => {
    ?x c:smarterThan ?z.
  }.
`;

async function parseRDF(input: string): Promise<Quad[]> {
  const parser = new StreamParser();
  const stream = Readable.from([input]);
  const quads: Quad[] = [];
  
  for await (const quad of stream.pipe(parser)) {
    quads.push(quad);
  }
  
  return quads;
}

import { n3reasoner } from "eyereasoner";

async function applyRules(data: Quad[], rules: string): Promise<N3.Store> {
  const store = new Store();
  store.addQuads(data);
  
  // Convert store to N3 string
  const writer = new N3.Writer({ format: 'text/n3', prefixes: { c: RDF.cartoons } });
  data.forEach(quad => writer.addQuad(quad));
  
  const n3Data = await new Promise<string>((resolve, reject) => {
    writer.end((error: Error | null, result: string) => error ? reject(error) : resolve(result));
  });

  // Use Eye reasoner
  const result = await n3reasoner(n3Data, rules);
  
  // Parse results back into store
  const parser = new N3.Parser({ format: 'text/n3' });
  const resultQuads = parser.parse(result);
  store.addQuads(resultQuads);
  
  return store;
}

function assertTriple(quad: Quad, subject: string, predicate: string, object: string) {
  assertEquals(quad.subject.value, RDF.cartoons + subject);
  assertEquals(quad.predicate.value, predicate.startsWith("http") ? predicate : RDF.cartoons + predicate);
  assertEquals(quad.object.value, RDF.cartoons + object);
}

Deno.test("Basic Tom and Jerry RDF", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  
  await t.step("should parse correct number of triples", () => {
    assertEquals(quads.length, 5);
  });

  await t.step("should identify Tom as a Cat", () => {
    assertTriple(quads[0], "Tom", RDF.type, "Cat");
  });

  await t.step("should identify Jerry as a Mouse", () => {
    assertTriple(quads[1], "Jerry", RDF.type, "Mouse");
  });

  await t.step("should establish Jerry is smarter than Tom", () => {
    assertTriple(quads[2], "Jerry", "smarterThan", "Tom");
  });
});

Deno.test("Transitive Reasoning with N3 Rules", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = await applyRules(quads, transitiveRule);
  
  await t.step("should have basic triples", () => {
    const spikeIsDog = store.getQuads(
      namedNode(RDF.cartoons + "Spike"),
      namedNode(RDF.type),
      namedNode(RDF.cartoons + "Dog"),
      null
    );
    assertEquals(spikeIsDog.length, 1);
  });

  await t.step("should infer Spike is smarter than Tom through transitivity", () => {
    const spikeIsSmarterThanTom = store.getQuads(
      namedNode(RDF.cartoons + "Spike"),
      namedNode(RDF.cartoons + "smarterThan"),
      namedNode(RDF.cartoons + "Tom"),
      null
    );
    assertEquals(spikeIsSmarterThanTom.length, 1, 
      "Expected to infer that Spike is smarter than Tom through transitivity");
  });
});
