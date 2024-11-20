import { assertEquals } from "@std/assert";
import N3 from "n3";
import { Quad } from "@rdfjs/types";
import { Readable } from "node:stream";

const RDF = {
  type: "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
  cartoons: "http://example.org/cartoons#"
};

const tomAndJerry = `PREFIX c: <${RDF.cartoons}>
  # Tom is a cat
  c:Tom a c:Cat.
  c:Jerry a c:Mouse;
    c:smarterThan c:Tom.`;

async function parseRDF(input: string): Promise<Quad[]> {
  const parser = new N3.StreamParser();
  const stream = Readable.from([input]);
  const quads: Quad[] = [];
  
  for await (const quad of stream.pipe(parser)) {
    quads.push(quad);
  }
  
  return quads;
}

function assertTriple(quad: Quad, subject: string, predicate: string, object: string) {
  assertEquals(quad.subject.value, RDF.cartoons + subject);
  assertEquals(quad.predicate.value, predicate.startsWith("http") ? predicate : RDF.cartoons + predicate);
  assertEquals(quad.object.value, RDF.cartoons + object);
}

Deno.test("Tom and Jerry RDF", async (t) => {
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
