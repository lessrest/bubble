import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { parseRDF } from "./src/utils.ts";
import { tomAndJerry } from "./test/data.ts";
import N3 from "n3";
import { Schema } from "./src/namespace.ts";

async function handler(req: Request): Promise<Response> {
  const url = new URL(req.url);

  if (url.pathname === "/") {
    return new Response(
      "RDF Test Server - Try /data for the Tom & Jerry dataset",
    );
  }

  if (url.pathname === "/data") {
    const quads = await parseRDF(tomAndJerry);
    const writer = new N3.Writer({
      format: "text/turtle",
      prefixes: { schema: Schema("").value },
    });
    quads.forEach((quad) => writer.addQuad(quad));

    return new Promise((resolve) => {
      writer.end((error, result) => {
        resolve(
          new Response(result, {
            headers: { "content-type": "text/turtle" },
          }),
        );
      });
    });
  }

  return new Response("Not Found", { status: 404 });
}

console.log("Server running at http://localhost:8000");
await serve(handler, { port: 8000 });
