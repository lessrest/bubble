import { assertEquals } from "@std/assert";
import N3 from "n3";
import { Quad } from "@rdfjs/types";
import { Readable } from "node:stream";

const tomAndJerry = `PREFIX c: <http://example.org/cartoons#>
  # Tom is a cat
  c:Tom a c:Cat.
  c:Jerry a c:Mouse;
    c:smarterThan c:Tom.`;

Deno.test("Parse Tom and Jerry RDF", async () => {
  const parser = new N3.StreamParser();
  const input = Readable.from([tomAndJerry]);
  const quads: Quad[] = [];

  for await (const quad of input.pipe(parser)) {
    quads.push(quad);
  }

  // Verify we got 3 triples (quads)
  assertEquals(quads.length, 3);

  // Verify specific triples
  const cartoons = "http://example.org/cartoons#";
  
  // Tom is a Cat
  assertEquals(quads[0].subject.value, cartoons + "Tom");
  assertEquals(quads[0].predicate.value, "http://www.w3.org/1999/02/22-rdf-syntax-ns#type");
  assertEquals(quads[0].object.value, cartoons + "Cat");

  // Jerry is a Mouse  
  assertEquals(quads[1].subject.value, cartoons + "Jerry");
  assertEquals(quads[1].predicate.value, "http://www.w3.org/1999/02/22-rdf-syntax-ns#type");
  assertEquals(quads[1].object.value, cartoons + "Mouse");

  // Jerry is smarter than Tom
  assertEquals(quads[2].subject.value, cartoons + "Jerry");
  assertEquals(quads[2].predicate.value, cartoons + "smarterThan");
  assertEquals(quads[2].object.value, cartoons + "Tom");
});
