import { Schema, RDFS } from "./namespace.ts";

export const tomAndJerry = `PREFIX schema: <${Schema("").value}>
  PREFIX rdfs: <${RDFS("").value}>
  schema:Pet rdfs:subClassOf schema:Character .
  schema:Bird rdfs:subClassOf schema:Pet .
  schema:Fish rdfs:subClassOf schema:Pet .
  schema:Seal rdfs:subClassOf schema:Pet .
  
  schema:Pet a schema:Bird .
  schema:Pal a schema:Fish ;
    schema:knows schema:Pet .
  schema:Pip a schema:Seal ;
    schema:knows schema:Pal .`;

export const typeInferenceRule = await Deno.readTextFile(
  new URL("./rules/type-inference.n3", import.meta.url)
);

export const transitiveRule = await Deno.readTextFile(
  new URL("./rules/transitive.n3", import.meta.url)
);
