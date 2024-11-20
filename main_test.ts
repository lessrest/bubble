import { assertEquals } from "@std/assert";
import N3 from "n3";
import { Quad } from "@rdfjs/types";
import { Readable } from "node:stream";

// Add Store for inference
const { Store, StreamParser } = N3;

const RDF = {
  type: "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
  cartoons: "http://example.org/cartoons#"
};

const tomAndJerry = `PREFIX c: <${RDF.cartoons}>
  # Tom is a cat
  c:Tom a c:Cat.
  c:Jerry a c:Mouse;
    c:smarterThan c:Tom.
  c:Spike a c:Dog;
    c:smarterThan c:Jerry.`;

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

async function applyRules(data: Quad[], rules: string): Promise<N3.Store> {
  const store = new Store();
  const parser = new N3.Parser();
  
  // Add data
  store.addQuads(data);
  
  // Parse and add rules
  const ruleQuads = parser.parse(rules);
  store.addQuads(ruleQuads);
  
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
    assertEquals(quads.length, 3);
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
      store.createTerm(RDF.cartoons + "Spike"),
      store.createTerm(RDF.type),
      store.createTerm(RDF.cartoons + "Dog"),
      null
    );
    assertEquals(spikeIsDog.length, 1);
  });

  await t.step("should infer Spike is smarter than Tom through transitivity", () => {
    const spikeIsSmarterThanTom = store.getQuads(
      store.createTerm(RDF.cartoons + "Spike"),
      store.createTerm(RDF.cartoons + "smarterThan"),
      store.createTerm(RDF.cartoons + "Tom"),
      null
    );
    assertEquals(spikeIsSmarterThanTom.length, 1, 
      "Expected to infer that Spike is smarter than Tom through transitivity");
  });
});
