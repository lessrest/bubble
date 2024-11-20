import { Example } from "./namespace.ts";

export const tomAndJerry = `PREFIX c: <${Example("").value}>
  c:Tom a c:Cat .
  c:Jerry a c:Mouse ;
    c:smarterThan c:Tom .
  c:Spike a c:Dog ;
    c:smarterThan c:Jerry .`;

export const transitiveRule = `
  @prefix c: <${Example("").value}> .
  {
    ?x c:smarterThan ?y.
    ?y c:smarterThan ?z.
  } => {
    ?x c:smarterThan ?z.
  }.
`;
