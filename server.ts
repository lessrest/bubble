import { handleWithRules, withGroundFacts } from "./src/utils.ts";

const store = await withGroundFacts(
  await Deno.readTextFile("./ground-facts.ttl")
);

const inboxRules = await Deno.readTextFile("./rules/inbox.n3");
const htmlRules = await Deno.readTextFile("./rules/html.n3");

const rules = inboxRules + "\n" + htmlRules;

export function handler(req: Request): Promise<Response> {
  return handleWithRules(req, rules, store, store);
}

if (import.meta.main) {
  const controller = new AbortController();
  const server = Deno.serve({ port: 8000, signal: controller.signal }, handler);
  Deno.addSignalListener("SIGINT", () => {
    console.log("SIGINT received");
    controller.abort();
  });
  Deno.addSignalListener("SIGTERM", () => {
    console.log("SIGTERM received");
    controller.abort();
  });
  server.finished.then(() => {
    console.log("Server stopping...");
  });
}
