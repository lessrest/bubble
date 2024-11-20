import { assertEquals } from "@std/assert";
import { createTriple } from "./main.ts";

Deno.test(function tripleTest() {
  const triple = createTriple(
    "http://example.org/cartoons#Tom",
    "http://example.org/cartoons#chases",
    "Jerry"
  );
  assertEquals(triple.subject.value, "http://example.org/cartoons#Tom");
  assertEquals(triple.predicate.value, "http://example.org/cartoons#chases");
  assertEquals(triple.object.value, "Jerry");
});
