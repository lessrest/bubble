import { Schema } from "./namespace.ts";

export const tomAndJerry = `PREFIX schema: <${Schema("").value}>
  schema:Tom a schema:Character ;
    a schema:Pet ;
    a schema:Cat .
  schema:Jerry a schema:Character ;
    a schema:Pet ;
    a schema:Mouse ;
    schema:knows schema:Tom .
  schema:Spike a schema:Character ;
    a schema:Pet ;
    a schema:Dog ;
    schema:knows schema:Jerry .`;

export const transitiveRule = `
  @prefix schema: <${Schema("").value}> .
  {
    ?x schema:knows ?y.
    ?y schema:knows ?z.
  } => {
    ?x schema:knows ?z.
  }.
`;
