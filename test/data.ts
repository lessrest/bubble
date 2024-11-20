export const RDF = {
  type: "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
  cartoons: "http://example.org/cartoons#"
};

export const tomAndJerry = `PREFIX c: <${RDF.cartoons}>
  c:Tom a c:Cat .
  c:Jerry a c:Mouse ;
    c:smarterThan c:Tom .
  c:Spike a c:Dog ;
    c:smarterThan c:Jerry .`;

export const transitiveRule = `
  @prefix c: <${RDF.cartoons}> .
  {
    ?x c:smarterThan ?y.
    ?y c:smarterThan ?z.
  } => {
    ?x c:smarterThan ?z.
  }.
`;
