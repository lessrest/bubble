import { assertEquals } from "https://deno.land/std@0.208.0/assert/mod.ts";
import { handler } from "../server.ts";
import { assertQuery, parseRDF, withGroundFacts } from "./utils.ts";
import N3 from "n3";

async function emptyStore() {
  const store = await withGroundFacts(
    await Deno.readTextFile("./config.ttl"),
  );
  return store;
}

Deno.test("Server Routes", async (t) => {
  await t.step("unknown path returns 404", async () => {
    const req = new Request("http://localhost:8000/unknown");
    const res = await handler(req, await emptyStore());

    assertEquals(res.status, 404);
    assertEquals(await res.text(), "Not Found");
  });

  await t.step("GET to empty inbox returns 200", async () => {
    const req = new Request("http://localhost:8000/users/alice/inbox", {
      method: "GET",
    });
    const res = await handler(req, await emptyStore());

    assertEquals(res.status, 200);
    assertEquals(res.headers.get("Content-Type"), "application/turtle");

    const body = await res.text();
    console.log("BODY", body);
    const result = await parseRDF(body);
    const store = await emptyStore();
    await store.addQuads(result);

    await assertQuery(
      store,
      `
      { ?collection a as:Collection .        
      }
    `,
      "collection exists",
    );
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
    const res = await handler(req, await emptyStore());

    assertEquals(res.status, 201);
    assertEquals(await res.text(), "Activity accepted");
  });
});

Deno.test("GET inbox after POST shows new item", async (t) => {
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
  const store = await emptyStore();
  const res = await handler(req, store);

  assertEquals(res.status, 201);

  const req2 = new Request("http://localhost:8000/users/alice/inbox", {
    method: "GET",
  });
  const res2 = await handler(req2, store);

  assertEquals(res2.status, 200);
  const body = await res2.text();
  const result = await parseRDF(body);
  await store.addQuads(result);

  // await assertQuery(
  //   store,
  //   `
  //     { ?collection a as:Collection.
  //       ?collection as:items ?item .
  //     }
  //   `,
  //   "a collection with an item",
  // );
});
