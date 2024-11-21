import { assertEquals } from "https://deno.land/std@0.208.0/assert/mod.ts";
import { handler } from "../server.ts";

Deno.test("Server Routes", async (t) => {
  await t.step("root path returns welcome message", async () => {
    const reqUrl = "http://localhost:8000/";
    const req = new Request(reqUrl);
    const res = await handler(req);
    const text = await res.text();
    
    assertEquals(res.status, 200);
    assertEquals(
      text,
      "RDF Test Server - Try /data for the Tom & Jerry dataset"
    );
  });

  await t.step("data path returns turtle format", async () => {
    const req = new Request("http://localhost:8000/data");
    const res = await handler(req);
    const text = await res.text();
    
    assertEquals(res.status, 200);
    assertEquals(res.headers.get("content-type"), "text/turtle");
    // Basic check that we got some turtle data back
    assertEquals(text.includes("@prefix schema:"), true);
  });

  await t.step("unknown path returns 404", async () => {
    const req = new Request("http://localhost:8000/unknown");
    const res = await handler(req);
    
    assertEquals(res.status, 404);
    assertEquals(await res.text(), "Not Found");
  });
});
