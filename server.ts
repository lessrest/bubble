import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { parseRDF } from "./test/utils.ts";
import { tomAndJerry } from "./test/data.ts";

async function handler(req: Request): Promise<Response> {
  const url = new URL(req.url);
  
  if (url.pathname === "/") {
    return new Response("RDF Test Server - Try /data for the Tom & Jerry dataset");
  }
  
  if (url.pathname === "/data") {
    const quads = await parseRDF(tomAndJerry);
    return new Response(JSON.stringify(quads, null, 2), {
      headers: { "content-type": "application/json" },
    });
  }

  return new Response("Not Found", { status: 404 });
}

console.log("Server running at http://localhost:8000");
await serve(handler, { port: 8000 });
