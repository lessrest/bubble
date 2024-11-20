import { assertEquals } from "@std/assert";
import { createTriple } from "./main.ts";

Deno.test(function datasetTest() {
  const dataset = createTriple(
    "http://example.org/cartoons#Tom",
    "http://example.org/cartoons#chases",
    "Jerry"
  );

  // Get the first (and only) quad from the dataset
  const quad = Array.from(dataset.dataset)[0];
  
  assertEquals(quad.subject.value, "http://example.org/cartoons#Tom");
  assertEquals(quad.predicate.value, "http://example.org/cartoons#chases");
  assertEquals(quad.object.value, "Jerry");
  
  // Verify we only have one quad in the dataset
  assertEquals(Array.from(dataset.dataset).length, 1);
});
