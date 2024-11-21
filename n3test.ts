import { assertEquals } from "@std/assert";
import N3 from "n3";
import { parseRDF, applyRules, assertTriple, assertTriples } from "./test/utils.ts";
import { tomAndJerry, transitiveRule, typeInferenceRule } from "./test/data.ts";
import { RDF, Schema } from "./test/namespace.ts";

Deno.test("Basic Tom and Jerry RDF", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  
  await t.step("should parse correct number of triples", () => {
    assertEquals(quads.length, 9);
  });

  const store = new N3.Store();
  store.addQuads(quads);

  await t.step("should identify Eve and Bob correctly", () => {
    assertTriples(store, [
      [Schema.Eve, RDF.type, Schema.Rat],
      [Schema.Bob, RDF.type, Schema.Eel]
    ]);
  });

  await t.step("should establish Bob knows Eve", () => {
    assertTriple(store, Schema.Bob, Schema.knows, Schema.Eve);
  });
});

Deno.test("Pet Classifications with Reasoning", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = await applyRules(quads, typeInferenceRule);
  
  await t.step("should infer all animals as both Pals and Pets through subclass reasoning", () => {
    assertTriples(store, [
      [Schema.Eve, RDF.type, Schema.Pet],
      [Schema.Eve, RDF.type, Schema.Pal],
      [Schema.Bob, RDF.type, Schema.Pet],
      [Schema.Bob, RDF.type, Schema.Pal],
      [Schema.Jim, RDF.type, Schema.Pet],
      [Schema.Jim, RDF.type, Schema.Pal]
    ]);
  });
});

Deno.test("RDF without transitive rules", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = new N3.Store();
  store.addQuads(quads);
  
  await t.step("should not have transitive inference without rules", () => {
    const jimKnowsEve = store.getQuads(
      Schema.Jim,
      Schema.knows,
      Schema.Eve,
      null
    );
    assertEquals(jimKnowsEve.length, 0,
      "Should not infer that Jim knows Eve without applying rules");
  });
});

Deno.test("Transitive Reasoning with N3 Rules", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = await applyRules(quads, transitiveRule);
  
  await t.step("should have basic triples", () => {
    assertTriples(store, [
      [Schema.Jim, RDF.type, Schema.Owl]
    ]);
  });

  await t.step("should infer Jim knows Eve through transitivity", () => {
    assertTriples(store, [
      [Schema.Jim, Schema.knows, Schema.Eve]
    ]);
  });
});
