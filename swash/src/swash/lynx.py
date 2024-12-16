from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Literal, Union, Dict
from xml.etree.ElementTree import Element as HTMLElement

import rich
from rich.console import Console, ConsoleRenderable, Group
from rich.text import Text
from rich.padding import Padding
from rich.columns import Columns
from rich.panel import Panel
from rich import box, inspect
from rich.align import Align

from structlog import get_logger

logger = get_logger()

#
# STEP 1: Parse HTML into a logical Node tree
#


@dataclass
class TextNode:
    text: str


@dataclass
class ElementNode:
    tag: str
    attributes: Dict[str, str]
    children: List[Node] = field(default_factory=list)


Node = Union[TextNode, ElementNode]


def to_node(element: HTMLElement) -> Node:
    """Convert an HTMLElement or plain text into a Node tree with all text extracted as TextNodes."""

    # Extract text node if element.text is non-empty
    nodes: List[Node] = []
    if element.text and element.text.strip():
        nodes.append(TextNode(element.text))

    # Convert children
    for child in element:
        nodes.append(to_node(child))
        # Tail text
        if child.tail and child.tail.strip():
            nodes.append(TextNode(child.tail))
    return ElementNode(element.tag, dict(element.attrib), nodes)


#
# STEP 2: Stylesheet and Style Computation
#
@dataclass
class Style:
    display: Optional[Literal["block", "flex", "inline"]] = None
    flex_direction: Optional[Literal["row", "column"]] = None
    gap: tuple[int, int] = (0, 0)
    padding: tuple[int, int, int, int] = (0, 0, 0, 0)
    is_link: bool = False
    is_bold: bool = False
    list_style: Optional[str] = None
    panel: bool = False
    text_color: Optional[str] = None
    small_caps: bool = False
    border: bool = False
    justify: Optional[Literal["between"]] = None


@dataclass
class StyleSheet:
    unknown_classes: set[str] = field(default_factory=set)

    TAG_DEFAULTS: Dict[str, Style] = field(
        default_factory=lambda: {
            "div": Style(display="block"),
            "span": Style(display="inline"),
            "a": Style(display="inline", is_link=True, text_color="blue"),
            "button": Style(display="inline", is_bold=True),
            "ul": Style(
                display="flex", flex_direction="column", list_style="bullet"
            ),
            "dl": Style(display="flex", flex_direction="column"),
            "details": Style(display="flex", flex_direction="column"),
            "summary": Style(display="inline", is_bold=True),
            "li": Style(display="flex", flex_direction="row"),
        }
    )

    CLASS_OVERRIDES: Dict[str, Style] = field(
        default_factory=lambda: {
            "flex": Style(display="flex"),
            "flex-row": Style(display="flex", flex_direction="row"),
            "flex-col": Style(display="flex", flex_direction="column"),
            "flex-wrap": Style(display="flex", flex_direction="column"),
            "font-bold": Style(is_bold=True),
            "link": Style(is_link=True, text_color="blue"),
            "gap-1": Style(gap=(1, 1)),
            "gap-2": Style(gap=(1, 1)),
            "gap-y-2": Style(gap=(1, 0)),
            "gap-x-6": Style(gap=(0, 2)),
            "small-caps": Style(small_caps=True),
            "pl-1": Style(padding=(0, 0, 0, 1)),
            "px-2": Style(padding=(0, 2, 0, 2)),
            "py-2": Style(padding=(2, 0, 2, 0)),
            "border": Style(border=True),
            "justify-between": Style(justify="between"),
            # ...
        }
    )

    def compute_style(self, tag: str, attributes: Dict[str, str]) -> Style:
        base = self.TAG_DEFAULTS.get(tag, Style())
        # Make a copy
        final_style = Style(**vars(base))

        classes = attributes.get("class", "")
        for c in classes.split():
            c = c.strip()
            if c and c in self.CLASS_OVERRIDES:
                ov = self.CLASS_OVERRIDES[c]
                for field_name in vars(ov):
                    val = getattr(ov, field_name)
                    if val is not None and val != (
                        0,
                        0,
                        0,
                        0,
                    ):  # for tuples
                        setattr(final_style, field_name, val)
            elif c:
                self.unknown_classes.add(c)
        return final_style


#
# STEP 2b: Convert Node tree to Box tree
#
# The Box tree explicitly encodes styling and layout decisions. Here we apply the computed style.
# We also handle semantic transformations, such as inserting bullet points for list items or
# indenting children.


@dataclass
class BoxTextNode:
    style: Style
    text: str


@dataclass
class BoxContainerNode:
    style: Style
    children: List[BoxNode] = field(default_factory=list)


BoxNode = Union[BoxTextNode, BoxContainerNode]


