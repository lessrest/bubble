import { createDataset } from "@rdfjs/dataset";
import { LdoDataset } from "ldo";

export function createTriple(subject: string, predicate: string, object: string) {
  const dataset = createDataset();
  const ldoDataset = new LdoDataset(dataset);
  
  ldoDataset.addQuad(
    subject,
    predicate,
    object
  );
  
  return ldoDataset;
}

if (import.meta.main) {
  const dataset = createTriple(
    "http://example.org/cartoons#Tom",
    "http://example.org/cartoons#chases",
    "Jerry"
  );
  
  // Print all quads in the dataset
  for (const quad of dataset.dataset) {
    console.log("Created triple:", quad.toString());
  }
}
