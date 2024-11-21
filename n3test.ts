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

  await t.step("should identify Alice and Bobby correctly", () => {
    assertTriples(store, [
      [Schema.Alice, RDF.type, Schema.Bird],
      [Schema.Bobby, RDF.type, Schema.Fish]
    ]);
  });

  await t.step("should establish Bobby knows Alice", () => {
    assertTriple(store, Schema.Bobby, Schema.knows, Schema.Alice);
  });
});

Deno.test("Character and Pet Classifications with Reasoning", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = await applyRules(quads, typeInferenceRule);
  
  await t.step("should infer all animals as both Characters and Pets through subclass reasoning", () => {
    assertTriples(store, [
      [Schema.Alice, RDF.type, Schema.Pet],
      [Schema.Alice, RDF.type, Schema.Character],
      [Schema.Bobby, RDF.type, Schema.Pet],
      [Schema.Bobby, RDF.type, Schema.Character],
      [Schema.Carol, RDF.type, Schema.Pet],
      [Schema.Carol, RDF.type, Schema.Character]
    ]);
  });
});

Deno.test("RDF without transitive rules", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = new N3.Store();
  store.addQuads(quads);
  
  await t.step("should not have transitive inference without rules", () => {
    const carolKnowsAlice = store.getQuads(
      Schema.Carol,
      Schema.knows,
      Schema.Alice,
      null
    );
    assertEquals(carolKnowsAlice.length, 0,
      "Should not infer that Carol knows Alice without applying rules");
  });
});

Deno.test("Transitive Reasoning with N3 Rules", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = await applyRules(quads, transitiveRule);
  
  await t.step("should have basic triples", () => {
    assertTriples(store, [
      [Schema.Carol, RDF.type, Schema.Seal]
    ]);
  });

  await t.step("should infer Carol knows Alice through transitivity", () => {
    assertTriples(store, [
      [Schema.Carol, Schema.knows, Schema.Alice]
    ]);
  });
});
