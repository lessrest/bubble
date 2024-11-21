import { assertEquals } from "@std/assert";
import { Quad, Term } from "@rdfjs/types";
import N3, { DataFactory } from "n3";
import { CommandLineReasoner } from "./reasoning.ts";
import { ACTIVITY_STREAMS, EXAMPLE, HTTP, RDF, Schema } from "./namespace.ts";
import { Store } from "n3";

export async function parseRDF(input: string): Promise<Quad[]> {
  const parser = new N3.Parser();
  return parser.parse(input);
}

export function writeN3(quads: Quad[]): Promise<string> {
  const writer = new N3.Writer({
    format: "text/n3",
    prefixes: {
      schema: Schema("").value,
      http: HTTP("").value,
      ex: EXAMPLE("").value,
      as: ACTIVITY_STREAMS("").value,
    },
  });

  for (const quad of quads) {
    writer.addQuad(quad);
  }

  return new Promise<string>((resolve, reject) => {
    writer.end((error: Error | null, result: string) =>
      error ? reject(error) : resolve(result)
    );
  });
}

export async function applyRules(
  data: Quad[],
  rules: string,
): Promise<N3.Store> {
  const store = new N3.Store();
  store.addQuads(data);

  const n3Data = await writeN3(data);
  const reasoner = new CommandLineReasoner();
  const result = await reasoner.reason(n3Data, rules);

  const parser = new N3.Parser({ format: "text/n3" });
  const resultQuads = parser.parse(result) as Quad[];
  store.addQuads(resultQuads);

  return store;
}

export function assertTriple(
  store: Store,
  subject: Term,
  predicate: Term,
  object: Term,
): void {
  const matches = store.getQuads(subject, predicate, object, null);
  assertEquals(
    matches.length,
    1,
    `Expected triple: <${subject.value}> <${predicate.value}> <${object.value}>`,
  );
}

export function assertTriples(
  store: Store,
  triples: [Term, Term, Term][],
): void {
  for (const [subject, predicate, object] of triples) {
    assertTriple(store, subject, predicate, object);
  }
}

function getStandardPrefixes(): string {
  return `
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix schema: <http://schema.org/> .
@prefix http: <http://www.w3.org/2011/http#> .
@prefix string: <http://www.w3.org/2000/10/swap/string#> .
@prefix e: <http://eulersharp.sourceforge.net/2003/03swap/log-rules#> .
@prefix as: <http://www.w3.org/ns/activitystreams#> .
`;
}

export async function assertQuery(
  store: Store,
  query: string,
  message: string,
): Promise<void> {
  const fullQuery = `
      ${getStandardPrefixes()}
      @prefix test: <http://example.org/test#> .
      
      ${query}
      => {
        [] a test:Success;
          test:message "${message}" .
      }.
    `;

  await assertN3Query(store, fullQuery, message);
}

export async function assertN3Query(
  store: Store,
  query: string,
  expectedMessage: string,
): Promise<void> {
  const reasoner = new CommandLineReasoner();
  const result = await reasoner.reason(
    await writeN3(store.getQuads()),
    "",
    { query },
  );
  const resultStore = new N3.Store();
  const parser = new N3.Parser({ format: "text/n3" });
  const resultQuads = parser.parse(result);
  resultStore.addQuads(resultQuads);

  const successQuads = resultStore.getQuads(
    null,
    DataFactory.namedNode("http://example.org/test#message"),
    DataFactory.literal(expectedMessage),
    null,
  );

  assertEquals(
    successQuads.length > 0,
    true,
    `N3 query failed to match expected pattern.
Actual graph contents:

${await writeN3(
      store.getQuads(),
    )}`,
  );
}

