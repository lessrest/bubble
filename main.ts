import * as RDF from "@rdfjs/data-model";

export function createTriple(subject: string, predicate: string, object: string) {
  const triple = RDF.quad(
    RDF.namedNode(subject),
    RDF.namedNode(predicate),
    RDF.literal(object)
  );
  return triple;
}

if (import.meta.main) {
  const triple = createTriple(
    "http://example.org/cartoons#Tom",
    "http://example.org/cartoons#chases",
    "Jerry"
  );
  console.log("Created triple:", triple.toString());
}
