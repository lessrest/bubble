import { assertEquals } from "@std/assert";
import N3 from "n3";
import { parseRDF, applyRules, assertTriple } from "./test/utils.ts";
import { RDF, tomAndJerry, transitiveRule } from "./test/data.ts";

const { DataFactory } = N3;
const { namedNode } = DataFactory;

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
