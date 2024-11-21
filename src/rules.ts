import { Quad } from "@rdfjs/types";
import N3 from "n3";
import { CommandLineReasoner } from "./reasoning.ts";
import { writeN3 } from "./utils.ts";

export async function applyRules(
  data: Quad[],
  rules: string,
): Promise<N3.Store> {
  const store = new N3.Store();
  store.addQuads(data);

  const n3Data = await writeN3(data);
  const reasoner = new CommandLineReasoner();
  const result = await reasoner.reason(n3Data, rules);

  const parser = new N3.Parser({ format: "text/n3" });
  const resultQuads = parser.parse(result) as Quad[];
  store.addQuads(resultQuads);

  return store;
}
