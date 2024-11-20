import { assertEquals } from "@std/assert";
import N3 from "n3";
import { parseRDF, applyRules } from "./test/utils.ts";
import { tomAndJerry, transitiveRule } from "./test/data.ts";
import { RDF, Schema } from "./test/namespace.ts";

Deno.test("Basic Tom and Jerry RDF", async (t) => {
  const quads = await parseRDF(tomAndJerry);
  
  await t.step("should parse correct number of triples", () => {
    assertEquals(quads.length, 9);
  });

  await t.step("should identify Tom as a Cat", () => {
    const tomIsCat = quads.some(quad => 
      quad.subject.value === Schema("Tom").value &&
      quad.predicate.value === RDF("type").value &&
      quad.object.value === Schema("Cat").value
    );
    assertEquals(tomIsCat, true);
  });

  await t.step("should identify Jerry as a Mouse", () => {
    const jerryIsMouse = quads.some(quad =>
      quad.subject.value === Schema("Jerry").value &&
      quad.predicate.value === RDF("type").value &&
      quad.object.value === Schema("Mouse").value
    );
    assertEquals(jerryIsMouse, true);
  });

  await t.step("should establish Jerry is smarter than Tom", () => {
    const jerryKnowsTom = quads.some(quad =>
      quad.subject.value === Schema("Jerry").value &&
      quad.predicate.value === Schema("knows").value &&
      quad.object.value === Schema("Tom").value
    );
    assertEquals(jerryKnowsTom, true);
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
