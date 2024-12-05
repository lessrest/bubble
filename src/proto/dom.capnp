@0x96e09069c4cb9a01;

enum InsertPosition {
  beforeBegin @0;  # Before the element itself
  afterBegin @1;   # Just inside the element, before its first child
  beforeEnd @2;    # Just inside the element, after its last child
  afterEnd @3;     # After the element itself
}

interface DOMNode {
  # Base interface for all DOM nodes
  
  insertAdjacent @0 (position: InsertPosition, node: DOMNode) -> ();
  # Inserts a node in a specified position relative to this node
}

interface DOMElement extends(DOMNode) {
  # Interface for element nodes

  setAttribute @0 (name: Text, value: Text) -> ();
  # Sets the value of an attribute on this element
}

interface DOMText extends(DOMNode) {
  # Interface for text nodes

  setText @0 (text: Text) -> ();
  # Sets the text content of this node
}

interface DOMDocument {
  # Represents the browser's document
  
  createElement @0 (tag: Text) -> (node: DOMElement);
  # Creates a new DOM element with the given tag name

  createTextNode @1 (data: Text) -> (node: DOMText);
  # Creates a new text node with the given text content
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