import { assertEquals } from "@std/assert";
import N3 from "n3";
import { parseRDF, applyRules, assertTriple } from "./test/utils.ts";
import { tomAndJerry, transitiveRule } from "./test/data.ts";
import { RDF, Example } from "./test/namespace.ts";

const { DataFactory } = N3;
const { namedNode } = DataFactory;

Deno.test("Basic Tom and Jerry RDF", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  
  await t.step("should parse correct number of triples", () => {
    assertEquals(quads.length, 5);
  });

  await t.step("should identify Tom as a Cat", () => {
    assertTriple(quads[0], "Tom", RDF("type").value, "Cat");
  });

  await t.step("should identify Jerry as a Mouse", () => {
    assertTriple(quads[1], "Jerry", RDF("type").value, "Mouse");
  });

  await t.step("should establish Jerry is smarter than Tom", () => {
    assertTriple(quads[2], "Jerry", "smarterThan", "Tom");
  });
});

Deno.test("RDF without transitive rules", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = new N3.Store();
  store.addQuads(quads);
  
  await t.step("should not have transitive inference without rules", () => {
    const spikeIsSmarterThanTom = store.getQuads(
      Example("Spike"),
      Example("smarterThan"),
      Example("Tom"),
      null
    );
    assertEquals(spikeIsSmarterThanTom.length, 0,
      "Should not infer that Spike is smarter than Tom without applying rules");
  });
});

Deno.test("Transitive Reasoning with N3 Rules", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = await applyRules(quads, transitiveRule);
  
  await t.step("should have basic triples", () => {
    const spikeIsDog = store.getQuads(
      Example("Spike"),
      RDF("type"),
      Example("Dog"),
      null
    );
    assertEquals(spikeIsDog.length, 1);
  });

  await t.step("should infer Spike is smarter than Tom through transitivity", () => {
    const spikeIsSmarterThanTom = store.getQuads(
      Example("Spike"),
      Example("smarterThan"),
      Example("Tom"),
      null
    );
    assertEquals(spikeIsSmarterThanTom.length, 1, 
      "Expected to infer that Spike is smarter than Tom through transitivity");
  });
});
