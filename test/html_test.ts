import { assertEquals } from "@std/assert";
import { handleWithRules, withGroundFacts } from "../src/utils.ts";

Deno.test("HTML Endpoints", async (t) => {
  const facts = `
    @prefix schema: <http://schema.org/>.
    </> schema:name "Test Site";
        schema:description "A test website".
  `;

  await t.step("server root returns HTML homepage", async () => {
    const req = new Request("http://localhost:8000/");
    const res = await handleWithRules(req, await Deno.readTextFile("./rules/html.n3"), withGroundFacts(facts));

    assertEquals(res.status, 200);
    assertEquals(res.headers.get("Content-Type"), "text/html");
    
    const body = await res.text();
    assertEquals(
      body.includes("<title>Test Site</title>"),
      true,
      "Homepage should include site title"
    );
    assertEquals(
      body.includes("<p>A test website</p>"),
      true,
      "Homepage should include site description"
    );
  });
});