export async function requestToStore(
  request: Request,
  requestIri: string,
): Promise<Store> {
  const store = new N3.Store();
  const url = new URL(request.url);

  const requestNode = DataFactory.namedNode(requestIri);

  // Add basic request triples
  store.addQuad(
    requestNode,
    DataFactory.namedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
    DataFactory.namedNode("http://www.w3.org/2011/http#Request"),
  );

  // Add path
  store.addQuad(
    requestNode,
    DataFactory.namedNode("http://www.w3.org/2011/http#path"),
    DataFactory.literal(url.pathname),
  );

  // Add href
  store.addQuad(
    requestNode,
    DataFactory.namedNode("http://www.w3.org/2011/http#href"),
    DataFactory.namedNode(url.href),
  );

  // Add method
  store.addQuad(
    requestNode,
    DataFactory.namedNode("http://www.w3.org/2011/http#method"),
    DataFactory.literal(request.method),
  );

  // // Add body
  // store.addQuad(
  //   requestNode,
  //   DataFactory.namedNode("http://www.w3.org/2011/http#body"),
  //   DataFactory.literal(await request.text()),
  // );

  // Add content type
  store.addQuad(
    requestNode,
    DataFactory.namedNode("http://www.w3.org/2011/http#contentType"),
    DataFactory.literal(request.headers.get("Content-Type") ?? ""),
  );

  // Check if content type is Turtle
  if (request.headers.get("Content-Type")?.includes("turtle")) {
    const source = await request.text();
    const parser = new N3.Parser({ baseIRI: requestNode.value });
    const quads = parser.parse(source);
    store.addQuads(quads);

    store.addQuad(
      requestNode,
      DataFactory.namedNode("http://www.w3.org/2011/http#body"),
      DataFactory.namedNode(requestNode.value + "#body"),
    );
  }

  return store;
}

export function withGroundFacts(facts: string): Store {
  const store = new N3.Store();
  const parser = new N3.Parser();
  store.addQuads(parser.parse(facts));
  return store;
}

// HTML namespace constants
const HTML = {
  element: DataFactory.namedNode("http://www.w3.org/1999/xhtml#element"),
  text: DataFactory.namedNode("http://www.w3.org/1999/xhtml#text"),
  tagName: DataFactory.namedNode("http://www.w3.org/1999/xhtml#tagName"),
  children: DataFactory.namedNode("http://www.w3.org/1999/xhtml#children"),
  content: DataFactory.namedNode("http://www.w3.org/1999/xhtml#content"),
  outerHTML: DataFactory.namedNode("http://www.w3.org/1999/xhtml#outerHTML"),
};

interface HTMLNode {
  type: "element" | "text" | "list";
  tagName?: string;
  content?: string;
  children?: Term[];
}

function getNodeType(store: Store, subject: Term): HTMLNode {
  const isElement = store.getQuads(subject, RDF("type"), HTML.element, null).length > 0;
  const isText = store.getQuads(subject, RDF("type"), HTML.text, null).length > 0;

  if (isElement) {
    const tagName = store.getObjects(subject, HTML.tagName, null)[0]?.value;
    if (!tagName) throw new Error("HTML element missing tagName");

    const childrenList = store.getObjects(subject, HTML.children, null)[0];
    const children = childrenList ? getRDFList(store, childrenList) : [];

    return { type: "element", tagName, children };
  }

  if (isText) {
    const content = store.getObjects(subject, HTML.content, null)[0]?.value ?? "";
    return { type: "text", content };
  }

  // Check for direct outerHTML
  const outerHTML = store.getObjects(subject, HTML.outerHTML, null)[0]?.value;
  if (outerHTML) {
    return { type: "text", content: outerHTML };
  }

  // Handle rdf:nil
  if (subject.value === RDF("nil").value) {
    return { type: "list", children: [] };
  }

  // Handle list nodes
  const first = store.getObjects(subject, RDF("first"), null)[0];
  const rest = store.getObjects(subject, RDF("rest"), null)[0];
  if (first && rest) {
    return { type: "list", children: [first, ...getRDFList(store, rest)] };
  }

  throw new Error(`Unknown HTML node type for: ${subject.value}`);
}

function getRDFList(store: Store, listNode: Term): Term[] {
  const node = getNodeType(store, listNode);
  return node.type === "list" && node.children ? node.children : [];
}

export async function renderHTML(store: Store, subject: Term): Promise<string> {
  const node = getNodeType(store, subject);

  switch (node.type) {
    case "element": {
      const innerHTML = await Promise.all(
        (node.children ?? []).map(child => renderHTML(store, child))
      ).then(parts => parts.join(""));

      // Get attributes if any exist
      const attributes = store.getObjects(subject, HTML.attributes, null)[0];
      let attrString = "";
      if (attributes) {
        const name = store.getObjects(attributes, HTML.name, null)[0]?.value;
        const value = store.getObjects(attributes, HTML.value, null)[0]?.value;
        if (name && value) {
          attrString = ` ${name}="${value}"`;
        }
      }

      // Special case for document
      if (node.tagName === "html") {
        return `<!doctype html>\n${innerHTML}`;
      }

      return `<${node.tagName}${attrString}>${innerHTML}</${node.tagName}>`;
    }

    case "text":
      return node.content ?? "";

    case "list":
      return (await Promise.all(
        (node.children ?? []).map(child => renderHTML(store, child))
      )).join("");

    default:
      throw new Error(`Cannot render node type: ${(node as HTMLNode).type}`);
  }
}

