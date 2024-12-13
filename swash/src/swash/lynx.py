from typing import Optional, List
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
            return Padding(text)
        return Text("")

    def _render_element(self, element: HTMLElement) -> ConsoleRenderable:
        handler = getattr(
            self, f"_render_{element.tag}", self._render_default
        )
        return handler(element)

    def _render_default(self, element: HTMLElement) -> ConsoleRenderable:
        """Default rendering for unknown elements."""
        renderables: List[ConsoleRenderable] = []

        if element.text:
            renderables.append(self._render_text(element.text))

        for child in element:
            renderables.append(self.render(child))

        if element.tail:
            renderables.append(self._render_text(element.tail))

        return Group(*renderables)

    def _render_div(self, element: HTMLElement) -> ConsoleRenderable:
        """Render div elements with spacing."""
        renderables = [self.render(child) for child in element]
        # for flex-col
        if "flex-col" in element.attrib.get("class", ""):
            if "gap" in element.attrib.get("class", ""):
                with_padding_between = []
                for i, renderable in enumerate(renderables):
                    if i > 0 and i < len(renderables) - 1:
                        x = Padding(renderable, (1, 1))
                    else:
                        x = renderable
                    with_padding_between.append(x)

                return Group(*with_padding_between, fit=False)
            else:
                return Group(*renderables, fit=False)
        else:
            return Columns(
                renderables, expand=False, padding=(0, 4), align="left"
            )

    def _render_span(self, element: HTMLElement) -> ConsoleRenderable:
        """Render span elements."""
        renderables = [self.render(child) for child in element]
        if element.text:
            renderables.insert(0, self._render_text(element.text))
        if element.tail:
            renderables.append(self._render_text(element.tail))
        if len(renderables) == 1:
            x = renderables[0]
        else:
            x = Columns(renderables)
        return x

    def _render_dl(self, element: HTMLElement) -> ConsoleRenderable:
        """Render definition lists.

        Creates a two-column layout where terms are bold and definitions are
        indented. Handles nested content and maintains proper spacing.
        """
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

        return Panel(
            Group(*renderables), border_style="dim", box=box.SQUARE
        )

    def _render_a(self, element: HTMLElement) -> ConsoleRenderable:
        """Render links."""
        text = self._capture_text(element)
        return Text(text, style="blue")

    def _render_button(self, element: HTMLElement) -> ConsoleRenderable:
        """Render buttons."""
        text = self._capture_text(element)
        return Text(f"[{text}]", style="bold")

    def _render_details(self, element: HTMLElement) -> ConsoleRenderable:
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

        return Group(*renderables)

    def _render_ul(self, element: HTMLElement) -> ConsoleRenderable:
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
        return Group(*renderables)

    # def _render_span(self, element: HTMLElement) -> ConsoleRenderable:
    #     """Render span elements."""
    #     text = self._capture_text(element)
    #     if "blur-sm" in element.attrib.get("class", ""):
    #         return Text("[REDACTED]", style="red")
    #     return Text(text)

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
