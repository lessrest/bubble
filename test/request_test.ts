import { assertHttpRequest } from "./utils.ts";
import { requestToStore } from "./request.ts";

Deno.test("HTTP Request to RDF", async (t) => {
  await t.step("converts URL path to RDF request", async () => {
    const request = new Request("http://example.com/api/users/123");
    const store = requestToStore(request);
    await assertHttpRequest(store, "/api/users/123", "Found expected HTTP request");
  });
});
