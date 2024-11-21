import { assertQuery } from "./utils.ts";
import { requestToStore } from "./request.ts";

Deno.test("HTTP Request to RDF", async (t) => {
  const request = new Request("http://example.com/api/users/123");
  const store = requestToStore(request);

  await t.step("converts URL path to RDF request", async (step) => {
    await assertQuery(
      store,
      `{
      ?request a http:Request;
        http:path "/api/users/123" .
    }`,
      step.name,
    );
  });

  await t.step(
    "can match request path prefix with string:startsWith",
    async (step) => {
      await assertQuery(
        store,
        `
    @prefix http: <http://www.w3.org/2011/http#> .
    @prefix string: <http://www.w3.org/2000/10/swap/string#> .
    
    {
      ?request a http:Request;
        http:path ?path .
      ?path string:startsWith "/api/" .
    }`,
        step.name,
      );
    },
  );

  await t.step(
    "can extract path components using string:scrape",
    async (step) => {
      await assertQuery(
        store,
        `
    @prefix http: <http://www.w3.org/2011/http#> .
    @prefix string: <http://www.w3.org/2000/10/swap/string#> .
    
    {
      ?request a http:Request;
        http:path ?path .
      (?path "/api/users/([^/]+)") string:scrape "123" .
    }`,
        step.name,
      );
    },
  );

  await t.step(
    "can split path using string:stringSplit",
    async (step) => {
      await assertQuery(
        store,
        `
    @prefix http: <http://www.w3.org/2011/http#> .
    @prefix string: <http://www.w3.org/2000/10/swap/string#> .
    @prefix e: <http://eulersharp.sourceforge.net/2003/03swap/log-rules#>.
    
    {
      ?request a http:Request;
        http:path ?path .
      
      # Split the path on "/" character
      (?path "/") e:stringSplit ("api" "users" "123") .
    }`,
        step.name,
      );
    },
  );
});
