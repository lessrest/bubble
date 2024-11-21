import { assertEquals } from "@std/assert";
import { assertQuery, handleWithRules, withGroundFacts } from "./utils.ts";
import N3 from "n3";

Deno.test("Rules-based Request Handler", async (t) => {
  await t.step("handles basic routing rule", async () => {
    const rules = `
      @prefix http: <http://www.w3.org/2011/http#>.

      {
        ?request http:path "/hello".
      } => {
        ?response a http:Response;
          http:respondsTo ?request;
          http:responseCode 200;
          http:body "Hello, World!".
      }.
    `;

    const reqUrl = "http://localhost:8000/hello";
    const req = new Request(reqUrl);
    const res = await handleWithRules(req, [rules]);

    assertEquals(res.status, 200);
    assertEquals(await res.text(), "Hello, World!");
  });

  await t.step("handles 404 for unmatched path", async () => {
    const rules = `
      @prefix http: <http://www.w3.org/2011/http#>.
      
      {
        ?request http:path "/specific-path".
      } => {
        ?response a http:Response;
          http:respondsTo ?request;
          http:responseCode 200;
          http:body "Found!".
      }.
    `;

    const req = new Request("http://localhost:8000/wrong-path");
    const res = await handleWithRules(req, [rules]);

    assertEquals(res.status, 404);
  });

  await t.step("can use string matching in rules", async () => {
    const rules = `
      @prefix http: <http://www.w3.org/2011/http#>.
      @prefix string: <http://www.w3.org/2000/10/swap/string#>.

      {
        ?request http:path ?path.
        ?path string:startsWith "/api/".
      } => {
        ?response a http:Response;
          http:respondsTo ?request;
          http:responseCode 200;
          http:body "API Request".
      }.
    `;

    const req = new Request("http://localhost:8000/api/users");
    const res = await handleWithRules(req, [rules]);

    assertEquals(res.status, 200);
    assertEquals(await res.text(), "API Request");
  });

  await t.step("handles multiple possible responses", async () => {
    const rules = `
      @prefix http: <http://www.w3.org/2011/http#>.
      
      {
        ?request http:path "/multi".
      } => {
        ?response1 a http:Response;
          http:respondsTo ?request;
          http:responseCode 200;
          http:body "First response".

        ?response2 a http:Response;
          http:respondsTo ?request;
          http:responseCode 201;
          http:body "Second response".
      }.
    `;

    const req = new Request("http://localhost:8000/multi");
    const res = await handleWithRules(req, [rules]);

    // Should use the first matching response
    assertEquals(res.status, 200);
    assertEquals(await res.text(), "First response");
  });

  await t.step("handles missing response code", async () => {
    const rules = `
      @prefix http: <http://www.w3.org/2011/http#>.
      
      {
        ?request http:path "/incomplete".
      } => {
        ?response a http:Response;
          http:respondsTo ?request;
          http:body "Missing status code".
      }.
    `;

    const req = new Request("http://localhost:8000/incomplete");
    const res = await handleWithRules(req, [rules]);

    assertEquals(res.status, 500);
    assertEquals(await res.text(), "Response missing status code");
  });

  await t.step("handles missing response body", async () => {
    const rules = `
      @prefix http: <http://www.w3.org/2011/http#>.
      
      {
        ?request http:path "/nobody".
      } => {
        ?response a http:Response;
          http:respondsTo ?request;
          http:responseCode 204.
      }.
    `;

    const req = new Request("http://localhost:8000/nobody");
    const res = await handleWithRules(req, [rules]);

    assertEquals(res.status, 204);
    assertEquals(await res.text(), "");
  });

  await t.step("can use ground facts in rules", async () => {
    const rules = `
      @prefix http: <http://www.w3.org/2011/http#>.
      
      {
        ?request http:path "/nobody".
      } => {
        ?response a http:Response;
          http:respondsTo ?request;
          http:responseCode 204.
      }.
    `;

    const req = new Request("http://localhost:8000/nobody");
    const res = await handleWithRules(req, [rules]);

    assertEquals(res.status, 204);
    assertEquals(await res.text(), "");
  });

  await t.step("can use ground facts in rules", async () => {
    const facts = `
      @prefix ex: <http://example.org/> .
      ex:config ex:greeting "Hola!" .
    `;

    const rules = `
      @prefix http: <http://www.w3.org/2011/http#>.
      @prefix ex: <http://example.org/>.
      
      {
        ?request http:path "/greet".
        ?config ex:greeting ?msg.
      } => {
        ?response a http:Response;
          http:respondsTo ?request;
          http:responseCode 200;
          http:body ?msg.
      }.
    `;

    const req = new Request("http://localhost:8000/greet");
    const res = await handleWithRules(req, [rules], withGroundFacts(facts));

    assertEquals(res.status, 200);
    assertEquals(await res.text(), "Hola!");
  });

  await t.step("handles ActivityPub inbox POST", async () => {
    // Define initial graph with Alice's inbox collection
    const facts = `
      @base <http://example.org/>.
      @prefix ap: <http://www.w3.org/ns/activitystreams#>.
      @prefix ex: <http://example.org/>.
      
      ex:alice a ap:Person;
        ap:inbox </cap/alice-inbox-root>.

      </cap/alice-inbox-root> a ap:Collection.
    `;

    // Rule: POST to collection adds Note to items
    const rules = `
      @prefix http: <http://www.w3.org/2011/http#>.
      @prefix ap: <http://www.w3.org/ns/activitystreams#>.
      
      {
        ?request http:href ?collection ;
                http:method "POST" .
        
        ?collection a ap:Collection.
        ?object a ap:Note.
      } => {
        ?response a http:Response;
          http:respondsTo ?request;
          http:responseCode 201;
          http:body "Activity accepted".

        ?collection ap:items ?object.
      }.
    `;

    // POST a Note to Alice's inbox
    const req = new Request("http://example.org/cap/alice-inbox-root", {
      method: "POST",
      headers: {
        "Content-Type": "application/turtle",
      },
      body: `
        @prefix as: <http://www.w3.org/ns/activitystreams#>.
        @prefix ex: <http://example.org/>.

        <#body> a as:Note;
          as:content "Hello Alice!".
      `,
    });

    // Apply rules and verify Note was added
    const store = await withGroundFacts(facts);
    const resultStore = new N3.Store();
    const res = await handleWithRules(req, [rules], store, resultStore);

    assertEquals(res.status, 201);
    assertEquals(await res.text(), "Activity accepted");

    await assertQuery(
      resultStore,
      `{ <http://example.org/cap/alice-inbox-root> as:items ?object. }`,
      "the object was added to the collection",
    );
  });
});
