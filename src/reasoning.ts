import { Quad } from "@rdfjs/types";

export interface Reasoner {
  reason(
    data: string,
    rules: string,
    options?: ReasonerOptions,
  ): Promise<string>;
}

export interface ReasonerOptions {
  query?: string;
}

export class WebAssemblyReasoner implements Reasoner {
  async reason(
    data: string,
    rules: string,
    options?: ReasonerOptions,
  ): Promise<string> {
    const { n3reasoner } = await import("eyereasoner");
    const query = options?.query;
    return n3reasoner(data + "\n" + rules, query, options);
  }
}

export class CommandLineReasoner implements Reasoner {
  async reason(
    data: string,
    rules: string,
    options?: ReasonerOptions,
  ): Promise<string> {
    // Write data and rules to temporary files
    const dataFile = await Deno.makeTempFile({ suffix: ".n3" });
    const rulesFile = await Deno.makeTempFile({ suffix: ".n3" });
    const queryFile = await Deno.makeTempFile({ suffix: ".n3" });

    await Deno.writeTextFile(dataFile, data);
    await Deno.writeTextFile(rulesFile, rules);
    if (options?.query) {
      await Deno.writeTextFile(queryFile, options.query);
    }

    // console.log("DATA", data);
    // console.log("RULES", rules);
    // console.log("QUERY", options?.query);

    try {
      // Run eye command
      const command = new Deno.Command("swipl", {
        args: [
          "-q",
          "-f",
          "/opt/eye/src/eye/eye.pl",
          "-g",
          "main",
          "--",
          "--pass",
          "--no-numerals",
          // "--no-qnames",
          "--no-qvars",
          // "--rdf-list-output",
          "--quiet",
          "--nope",
          dataFile,
          rulesFile,
          ...(options?.query ? ["--query", queryFile] : []),
        ],
      });

      const { code, stdout, stderr } = await command.output();

      if (code !== 0) {
        throw new Error(
          `eye failed with code ${code}: ${new TextDecoder().decode(stderr)}`,
        );
      }

      const result = new TextDecoder().decode(stdout);
      //console.log("RESULT", result);
      return result;
    } finally {
      // Cleanup temp files
      await Deno.remove(dataFile);
      await Deno.remove(rulesFile);
    }
  }
}
