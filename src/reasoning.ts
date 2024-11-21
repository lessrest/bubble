import { Quad } from "@rdfjs/types";

export interface Reasoner {
  reason(
    inputs: string[],
    options?: ReasonerOptions,
  ): Promise<string>;
}

export interface ReasonerOptions {
  query?: string;
}

export class WebAssemblyReasoner implements Reasoner {
  async reason(
    inputs: string[],
    options?: ReasonerOptions,
  ): Promise<string> {
    const { n3reasoner } = await import("eyereasoner");
    const query = options?.query;
    return n3reasoner(inputs.join("\n"), query, options);
  }
}

export class CommandLineReasoner implements Reasoner {
  async reason(
    inputs: string[],
    options?: ReasonerOptions,
  ): Promise<string> {
    const queryFile = await Deno.makeTempFile({ suffix: ".n3" });

    const inputFiles = await Promise.all(inputs.map(async (input) => {
      const file = await Deno.makeTempFile({ suffix: ".n3" });
      await Deno.writeTextFile(file, input);
      return file;
    }));

    if (options?.query) {
      await Deno.writeTextFile(queryFile, options.query);
    }

    // console.log("DATA", data);
    // console.log("RULES", rules);
    // console.log("QUERY", options?.query);

    try {
      // Run eye command
      const command = new Deno.Command("eye", {
        args: [
          // "-q",
          // "-f",
          // "/opt/eye/src/eye/eye.pl",
          // "-g",
          // "main",
          // "--",
          "--pass",
          //          "--no-bnode-relabeling",
          // "--no-numerals",
          // "--no-qnames",
          "--no-qvars",
          // "--no-ucall",
          // "--rdf-list-output",
          "--quiet",
          "--nope",
          "--quantify",
          `foo`,
          "--debug",
          //"--no-bnode-relabeling",
          ...inputFiles,
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
      console.log("*** RESULT ***");
      console.log(result);
      return result;
    } finally {
      // don't clean up
      console.log("*** NOT CLEANING UP ***");
      console.log(inputFiles);
      console.log(queryFile);
    }
  }
}
