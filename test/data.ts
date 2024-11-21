import { Schema, RDFS } from "./namespace.ts";

export const tomAndJerry = `PREFIX schema: <${Schema("").value}>
  PREFIX rdfs: <${RDFS("").value}>
  schema:Pet rdfs:subClassOf schema:Character .
  schema:Bird rdfs:subClassOf schema:Pet .
  schema:Fish rdfs:subClassOf schema:Pet .
  schema:Seal rdfs:subClassOf schema:Pet .
  
  schema:Alice a schema:Bird .
  schema:Bobby a schema:Fish ;
    schema:knows schema:Alice .
  schema:Carol a schema:Seal ;
    schema:knows schema:Bobby .`;

export const typeInferenceRule = await Deno.readTextFile(
  new URL("./rules/type-inference.n3", import.meta.url)
);

export const transitiveRule = await Deno.readTextFile(
  new URL("./rules/transitive.n3", import.meta.url)
);
