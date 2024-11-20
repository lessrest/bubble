import { DataFactory } from "n3";
const { namedNode } = DataFactory;

export function namespace(baseIRI: string) {
  return (term: string) => namedNode(baseIRI + term);
}

export const RDF = namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#");
export const Schema = namespace("http://schema.org/");
