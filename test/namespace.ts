import { DataFactory } from "n3";
const { namedNode } = DataFactory;

export function namespace(baseIRI: string) {
  return (term: string) => namedNode(baseIRI + term);
}

export const RDF = {
  ns: namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
  cartoons: namespace("http://example.org/cartoons#")
};
