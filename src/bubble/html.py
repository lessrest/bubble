import logging
import functools
import xml.etree.ElementTree as ET

from io import StringIO
from typing import (
    Any,
    Literal,
    Callable,
)
from contextlib import contextmanager, asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass

import rich
import trio
import starlette
import starlette.middleware

from fastapi import (
    Request,
    Response,
)
from rich.traceback import Traceback
from starlette.types import Send, Scope, ASGIApp, Receive
from fastapi.responses import HTMLResponse


"""
A module for building HTML/XML documents using Python context managers.
Provides a declarative way to construct DOM trees with live-updating capabilities.
"""

logger = logging.getLogger(__name__)


class HTMLDecorators:
    """
    Provides a convenient API for creating HTML elements as decorators.
    Usage: @html.div(class="container") or @html("div", class="container")
    """

    def __getattr__(self, name: str) -> Callable[..., Any]:
        return lambda *args, **kwargs: element(name, *args, **kwargs)

    def __call__(
        self, name: str, *klasses: str, **kwargs: Any
    ) -> Callable[[Any], Any]:
        return element(name, *klasses, **kwargs)


html = HTMLDecorators()


def element(tag_name: str, *klasses: str, **kwargs):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs2):
            with tag(tag_name, **kwargs):
                classes(*klasses)
                return func(*args, **kwargs2)

        return wrapper

    return decorator


class Fragment:
    """
    Represents a collection of HTML/XML elements that can be rendered
    as a complete document or XML fragment.
    """

    def __init__(self):
        self.element = ET.Element("fragment")

    def __str__(self) -> str:
        return self.to_html()

    def to_html(self, compact: bool = True) -> str:
        if len(self.element) == 0:
            return ""
        elif len(self.element) > 1 and not compact:
            raise ValueError(
                "Pretty printing requires exactly one root element"
            )

        if compact:
            return "".join(
                ET.tostring(child, encoding="unicode", method="html")
                for child in self.element
            )

        # For pretty printing, use BeautifulSoup
        from bs4 import BeautifulSoup

        element = (
            self.element[0] if len(self.element) == 1 else self.element
        )
        rough_string = ET.tostring(
            element, encoding="unicode", method="html"
        )
        soup = BeautifulSoup(rough_string, "html.parser")
        return soup.prettify()

    def to_xml(self) -> str:
        if len(self.element) > 1:
            raise ValueError("Fragment has more than one element")
        tree = ET.ElementTree(self.element[0])
        s = StringIO()
        tree.write(s, encoding="unicode", method="xml")
        return s.getvalue()


def attr_name_to_xml(name: str) -> str:
    if name == "classes":
        return "class"
    # replace _ with -
    return name.replace("_", "-").removesuffix("-")


# Context variables to track the current element and root document
node: ContextVar[ET.Element] = ContextVar("node")
root: ContextVar[Fragment] = ContextVar("root")


@contextmanager
def document():
    """Creates a new document context for building HTML/XML content"""
    doc = Fragment()
    token = root.set(doc)
    token2 = node.set(doc.element)
    try:
        yield doc
    finally:
        root.reset(token)
        node.reset(token2)


def tag(tagname: str, **kwargs):
    """
    Creates a new HTML/XML element with the given tag name and attributes.
    Returns a context manager for adding child elements.
    """
    element = ET.Element(
        tagname,
        attrib={
            attr_name_to_xml(k): "" if v is True else str(v)
            for k, v in kwargs.items()
            if v
        },
    )
    parent = node.get()
    parent.append(element)

    @contextmanager
    def context():
        token = node.set(element)
        try:
            yield element
        finally:
            node.reset(token)

    return context()


def text(content: str):
    element = node.get()
    if len(element) > 0:
        last_child = element[-1]
        last_child.tail = (last_child.tail or "") + content
    else:
        element.text = (element.text or "") + content


def attr(name: str, value: str | bool | None = True):
    element = node.get()
    xml_name = attr_name_to_xml(name)

    if value is None or value is False:
        element.attrib.pop(xml_name, None)
    elif value is True:
        element.set(xml_name, "")
    else:
        element.set(xml_name, str(value))


def classes(*names: str):
    current = node.get().get("class", "").strip()
    if current and names:
        current += " "
    node.get().set("class", current + " ".join(names))


def dataset(data: dict[str, str]):
    for k, v in data.items():
        attr(f"data-{k}", v)


class HypermediaResponse(HTMLResponse):
    def render(self, content: str | None = None) -> bytes | memoryview:
        doc = root.get()
        if doc:
            html = doc.to_html()
            return f"<!doctype html>\n{html}".encode("utf-8")
        else:
            return super().render(content)


class XMLResponse(Response):
    media_type = "application/xml"

    def render(self, content: Any) -> bytes:
        doc = root.get()
        if doc:
            return doc.to_xml().encode("utf-8")
        else:
            return str(content).encode("utf-8")


@asynccontextmanager
async def appending(send: trio.MemorySendChannel[ET.Element]):
    with document() as doc:
        yield
        for element in doc.element:
            await send.send(element)


@dataclass
class LiveMessage:
    id: str
    action: Literal["append", "replace", "prepend"]
    html: str


# pure ASGI middleware
class ErrorMiddleware:
    """
    ASGI middleware that catches exceptions and renders them as
    rich HTML error pages with detailed tracebacks.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        except* Exception as eg:
            with document() as doc:
                with tag("html"):
                    with tag("head"):
                        tag(
                            "script",
                            src="https://cdn.tailwindcss.com",
                        )
                        tag(
                            "script",
                            src="https://unpkg.com/htmx.org@2",
                        )
                    with tag("body"):
                        classes("bg-gray-800 text-white p-4")
                        for e in eg.exceptions:
                            self.render_error(e)
                            logger.error(
                                "Error during request",
                                exc_info=(
                                    e.__class__,
                                    e,
                                    e.__traceback__,
                                ),
                            )
                response = HypermediaResponse(
                    ET.tostring(doc.element, encoding="unicode"),
                    status_code=500,
                )
                await response(scope, receive, send)

    def render_error(self, e):
        with tag("pre"):
            classes("font-mono bg-gray-800 leading-tight")
            console = rich.console.Console(
                file=StringIO(),
                force_terminal=True,
                record=True,
                width=120,
                color_system="truecolor",
            )
            traceback = Traceback.from_exception(
                exc_type=e.__class__,
                exc_value=e,
                traceback=e.__traceback__,
                show_locals=True,
                max_frames=100,
                width=120,
                indent_guides=True,
                word_wrap=True,
                suppress=[starlette.middleware],
            )
            console.print(traceback)
            text(console.export_text())


async def log_middleware(request: Request, call_next):
    logger.debug(f"{request.method} {request.url}")
    response = await call_next(request)
    logger.info(
        f"{response.status_code} {request.method} {request.url}"
    )
    return response
