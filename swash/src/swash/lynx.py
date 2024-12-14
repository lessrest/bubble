from typing import Literal, Optional, List, Tuple
from rich.console import Console, ConsoleRenderable, Group
from rich.text import Text
from rich.padding import Padding
from rich.columns import Columns
from rich.panel import Panel
from rich import box
from xml.etree.ElementTree import Element as HTMLElement


def render_html(
    element: HTMLElement | str, console: Optional[Console] = None
) -> None:
    """Render an HTML element to the console in a lynx-like style."""
    if console is None:
        console = Console()

    renderer = LynxRenderer(console)
    renderable = renderer.render(element)
    console.print(renderable)


class Style:
    """A simple style model based on a subset of Tailwind-like classes.

    Supported properties:
    - display: 'block' or 'flex' or None
    - flex_direction: 'row' or 'column' (only if display='flex')
    - gap: integer (spacing between items)
    - padding: tuple (top, right, bottom, left)
    - is_link: bool
    - is_bold: bool (e.g. for buttons)
    """

    flex_direction: Optional[Literal["row", "column"]] = None
    display: Optional[Literal["flex", "block"]] = None
    gap: Optional[int] = None
    padding: Optional[Tuple[int, int, int, int]] = None
    is_link: Optional[bool] = None
    is_bold: Optional[bool] = None

    def __init__(self):
        self.display = None
        self.flex_direction = None
        self.gap = 0
        self.padding = (0, 0, 0, 0)
        self.is_link = False
        self.is_bold = False

    def apply_classes(self, classes: List[str]):
        for cls in classes:
            # Basic flex classes
            if cls == "flex":
                self.display = "flex"
            elif cls == "flex-row":
                self.display = "flex"
                self.flex_direction = "row"
            elif cls == "flex-col":
                self.display = "flex"
                self.flex_direction = "column"

            # Gap classes like gap-1, gap-2 etc.
            if cls.startswith("gap-"):
                try:
                    self.gap = int(cls.split("-")[1])
                except ValueError:
                    pass

            # Padding classes like p-1, p-2 etc.
            # For simplicity, apply same padding on all sides
            if cls.startswith("p-"):
                try:
                    p = int(cls.split("-")[1])
                    self.padding = (p, p, p, p)
                except ValueError:
                    pass

            # Bold text, links, etc. (just examples)
            if cls == "font-bold":
                self.is_bold = True

            if cls == "link":
                self.is_link = True

    def apply_padding(
        self, renderable: ConsoleRenderable
    ) -> ConsoleRenderable:
        if self.padding and self.padding != (0, 0, 0, 0):
            return Padding(renderable, self.padding)
        return renderable

    def layout(
        self, children: List[ConsoleRenderable]
    ) -> ConsoleRenderable:
        """Apply the layout instructions based on the style properties."""
        # If display=flex and direction=row, use Columns
        # If display=flex and direction=column, use Group with spacing (gap)
        # Else just a Group
        if self.display == "flex":
            if not self.flex_direction:
                self.flex_direction = "row"
            if self.flex_direction == "row":
                # Apply gap as padding between columns
                # rich.Columns doesn't have a direct "gap" option,
                # but we can simulate with padding.
                # We'll just use Columns with a padding equal to gap,
                # which will be horizontal spacing.
                return Columns(
                    children,
                    expand=False,
                    padding=(0, self.gap or 0),
                    align="left",
                )
            else:
                # vertical layout
                # If gap > 0, we apply spacing between items.
                # Group doesn't have a gap directly; we can manually insert padding.
                if self.gap and self.gap > 0 and len(children) > 1:
                    spaced = []
                    for i, ch in enumerate(children):
                        if i > 0:
                            # Add vertical spacing above this item by padding
                            ch = Padding(ch, (self.gap, 0, 0, 0))
                        spaced.append(ch)
                    return Group(*spaced, fit=False)
                else:
                    return Group(*children, fit=False)
        else:
            # Default block rendering: just stack children
            return Group(*children)


