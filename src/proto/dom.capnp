@0xd4e19674c5d5f0c9;

using Cxx = import "/capnp/c++.capnp";
$Cxx.namespace("bubble::dom");

interface DOMNode {
  # A capability provided by the client (browser) to the server
  # for manipulating a specific DOM node
  
  append @0 (html: Text) -> ();
  # Appends HTML content to this node
  
  prepend @1 (html: Text) -> ();
  # Prepends HTML content to this node
  
  replace @2 (html: Text) -> ();
  # Replaces this node's content with new HTML
}

interface DOMDocument {
  # Represents the browser's document
  
  createElement @0 (tag: Text) -> (node: DOMNode);
  # Creates a new DOM element with the given tag name
}

interface DOMSession {
  # The main interface that clients connect to
  
  subscribe @0 (id: Text, node: DOMNode) -> ();
  # Client provides a DOMNode capability for a specific DOM element ID
  
  unsubscribe @1 (id: Text) -> ();
  # Client removes the DOMNode capability for an ID
  
  getDocument @2 () -> (document: DOMDocument);
  # Gets the document capability for creating new elements
} 