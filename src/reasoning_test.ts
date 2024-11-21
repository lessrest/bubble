import { assertEquals } from "@std/assert";
import { CommandLineReasoner } from "./reasoning.ts";

const TEST_DATA = `
@prefix : <http://example.org/>.
:alice :knows :bob.
:bob :knows :charlie.
`;

const TEST_RULES = `
@prefix : <http://example.org/>.
{
  ?x :knows ?y.
  ?y :knows ?z.
} => {
  ?x :knows ?z.
}.
`;

Deno.test("CommandLine Reasoner", async (t) => {
  const reasoner = new CommandLineReasoner();

  await t.step("applies transitive rules", async () => {
    const result = await reasoner.reason([TEST_DATA, TEST_RULES]);
    console.log("*** RESULT ***");
    console.log(result);
    assertTrue(
      result.includes(
        ":alice :knows :bob",
      ),
    );
  });
});

function assertTrue(condition: boolean) {
  assertEquals(condition, true);
}