class LynxRenderer:
    def __init__(self, console: Console):
        self.console = console
        self.indent_level = 0

    def render(self, element: HTMLElement | str) -> ConsoleRenderable:
        if isinstance(element, str):
            return self._render_text(element)
        else:
            return self._render_element(element)

    def _render_text(self, text: str) -> ConsoleRenderable:
        if text.strip():
            return Text(text)
        return Text("")

    def _render_element(self, element: HTMLElement) -> ConsoleRenderable:
        # Parse classes and derive style
        style = self._parse_classes(element)
        handler = getattr(
            self, f"_render_{element.tag}", self._render_default
        )
        rendered = handler(element, style)
        # Apply block-level padding from style
        rendered = style.apply_padding(rendered)
        return rendered

    def _parse_classes(self, element: HTMLElement) -> Style:
        style = Style()
        classes = element.attrib.get("class", "")
        if classes:
            class_list = [c.strip() for c in classes.split()]
            style.apply_classes(class_list)
        return style

    def _apply_style(
        self, style: Style, children: List[ConsoleRenderable]
    ) -> ConsoleRenderable:
        return style.layout(children)

    def _render_default(
        self, element: HTMLElement, style: Style
    ) -> ConsoleRenderable:
        """Default rendering for unknown elements."""
        renderables: List[ConsoleRenderable] = []

        if element.text:
            renderables.append(self._render_text(element.text))

        for child in element:
            renderables.append(self.render(child))

        if element.tail and element.tail.strip():
            renderables.append(self._render_text(element.tail))

        return self._apply_style(style, renderables)

    def _render_div(
        self, element: HTMLElement, style: Style
    ) -> ConsoleRenderable:
        """Render div elements with styling applied."""
        renderables = []

        if element.text and element.text.strip():
            renderables.append(self._render_text(element.text))

        for child in element:
            renderables.append(self.render(child))

        if element.tail and element.tail.strip():
            renderables.append(self._render_text(element.tail))

        return self._apply_style(style, renderables)

    def _render_span(
        self, element: HTMLElement, style: Style
    ) -> ConsoleRenderable:
        """Render span elements."""
        renderables = []

        # Gather text before children
        if element.text and element.text.strip():
            renderables.append(self._render_text(element.text))

        # Render children
        for child in element:
            renderables.append(self.render(child))

        # Tail text
        if element.tail and element.tail.strip():
            renderables.append(self._render_text(element.tail))

        return self._apply_style(style, renderables)

    def _render_dl(
        self, element: HTMLElement, style: Style
    ) -> ConsoleRenderable:
        """Render definition lists as panels."""
        renderables = []

        for child in element:
            if not isinstance(child, HTMLElement):
                continue

            if child.tag == "dt":
                # Add some spacing before new terms (except the first one)
                if renderables:
                    renderables.append(Text(""))
                # Render the term in bold
                term_content = self.render(child)
                renderables.append(
                    Padding(term_content, (0, 2, 0, 0), style="bold")
                )

            elif child.tag == "dd":
                # Indent the definition and handle multi-line content
                self.indent_level += 1
                definition = self.render(child)
                self.indent_level -= 1
                renderables.append(Padding(definition, (0, 0, 0, 0)))

            # Handle any trailing text
            if child.tail and child.tail.strip():
                renderables.append(self._render_text(child.tail))

        panel = Panel(
            Group(*renderables), border_style="dim", box=box.SQUARE
        )
        return style.apply_padding(panel)

    def _render_a(
        self, element: HTMLElement, style: Style
    ) -> ConsoleRenderable:
        """Render links."""
        text = self._capture_text(element)
        # If style says link or we treat 'a' as a link by default
        link_text = Text(text, style="blue")
        # If style.is_link is set, we might do something else, but here it's default anyway.
        # Just return it as is.
        if style.is_bold:
            link_text.stylize("bold")
        return style.apply_padding(link_text)

    def _render_button(
        self, element: HTMLElement, style: Style
    ) -> ConsoleRenderable:
        """Render buttons."""
        text = self._capture_text(element)
        btn_text = Text(f"[{text}]")
        if style.is_bold:
            btn_text.stylize("bold")
        return style.apply_padding(btn_text)

    def _render_details(
        self, element: HTMLElement, style: Style
    ) -> ConsoleRenderable:
        """Render details/summary elements."""
        summary = None
        content_renderables = []

        for child in element:
            if isinstance(child, HTMLElement):
                if child.tag == "summary":
                    summary = self._capture_text(child)
                else:
                    self.indent_level += 1
                    content_renderables.append(self.render(child))
                    self.indent_level -= 1

        renderables = []
        if summary:
            renderables.append(Text("▶ " + summary, style="bold"))
        renderables.extend(content_renderables)

        return self._apply_style(style, renderables)

    def _render_ul(
        self, element: HTMLElement, style: Style
    ) -> ConsoleRenderable:
        """Render unordered lists."""
        renderables = []
        for child in element:
            if isinstance(child, HTMLElement) and child.tag == "li":
                # Render the entire li subtree
                content = self.render(child)
                bullet = Padding(
                    Columns([Text("•", style="bold"), content]),
                    (0, 0, 0, self.indent_level * 2),
                )
                renderables.append(bullet)
            else:
                raise ValueError(f"Unknown child type: {type(child)}")
        return self._apply_style(style, renderables)

    def _capture_text(self, element: HTMLElement) -> str:
        """Capture all text content from an element and its children."""
        parts = []
        if element.text:
            parts.append(element.text)
        for child in element:
            if isinstance(child, str):
                parts.append(child)
            elif isinstance(child, HTMLElement):
                parts.append(self._capture_text(child))
        if element.tail:
            parts.append(element.tail)
        return " ".join(filter(None, parts))
