import { assertEquals } from "@std/assert";
import { handleWithRules } from "../src/utils.ts";

Deno.test("Rules-based Request Handler", async (t) => {
  await t.step("handles basic routing rule", async () => {
    const rules = `
      @prefix http: <http://www.w3.org/2011/http#>.
      @prefix string: <http://www.w3.org/2000/10/swap/string#>.

      {
        ?request http:path "/hello".
      } => {
        [] http:responseCode 200;
           http:body "Hello, World!".
      }.
    `;

    const req = new Request("http://localhost:8000/hello");
    const res = await handleWithRules(req, rules);
    
    assertEquals(res.status, 200);
    assertEquals(await res.text(), "Hello, World!");
  });

  await t.step("handles 404 for unmatched path", async () => {
    const rules = `
      @prefix http: <http://www.w3.org/2011/http#>.
      
      {
        ?request http:path "/specific-path".
      } => {
        [] http:responseCode 200;
           http:body "Found!".
      }.
    `;

    const req = new Request("http://localhost:8000/wrong-path");
    const res = await handleWithRules(req, rules);
    
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
        [] http:responseCode 200;
           http:body "API Request".
      }.
    `;

    const req = new Request("http://localhost:8000/api/users");
    const res = await handleWithRules(req, rules);
    
    assertEquals(res.status, 200);
    assertEquals(await res.text(), "API Request");
  });
});
