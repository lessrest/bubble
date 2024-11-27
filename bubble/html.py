import logging
import functools
import xml.etree.ElementTree as ET

from io import StringIO
from typing import (
    Any,
    Dict,
    Literal,
    Callable,
    Awaitable,
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
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)
from rich.traceback import Traceback
from starlette.types import Send, Scope, ASGIApp, Receive
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocketState

from bubble import mint

logger = logging.getLogger(__name__)

live_router = APIRouter(prefix="/live")


class HTMLDecorators:
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
    def __init__(self):
        self.element = ET.Element("fragment")

    def __str__(self) -> str:
        return "".join(
            ET.tostring(child, encoding="unicode", method="html")
            for child in self.element
        )

    def to_html(self) -> str:
        return self.__str__()

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


node: ContextVar[ET.Element] = ContextVar("node")
root: ContextVar[Fragment] = ContextVar("root")

livetags: Dict[
    str, tuple[Callable[..., Awaitable[Any]], tuple, dict]
] = {}


@contextmanager
def document():
    doc = Fragment()
    token = root.set(doc)
    token2 = node.set(doc.element)
    try:
        yield doc
    finally:
        root.reset(token)
        node.reset(token2)


def tag(tagname: str, **kwargs):
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


def append_element(content: ET.Element):
    parent = node.get()
    parent.append(content)

    @contextmanager
    def context():
        token = node.set(content)
        try:
            yield content
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
    current = node.get().get("class", "")
    if current:
        current += " "
    node.get().set("class", current + " ".join(names))


def dataset(data: dict[str, str]):
    for k, v in data.items():
        attr(f"data-{k}", v)


def live(
    func: Callable[..., Awaitable[Any]],
    *args: Any,
    **kwargs: Any,
):
    classes("live")
    element = node.get()
    id = element.get("id")
    if id is None:
        id = mint.fresh_id()
        element.set("id", id)
    livetags[id] = (func, args, kwargs)


class HypermediaResponse(HTMLResponse):
    def render(self, content: str | None = None) -> bytes | memoryview:
        doc = root.get()
        if doc:
            return doc.to_html().encode("utf-8")
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
async def live_node(send: trio.MemorySendChannel[ET.Element]):
    with document() as doc:
        yield doc
        for element in doc.element:
            await send.send(element)


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


class LiveNode:
    # wrap a send channel and allow appending
    def __init__(
        self, id: str, send: trio.MemorySendChannel[LiveMessage]
    ):
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
                if (
                    websocket.application_state
                    == WebSocketState.CONNECTED
                ):
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


@live_router.websocket("/socket")
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
                websocket.application_state = (
                    WebSocketState.DISCONNECTED
                )
                break


@live_router.get("/index.js", response_class=Response)
async def get_livejs():
    return Response(
        content="""
    document.addEventListener("DOMContentLoaded", function() {
        const ws = new WebSocket(`wss://${window.location.host}/live/socket`);
        ws.onmessage = function(event) {
            const { id, html, action } = JSON.parse(event.data);
            const element = document.getElementById(id);
            document.startViewTransition(() => {
                if (action === "append") {
                    element.insertAdjacentHTML("beforeend", html);
                } else if (action === "replace") {
                    element.innerHTML = html;
                } else if (action === "prepend") {
                    element.insertAdjacentHTML("afterbegin", html);
                }
                htmx.process(element);
            });
        };
        ws.onopen = function() {
            for (const element of document.querySelectorAll(".live")) {
                ws.send(JSON.stringify({
                    "action": "subscribe",
                    "id": element.id,
                }));
            }
        };
        ws.onclose = function() {
        };

        const observer = new MutationObserver((mutations) => {
            mutations.forEach(({ type, addedNodes, removedNodes }) => {
                if (type === 'childList') {
                    const processNodes = (nodes, action) => {
                        nodes.forEach(node => {
                            if (node.nodeType === Node.ELEMENT_NODE) {
                                const liveNodes = [...node.querySelectorAll('.live'), ...(node.classList.contains('live') ? [node] : [])];
                                liveNodes.forEach(liveNode => {
                                    ws.send(JSON.stringify({ action, id: liveNode.id }));
                                });
                            }
                        });
                    };

                    processNodes(removedNodes, 'unsubscribe');
                    processNodes(addedNodes, 'subscribe');
                }
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    });
    """,
        media_type="text/javascript",
    )


# pure ASGI middleware
class ErrorMiddleware:
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
            # dump = console.export_html(
            #     inline_styles=True,
            #     theme=rich.terminal_theme.MONOKAI,
            #     code_format="{code}",
            # )

            # raw_fragment(dump)
            text(console.export_text())


async def log_middleware(request: Request, call_next):
    logger.debug(f"{request.method} {request.url}")
    response = await call_next(request)
    logger.info(
        f"{response.status_code} {request.method} {request.url}"
    )
    return response


def xslt_document():
    @contextmanager
    def context():
        with document() as doc:
            with tag(
                "xsl:stylesheet",
                version="1.0",
                xmlns_xsl="http://www.w3.org/1999/XSL/Transform",
            ):
                yield doc

    return context()
