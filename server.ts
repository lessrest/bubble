import { handleWithRules, withGroundFacts } from "./src/utils.ts";

const store = await withGroundFacts(await Deno.readTextFile("./ground-facts.ttl"));
const rules = await Deno.readTextFile("./rules/inbox.n3");

export async function handler(req: Request): Promise<Response> {
  return handleWithRules(req, rules, store, store);
}

if (import.meta.main) {
  await Deno.serve({ port: 8000 }, handler);
}
