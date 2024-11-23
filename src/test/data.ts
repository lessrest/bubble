import { RDFS, Schema } from "../src/namespace.ts";

export const tomAndJerry = `PREFIX schema: <${Schema("").value}>
  PREFIX rdfs: <${RDFS("").value}>
  schema:Pet rdfs:subClassOf schema:Pal .
  schema:Rat rdfs:subClassOf schema:Pet .
  schema:Eel rdfs:subClassOf schema:Pet .
  schema:Owl rdfs:subClassOf schema:Pet .
  
  schema:Eve a schema:Rat .
  schema:Bob a schema:Eel ;
    schema:knows schema:Eve .
  schema:Jim a schema:Owl ;
    schema:knows schema:Bob .`;

export const typeInferenceRule = await Deno.readTextFile(
  new URL("../rules/type-inference.n3", import.meta.url),
);

export const transitiveRule = await Deno.readTextFile(
  new URL("../rules/transitive.n3", import.meta.url),
);
