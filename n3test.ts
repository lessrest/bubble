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

  await t.step("should identify Pet and Pal correctly", () => {
    assertTriples(store, [
      [Schema.Pet, RDF.type, Schema.Bird],
      [Schema.Pal, RDF.type, Schema.Fish]
    ]);
  });

  await t.step("should establish Pal knows Pet", () => {
    assertTriple(store, Schema.Pal, Schema.knows, Schema.Pet);
  });
});

Deno.test("Character and Pet Classifications with Reasoning", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = await applyRules(quads, typeInferenceRule);
  
  await t.step("should infer all animals as both Characters and Pets through subclass reasoning", () => {
    assertTriples(store, [
      [Schema.Pet, RDF.type, Schema.Pet],
      [Schema.Pet, RDF.type, Schema.Character],
      [Schema.Pal, RDF.type, Schema.Pet],
      [Schema.Pal, RDF.type, Schema.Character],
      [Schema.Pip, RDF.type, Schema.Pet],
      [Schema.Pip, RDF.type, Schema.Character]
    ]);
  });
});

Deno.test("RDF without transitive rules", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = new N3.Store();
  store.addQuads(quads);
  
  await t.step("should not have transitive inference without rules", () => {
    const pipKnowsPet = store.getQuads(
      Schema.Pip,
      Schema.knows,
      Schema.Pet,
      null
    );
    assertEquals(pipKnowsPet.length, 0,
      "Should not infer that Pip knows Pet without applying rules");
  });
});

Deno.test("Transitive Reasoning with N3 Rules", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = await applyRules(quads, transitiveRule);
  
  await t.step("should have basic triples", () => {
    assertTriples(store, [
      [Schema.Pip, RDF.type, Schema.Seal]
    ]);
  });

  await t.step("should infer Pip knows Pet through transitivity", () => {
    assertTriples(store, [
      [Schema.Pip, Schema.knows, Schema.Pet]
    ]);
  });
});