def node_to_box(
    node: Node, stylesheet: StyleSheet, parent_style: Optional[Style] = None
) -> BoxNode:
    if isinstance(node, TextNode):
        # Use parent style if available, otherwise default style
        style = parent_style or Style(display="inline")
        return BoxTextNode(style=style, text=node.text)

    # Element node:
    style = stylesheet.compute_style(node.tag, node.attributes)

    # Merge with parent style for inheritance
    if parent_style:
        # Inherit certain properties from parent
        if not style.text_color:
            style.text_color = parent_style.text_color
        if not style.is_bold:
            style.is_bold = parent_style.is_bold

    # Compute children box nodes with current style
    box_children = [
        node_to_box(ch, stylesheet, style) for ch in node.children
    ]

    # Handle special semantics: like bullet for list items (ul/li)
    if style.list_style == "bullet":
        # If this node is <ul>, children might be <li>. For each li child,
        # we can prepend a bullet text node with indentation. Actually, let's
        # handle this in the final rendering step or transform <li> node children here.
        # Instead, let's say for each BoxContainerNode child that corresponds to <li>,
        # we do an internal transform:
        if node.tag == "ul":
            # For each child that is a BoxContainerNode (representing <li>),
            # prepend a bullet as a text node:
            transformed_children = []
            for ch in box_children:
                # Prepend bullet node
                bullet_node = BoxTextNode(
                    style=Style(display="inline", is_bold=True), text="• "
                )
                # Create a container for li content: maybe just wrap if needed
                if isinstance(ch, BoxContainerNode):
                    ch.children.insert(0, bullet_node)
                    transformed_children.append(ch)
                else:
                    # If somehow a text node at li level, wrap it
                    transformed_children.append(
                        BoxContainerNode(
                            style=Style(
                                display="flex", flex_direction="row"
                            ),
                            children=[bullet_node, ch],
                        )
                    )
            box_children = transformed_children

    # Return a container node
    return BoxContainerNode(style=style, children=box_children)


#
# STEP 3: Rendering Box tree to Rich objects
#
# Now we have a well-structured BoxNode tree. Each BoxNode has a final style and children.
# We just translate this into Rich objects. No more style computation, just mechanical translation.


def box_to_rich(node: BoxNode) -> ConsoleRenderable:
    if isinstance(node, BoxTextNode):
        # Render text with the given style
        node_text = node.text
        if node.style.small_caps:
            node_text = node_text.upper()
        text = Text(node_text, end="")
        if node.style.is_bold:
            text.stylize("bold")
        if node.style.is_link or node.style.text_color:
            # If text_color is set, apply it
            if node.style.text_color:
                text.stylize(node.style.text_color)
        return text

    if isinstance(node, BoxContainerNode):
        # Render children according to style
        child_renderables = [box_to_rich(ch) for ch in node.children]

        renderable = layout_box_container(node.style, child_renderables)

        # If panel is True, wrap in Panel
        if node.style.panel or node.style.border:
            renderable = Panel(
                renderable, border_style="dim", box=box.SQUARE
            )

        # Apply padding
        if node.style.padding != (0, 0, 0, 0):
            if isinstance(renderable, Text):
                renderable.pad_left(node.style.padding[3])
                renderable.pad_right(node.style.padding[1])
            else:
                renderable = Padding(renderable, node.style.padding)

        return renderable


def layout_box_container(
    style: Style, children: List[ConsoleRenderable]
) -> ConsoleRenderable:
    match style.display:
        case "flex" | "block" | None:
            if style.flex_direction == "row":
                if style.justify == "between" and len(children) > 1:
                    # For justify-between, wrap children in Align components
                    aligned_children = []
                    for i, child in enumerate(children):
                        if i == 0:
                            # First child aligned left
                            aligned_children.append(Align.left(child))
                        elif i == len(children) - 1:
                            # Last child aligned right
                            aligned_children.append(Align.right(child))
                        else:
                            # Middle children centered
                            aligned_children.append(Align.center(child))

                    return Columns(
                        aligned_children,
                        expand=True,
                        equal=True,
                        padding=(0, style.gap[1]),
                        align=None,
                    )
                else:
                    return Columns(
                        children,
                        expand=True,
                        padding=(0, style.gap[1]),
                        align="left",
                    )
            else:
                if len(children) == 1:
                    return children[0]
                # column layout
                if style.gap[0] > 0:
                    spaced = []
                    for i, ch in enumerate(children):
                        if i > 0:
                            ch = Padding(ch, (style.gap[0], 0, 0, 0))
                        spaced.append(ch)
                    return Group(*spaced)
                else:
                    return Group(*children)
        case "inline":
            return layout_inline(children)


def layout_inline(children: List[ConsoleRenderable]) -> ConsoleRenderable:
    # rich.inspect(children)

    def flatten(children: List[ConsoleRenderable]) -> List[Text]:
        texts = []
        for ch in children:
            if isinstance(ch, Text):
                texts.append(ch)
            else:
                raise Exception("Not implemented")
        return texts

    texts = flatten(children)
    text = Text(end="")
    for t in texts:
        text.append_text(t)
    return text


#
# Public API
#


def render_html(
    element: HTMLElement, console: Optional[Console] = None
) -> None:
    if console is None:
        console = Console()
    stylesheet = StyleSheet()

    # Step 1: HTML -> Node
    node_tree = to_node(element)
    #    rich.inspect(node_tree)

    # Step 2: Node -> Box Tree
    box_tree = node_to_box(node_tree, stylesheet, None)

    # inspect(box_tree)

    # Step 3: Box Tree -> Rich Renderable
    renderable = box_to_rich(box_tree)

    #    pudb.set_trace()
    console.print(renderable)

    # if stylesheet.unknown_classes:
    #     logger.warning(
    #         "Unknown classes",
    #         classes=sorted(list(stylesheet.unknown_classes)),
    #     )
