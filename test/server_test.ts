import { assertEquals } from "https://deno.land/std@0.208.0/assert/mod.ts";
import { handler } from "../server.ts";

Deno.test("Server Routes", async (t) => {

  await t.step("unknown path returns 404", async () => {
    const req = new Request("http://localhost:8000/unknown");
    const res = await handler(req);
    
    assertEquals(res.status, 404);
    assertEquals(await res.text(), "Not Found");
  });
});
