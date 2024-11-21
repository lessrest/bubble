import { Schema, RDFS } from "./namespace.ts";

export const tomAndJerry = `PREFIX schema: <${Schema("").value}>
  PREFIX rdfs: <${RDFS("").value}>
  schema:Pet rdfs:subClassOf schema:Pal .
  schema:Bird rdfs:subClassOf schema:Pet .
  schema:Fish rdfs:subClassOf schema:Pet .
  schema:Seal rdfs:subClassOf schema:Pet .
  
  schema:Eve a schema:Bird .
  schema:Bob a schema:Fish ;
    schema:knows schema:Eve .
  schema:Jim a schema:Seal ;
    schema:knows schema:Bob .`;

export const typeInferenceRule = await Deno.readTextFile(
  new URL("./rules/type-inference.n3", import.meta.url)
);

export const transitiveRule = await Deno.readTextFile(
  new URL("./rules/transitive.n3", import.meta.url)
);
