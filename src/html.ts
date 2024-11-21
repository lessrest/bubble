import { Store, DataFactory } from "n3";
import { Term } from "@rdfjs/types";
import { RDF } from "./namespace.ts";

// HTML namespace constants
export const HTML = {
  element: DataFactory.namedNode("http://www.w3.org/1999/xhtml#element"),
  text: DataFactory.namedNode("http://www.w3.org/1999/xhtml#text"),
  tagName: DataFactory.namedNode("http://www.w3.org/1999/xhtml#tagName"),
  children: DataFactory.namedNode("http://www.w3.org/1999/xhtml#children"),
  content: DataFactory.namedNode("http://www.w3.org/1999/xhtml#content"),
  outerHTML: DataFactory.namedNode("http://www.w3.org/1999/xhtml#outerHTML"),
  attributes: DataFactory.namedNode("http://www.w3.org/1999/xhtml#attributes"),
  name: DataFactory.namedNode("http://www.w3.org/1999/xhtml#name"),
  value: DataFactory.namedNode("http://www.w3.org/1999/xhtml#value"),
};

interface HTMLNode {
  type: "element" | "text" | "list";
  tagName?: string;
  content?: string;
  children?: Term[];
}

function getNodeType(store: Store, subject: Term): HTMLNode {
  // Handle literal values directly
  if (subject.termType === "Literal") {
    return { type: "text", content: subject.value };
  }

  const isElement =
    store.getQuads(subject, RDF("type"), HTML.element, null).length > 0;
  const isText =
    store.getQuads(subject, RDF("type"), HTML.text, null).length > 0;

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
        (node.children ?? []).map((child) => renderHTML(store, child)),
      ).then((parts) => parts.join(""));

      // Get attributes if any exist
      const attributes = store.getObjects(subject, HTML.attributes, null)[0];
      let attrString = "";
      if (attributes) {
        const name = store.getObjects(attributes, HTML.name, null)[0]?.value;
        const value = store.getObjects(attributes, HTML.value, null)[0]?.value;
        if (name && value) {
          // For meta tags, name/content are the standard attributes
          if (node.tagName === "meta" && name === "viewport") {
            attrString = ` name="${name}" content="${value}"`;
          } else {
            attrString = ` ${name}="${value}"`;
          }
        }
      }

      // Handle self-closing tags
      const selfClosing = ["meta", "link", "br", "hr", "img", "input"];
      if (node.tagName && selfClosing.includes(node.tagName)) {
        return `<${node.tagName}${attrString}>`;
      }

      // Special case for document
      if (node.tagName === "html") {
        return `<!doctype html>\n<html>${innerHTML}</html>`;
      }

      return `<${node.tagName}${attrString}>${innerHTML}</${node.tagName}>`;
    }

    case "text":
      return node.content ?? "";

    case "list":
      return (await Promise.all(
        (node.children ?? []).map((child) => renderHTML(store, child)),
      )).join("");

    default:
      throw new Error(`Cannot render node type: ${(node as HTMLNode).type}`);
  }
}
