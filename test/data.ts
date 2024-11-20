import { Schema, RDFS } from "./namespace.ts";

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
  @prefix rdfs: <${RDFS("").value}> .
  @prefix schema: <${Schema("").value}> .
  {
    ?instance a ?class .
    ?class rdfs:subClassOf ?superclass .
  } => {
    ?instance a ?superclass .
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
