import { assertEquals } from "@std/assert";
import N3 from "n3";
import { parseRDF, applyRules, assertTriple, assertTriples, assertTurtleGraph } from "./test/utils.ts";
import { tomAndJerry, transitiveRule, typeInferenceRule } from "./test/data.ts";
import { RDF, Schema } from "./test/namespace.ts";

Deno.test("RDF Parser", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  
  await t.step("parses expected triples", () => {
    assertEquals(quads.length, 9);
  });

  const store = new N3.Store();
  store.addQuads(quads);

  await t.step("identifies characters", () => {
    assertTurtleGraph(store, `
      schema:Eve a schema:Rat .
      schema:Bob a schema:Eel .
    `);
  });

  await t.step("verifies relationships", () => {
    assertTriple(store, Schema.Bob, Schema.knows, Schema.Eve);
  });
});

Deno.test("RDFS Subclass Inference", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = await applyRules(quads, typeInferenceRule);
  
  await t.step("infers types through subclassing", () => {
    assertTurtleGraph(store, `
      schema:Eve a schema:Pet, schema:Pal .
      schema:Bob a schema:Pet, schema:Pal .
      schema:Jim a schema:Pet, schema:Pal .
    `);
  });
});

Deno.test("No Inference Without Rules", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = new N3.Store();
  store.addQuads(quads);
  
  await t.step("has no inference without rules", () => {
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

Deno.test("Transitive Inference", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  const store = await applyRules(quads, transitiveRule);
  
  await t.step("infers transitive relationships", () => {
    assertTurtleGraph(store, `
      schema:Jim a schema:Owl ;
        schema:knows schema:Eve .
    `);
  });
});
