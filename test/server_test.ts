import { assertEquals } from "https://deno.land/std@0.208.0/assert/mod.ts";
import { handler } from "../server.ts";
import { assertQuery, parseRDF } from "../src/utils.ts";
import N3 from "n3";

Deno.test("Server Routes", async (t) => {
  await t.step("unknown path returns 404", async () => {
    const req = new Request("http://localhost:8000/unknown");
    const res = await handler(req);

    assertEquals(res.status, 404);
    assertEquals(await res.text(), "Not Found");
  });

  await t.step("POST note to inbox", async () => {
    const req = new Request("http://localhost:8000/users/alice/inbox", {
      method: "POST",
      headers: {
        "Content-Type": "application/turtle",
      },
      body: `
        @prefix as: <http://www.w3.org/ns/activitystreams#>.
        
        <#body> a as:Note;
          as:content "Hello Alice!".
      `,
    });
    const res = await handler(req);

    assertEquals(res.status, 201);
    assertEquals(await res.text(), "Activity accepted");
  });

  await t.step("GET to inbox returns 200", async () => {
    const req = new Request("http://localhost:8000/users/alice/inbox", {
      method: "GET",
    });
    const res = await handler(req);

    assertEquals(res.status, 200);
    assertEquals(res.headers.get("Content-Type"), "application/turtle");

    const body = await res.text();
    const result = await parseRDF(body);
    const store = new N3.Store();
    await store.addQuads(result);

    await assertQuery(
      store,
      `
      { ?collection a as:Collection. 
        ?collection rdfs:label "Inbox" .
      }
    `,
      "a collection labeled 'Inbox'",
    );
  });
});
