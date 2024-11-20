import { Schema, RDFS, RDF } from "./namespace.ts";

export const tomAndJerry = `PREFIX schema: <${Schema("").value}>
  PREFIX rdfs: <${RDFS("").value}>
  schema:Pet rdfs:subClassOf schema:Character .
  schema:Cat rdfs:subClassOf schema:Pet .
  schema:Mouse rdfs:subClassOf schema:Pet .
  schema:Dog rdfs:subClassOf schema:Pet .
  
  schema:Tom a schema:Cat .
  schema:Jerry a schema:Mouse ;
    schema:knows schema:Tom .
  schema:Spike a schema:Dog ;
    schema:knows schema:Jerry .`;

export const typeInferenceRule = `
  @prefix rdf: <${RDF("").value}> .
  @prefix rdfs: <${RDFS("").value}> .

  # transitive subclassing
  {
    ?class1 rdfs:subClassOf ?class2 .
    ?class2 rdfs:subClassOf ?class3 .
  } => {
    ?class1 rdfs:subClassOf ?class3 .
  }.

  {
    ?instance a ?class .
    ?class rdfs:subClassOf ?superclass .
  } => {
    ?instance rdf:type ?superclass .
  }.

`;

export const transitiveRule = `
  @prefix schema: <${Schema("").value}> .
  {
    ?x schema:knows ?y.
    ?y schema:knows ?z.
  } => {
    ?x schema:knows ?z.
  }.
`;
