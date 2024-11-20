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

export const typeInferenceRule = await Deno.readTextFile(
  new URL("./rules/type-inference.n3", import.meta.url)
);

export const transitiveRule = await Deno.readTextFile(
  new URL("./rules/transitive.n3", import.meta.url)
);
