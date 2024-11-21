import { assertEquals } from "@std/assert";
import { handleWithRules, withGroundFacts } from "../src/utils.ts";
import { renderHTML } from "../src/utils.ts";
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

  await t.step("renders primitive DOM model", () => {
    const store = new N3.Store();
    const doc = DataFactory.blankNode();
    const html = DataFactory.blankNode();
    const head = DataFactory.blankNode();
    const title = DataFactory.blankNode();
    const body = DataFactory.blankNode();
    const p = DataFactory.blankNode();

    store.addQuad(
      doc,
      DataFactory.namedNode("http://www.w3.org/1999/xhtml#documentElement"),
      html
    );

    store.addQuad(
      html,
      DataFactory.namedNode("http://www.w3.org/1999/xhtml#tagName"),
      DataFactory.literal("html")
    );

    store.addQuad(
      html,
      DataFactory.namedNode("http://www.w3.org/1999/xhtml#head"),
      head
    );

    store.addQuad(
      head,
      DataFactory.namedNode("http://www.w3.org/1999/xhtml#tagName"),
      DataFactory.literal("head")
    );

    store.addQuad(
      head,
      DataFactory.namedNode("http://www.w3.org/1999/xhtml#child"),
      title
    );

    store.addQuad(
      title,
      DataFactory.namedNode("http://www.w3.org/1999/xhtml#tagName"),
      DataFactory.literal("title")
    );

    store.addQuad(
      title,
      DataFactory.namedNode("http://www.w3.org/1999/xhtml#textContent"),
      DataFactory.literal("Test Page")
    );

    store.addQuad(
      html,
      DataFactory.namedNode("http://www.w3.org/1999/xhtml#body"),
      body
    );

    store.addQuad(
      body,
      DataFactory.namedNode("http://www.w3.org/1999/xhtml#tagName"),
      DataFactory.literal("body")
    );

    store.addQuad(
      body,
      DataFactory.namedNode("http://www.w3.org/1999/xhtml#child"),
      p
    );

    store.addQuad(
      p,
      DataFactory.namedNode("http://www.w3.org/1999/xhtml#tagName"),
      DataFactory.literal("p")
    );

    store.addQuad(
      p,
      DataFactory.namedNode("http://www.w3.org/1999/xhtml#textContent"),
      DataFactory.literal("Hello World")
    );

    const html_output = renderHTML(store, doc);
    assertEquals(
      html_output,
      `<!DOCTYPE html>
<html><head><title>Test Page</title></head><body><p>Hello World</p></body></html>`
    );
  });
});
