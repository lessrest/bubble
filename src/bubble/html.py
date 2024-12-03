import functools
import xml.etree.ElementTree as ET

from io import StringIO
from typing import (
    Any,
    Awaitable,
    Literal,
    Callable,
)
from contextlib import contextmanager, asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from fastapi.websockets import WebSocketState
import rich
import structlog
import trio
import starlette
import starlette.middleware

from fastapi import (
    APIRouter,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from rich.traceback import Traceback
from starlette.types import Send, Scope, ASGIApp, Receive
from fastapi.responses import HTMLResponse

from bubble.mint import fresh_id


"""
A module for building HTML/XML documents using Python context managers.
Provides a declarative way to construct DOM trees with live-updating capabilities.
"""

logger = structlog.get_logger()


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


def strs(value: str | list[str]) -> str:
    if isinstance(value, list):
        return " ".join(value)
    return value


def tag(tagname: str, **kwargs):
    """
    Creates a new HTML/XML element with the given tag name and attributes.
    Returns a context manager for adding child elements.
    """
    element = ET.Element(
        tagname,
        attrib={
            attr_name_to_xml(k): "" if v is True else strs(v)
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


@asynccontextmanager
async def live_node(send: trio.MemorySendChannel[ET.Element]):
    with document() as doc:
        yield doc
        for element in doc.element:
            await send.send(element)


class LiveNode:
    # wrap a send channel and allow appending
    def __init__(self, id: str, send: trio.MemorySendChannel[LiveMessage]):
        self.id = id
        self.send = send

    async def _send_elements(
        self, action: Literal["append", "replace", "prepend"]
    ):
        doc = root.get()
        for element in doc.element:
            await self.send.send(
                LiveMessage(
                    id=self.id,
                    action=action,
                    html=ET.tostring(element, encoding="unicode"),
                )
            )

    @asynccontextmanager
    async def appending(self):
        with document():
            yield
            await self._send_elements("append")

    @asynccontextmanager
    async def replacing(self):
        with document():
            yield
            await self._send_elements("replace")

    @asynccontextmanager
    async def prepending(self):
        with document():
            yield
            await self._send_elements("prepend")


live_cancel_scopes: dict[str, trio.CancelScope] = {}
livetags: dict[str, tuple[Callable[..., Awaitable[Any]], tuple, dict]] = {}


def live(
    func: Callable[..., Awaitable[Any]],
    *args: Any,
    **kwargs: Any,
):
    classes("live")
    element = node.get()
    id = element.get("id")
    if id is None:
        id = fresh_id()
        element.set("id", id)
    livetags[id] = (func, args, kwargs)


async def live_subscription(websocket, id: str):
    func, args, kwargs = livetags[id]
    logger.info(f"live subscription for {id} started")
    async with trio.open_nursery() as nursery:
        live_cancel_scopes[id] = nursery.cancel_scope
        try:
            send, recv = trio.open_memory_channel(1)

            withargs = functools.partial(
                func, LiveNode(id, send), *args, **kwargs
            )

            nursery.start_soon(withargs)
            async for message in recv:
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.send_json(
                        {
                            "id": message.id,
                            "action": message.action,
                            "html": message.html,
                        }
                    )
                else:
                    break
        except trio.Cancelled:
            logger.info(f"live subscription for {id} cancelled")
            raise
        finally:
            logger.info(f"live subscription for {id} ended")
            del live_cancel_scopes[id]


router = APIRouter()


@router.websocket("/live")
async def live_websocket(websocket: WebSocket):
    await websocket.accept()

    async with trio.open_nursery() as nursery:
        while True:
            try:
                message = await websocket.receive_json()
                logger.info(f"live message: {message}")

                if message["action"] == "subscribe":
                    id = message["id"]
                    nursery.start_soon(live_subscription, websocket, id)
                elif message["action"] == "unsubscribe":
                    id = message["id"]
                    logger.info(f"unsubscribing from {id}")
                    if id in live_cancel_scopes:
                        live_cancel_scopes[id].cancel()

            except WebSocketDisconnect:
                logger.info("websocket disconnected")
                websocket.application_state = WebSocketState.DISCONNECTED
                break


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
                        classes("bg-slate-950 text-white p-4")
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
            classes("font-mono bg-slate-950 leading-tight")
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
    logger.info(f"{response.status_code} {request.method} {request.url}")
    return response
