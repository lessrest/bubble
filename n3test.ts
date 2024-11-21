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
      [Schema.Eve, RDF.type, Schema.Bird],
      [Schema.Bob, RDF.type, Schema.Fish]
    ]);
  });

  await t.step("should establish Bob knows Eve", () => {
    assertTriple(store, Schema.Bob, Schema.knows, Schema.Eve);
  });
});

Deno.test("Character and Pet Classifications with Reasoning", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = await applyRules(quads, typeInferenceRule);
  
  await t.step("should infer all animals as both Characters and Pets through subclass reasoning", () => {
    assertTriples(store, [
      [Schema.Eve, RDF.type, Schema.Pet],
      [Schema.Eve, RDF.type, Schema.Character],
      [Schema.Bob, RDF.type, Schema.Pet],
      [Schema.Bob, RDF.type, Schema.Character],
      [Schema.Jim, RDF.type, Schema.Pet],
      [Schema.Jim, RDF.type, Schema.Character]
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
    assertEquals(carolKnowsAlice.length, 0,
      "Should not infer that Jim knows Eve without applying rules");
  });
});

Deno.test("Transitive Reasoning with N3 Rules", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = await applyRules(quads, transitiveRule);
  
  await t.step("should have basic triples", () => {
    assertTriples(store, [
      [Schema.Jim, RDF.type, Schema.Seal]
    ]);
  });

  await t.step("should infer Carol knows Alice through transitivity", () => {
    assertTriples(store, [
      [Schema.Jim, Schema.knows, Schema.Eve]
    ]);
  });
});
