import { Quad } from "@rdfjs/types";

export interface Reasoner {
  reason(data: string, rules: string, options?: ReasonerOptions): Promise<string>;
}

export interface ReasonerOptions {
  output?: "deductive_closure";
}

export class WebAssemblyReasoner implements Reasoner {
  async reason(data: string, rules: string, options?: ReasonerOptions): Promise<string> {
    const { n3reasoner } = await import("eyereasoner");
    return n3reasoner(data + "\n" + rules, undefined, options);
  }
}

export class CommandLineReasoner implements Reasoner {
  async reason(data: string, rules: string, _options?: ReasonerOptions): Promise<string> {
    // Write data and rules to temporary files
    const dataFile = await Deno.makeTempFile({suffix: ".n3"});
    const rulesFile = await Deno.makeTempFile({suffix: ".n3"});
    
    await Deno.writeTextFile(dataFile, data);
    await Deno.writeTextFile(rulesFile, rules);

    try {
      // Run eye command
      const command = new Deno.Command("eye", {
        args: ["--nope", "--quiet", dataFile, rulesFile],
      });
      
      const { code, stdout, stderr } = await command.output();
      
      if (code !== 0) {
        throw new Error(`eye failed with code ${code}: ${new TextDecoder().decode(stderr)}`);
      }
      
      return new TextDecoder().decode(stdout);
    } finally {
      // Cleanup temp files
      await Deno.remove(dataFile);
      await Deno.remove(rulesFile);
    }
  }
}
