import { assertEquals } from "@std/assert";
import N3 from "n3";
import { parseRDF, applyRules, assertTriple, assertTriples } from "./test/utils.ts";
import { tomAndJerry, transitiveRule } from "./test/data.ts";
import { RDF, Schema } from "./test/namespace.ts";

Deno.test("Basic Tom and Jerry RDF", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  
  await t.step("should parse correct number of triples", () => {
    assertEquals(quads.length, 11);
  });

  const store = new N3.Store();
  store.addQuads(quads);

  await t.step("should identify Tom and Jerry correctly", () => {
    assertTriples(store, [
      [Schema("Tom"), RDF("type"), Schema("Cat")],
      [Schema("Jerry"), RDF("type"), Schema("Mouse")]
    ]);
  });

  await t.step("should establish Jerry is smarter than Tom", () => {
    assertTriple(store, Schema("Jerry"), Schema("knows"), Schema("Tom"));
  });
});

Deno.test("Character and Pet Classifications with Reasoning", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = await applyRules(quads, typeInferenceRule);
  
  await t.step("should infer all animals as both Characters and Pets through subclass reasoning", () => {
    assertTriples(store, [
      [Schema("Tom"), RDF("type"), Schema("Pet")],
      [Schema("Tom"), RDF("type"), Schema("Character")],
      [Schema("Jerry"), RDF("type"), Schema("Pet")],
      [Schema("Jerry"), RDF("type"), Schema("Character")],
      [Schema("Spike"), RDF("type"), Schema("Pet")],
      [Schema("Spike"), RDF("type"), Schema("Character")]
    ]);
  });
});

Deno.test("RDF without transitive rules", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = new N3.Store();
  store.addQuads(quads);
  
  await t.step("should not have transitive inference without rules", () => {
    const spikeIsSmarterThanTom = store.getQuads(
      Schema("Spike"),
      Schema("knows"),
      Schema("Tom"),
      null
    );
    assertEquals(spikeIsSmarterThanTom.length, 0,
      "Should not infer that Spike knows Tom without applying rules");
  });
});

Deno.test("Transitive Reasoning with N3 Rules", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = await applyRules(quads, transitiveRule);
  
  await t.step("should have basic triples", () => {
    const spikeIsDog = store.getQuads(
      Schema("Spike"),
      RDF("type"),
      Schema("Dog"),
      null
    );
    assertEquals(spikeIsDog.length, 1);
  });

  await t.step("should infer Spike is smarter than Tom through transitivity", () => {
    const spikeIsSmarterThanTom = store.getQuads(
      Schema("Spike"),
      Schema("knows"),
      Schema("Tom"),
      null
    );
    assertEquals(spikeIsSmarterThanTom.length, 1, 
      "Expected to infer that Spike knows Tom through transitivity");
  });
});
