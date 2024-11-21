import { assertEquals } from "@std/assert";
import { handleWithRules, withGroundFacts } from "./utils.ts";
import { renderHTML } from "./html.ts";
import N3 from "n3";
const { DataFactory } = N3;

Deno.test("HTML Endpoints", async (t) => {
  const facts = `
    @prefix schema: <http://schema.org/>.
    </> schema:name "Test Site";
        schema:description "A test website".
  `;

  await t.step("server root returns HTML homepage", async () => {
    const req = new Request("http://localhost:8000/");
    const res = await handleWithRules(
      req,
      await Deno.readTextFile("./rules/html.n3"),
      withGroundFacts(facts),
    );

    assertEquals(res.status, 200);
    assertEquals(res.headers.get("Content-Type"), "text/html");

    const body = await res.text();
    assertEquals(
      body,
      `<!doctype html>
<html><title>Test Site</title><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><body><p>A test website</p></body></html>`,
      "Homepage should include site title and metadata",
    );
  });

  await t.step("renders HTML from outerHTML property", async () => {
    const store = new N3.Store();
    const doc = DataFactory.blankNode();

    store.addQuad(
      doc,
      DataFactory.namedNode("http://www.w3.org/1999/xhtml#outerHTML"),
      DataFactory.literal(
        "<html><head><title>Test Page</title></head><body><p>Hello World</p></body></html>",
      ),
    );

    const html_output = await renderHTML(store, doc);
    assertEquals(
      html_output,
      `<html><head><title>Test Page</title></head><body><p>Hello World</p></body></html>`,
    );
  });
});