export async function handleWithRules(
  request: Request,
  rules: string,
  groundFacts?: Store,
  resultStore?: Store,
): Promise<Response> {
  // Convert request to RDF store
  // Use request URL as the IRI
  const uuid = crypto.randomUUID();
  const requestIri = `urn:request:${uuid}`;
  const store = await requestToStore(request, requestIri);

  // Add ground facts if provided
  if (groundFacts) {
    store.addQuads(groundFacts.getQuads());
  }

  // Apply the rules
  const reasoner = new CommandLineReasoner();
  const n3Input = await writeN3(store.getQuads());
  const result = await reasoner.reason(n3Input, rules);
  // Parse the results
  if (!resultStore) {
    resultStore = new N3.Store();
  }

  const parser = new N3.Parser({ format: "text/n3" });

  const resultQuads = parser.parse(result) as Quad[];

  resultStore.addQuads(resultQuads);

  // Find request node
  const requestQuads = resultStore.getQuads(
    DataFactory.namedNode(requestIri),
    DataFactory.namedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
    DataFactory.namedNode("http://www.w3.org/2011/http#Request"),
    null,
  );

  if (requestQuads.length === 0) {
    return new Response("Request not found in result", { status: 500 });
  }

  // Look for response that responds to this request
  const responseQuads = resultStore.getQuads(
    null,
    DataFactory.namedNode("http://www.w3.org/2011/http#respondsTo"),
    requestQuads[0].subject,
    null,
  );

  if (responseQuads.length === 0) {
    return new Response("Not Found", { status: 404 });
  }

  // Get status code for the response
  const statusQuads = resultStore.getQuads(
    responseQuads[0].subject,
    DataFactory.namedNode("http://www.w3.org/2011/http#responseCode"),
    null,
    null,
  );

  if (statusQuads.length === 0) {
    return new Response("Response missing status code", { status: 500 });
  }

  const statusCode = parseInt(statusQuads[0].object.value);

  // Get response body
  const bodyQuads = resultStore.getQuads(
    responseQuads[0].subject,
    DataFactory.namedNode("http://www.w3.org/2011/http#body"),
    null,
    null,
  );

  let body: string | null = null;

  if (bodyQuads.length > 0) {
    const bodyStore = new N3.Store();

    for (const bodyQuad of bodyQuads) {
      if (bodyQuad.object.termType === "Quad") {
        bodyStore.addQuad(bodyQuad.object);
      } else if (bodyQuad.object.termType === "Literal") {
        // For literals, concatenate their values
        body = (body ?? "") + bodyQuad.object.value;
      } else if (
        bodyQuad.object.termType === "BlankNode" ||
        bodyQuad.object.termType === "NamedNode"
      ) {
        // Check if this is an HTML page
        const isHtmlPage = resultStore.getQuads(
          bodyQuad.object,
          DataFactory.namedNode(
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
          ),
          DataFactory.namedNode("http://www.w3.org/1999/xhtml#element"),
          null,
        ).length > 0;

        if (isHtmlPage) {
          console.log(
            `Before rendering HTML: ${await writeN3(resultStore.getQuads())}`,
          );
          body = await renderHTML(resultStore, bodyQuad.object);
        } else {
          const graphId = bodyQuad.object.termType === "BlankNode"
            ? `_:${bodyQuad.object.value}`
            : bodyQuad.object.value;
          const subgraph = resultStore.getQuads(
            null,
            null,
            null,
            graphId,
          ) as Quad[];
          for (const quad of subgraph) {
            bodyStore.addQuad(quad.subject, quad.predicate, quad.object);
          }
        }
      } else {
        console.log(
          await writeN3(resultQuads),
        );
        throw new Error(`Unsupported body type: ${bodyQuad.object.termType}`);
      }
    }

    // If we collected any quads, serialize them
    if (bodyStore.size > 0) {
      body = (body ?? "") + await writeN3(bodyStore.getQuads());
    }
  }

  // Content-Type
  const contentTypeQuads = resultStore.getQuads(
    responseQuads[0].subject,
    DataFactory.namedNode("http://www.w3.org/2011/http#contentType"),
    null,
    null,
  );

  const contentType = contentTypeQuads.length > 0
    ? contentTypeQuads[0].object.value
    : "text/plain";

  return new Response(body, {
    status: statusCode,
    headers: { "Content-Type": contentType },
  });
}
