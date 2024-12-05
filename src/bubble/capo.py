import inspect

from enum import Enum
from typing import Any, Callable, Dict, Union, Protocol
from contextlib import asynccontextmanager

import trio
import cbor2
import structlog

from fastapi import WebSocket
from trio_websocket import (
    WebSocketConnection as TrioWebSocket,
    ConnectionClosed as TrioConnectionClosed,
)
from trio_websocket import (
    open_websocket_url,
)
from starlette.websockets import (
    WebSocket as StarletteWebSocket,
    WebSocketDisconnect as StarletteConnectionClosed,
)

logger = structlog.stdlib.get_logger()


class CapRef[T]:
    _vat: "Vat"
    _protocol: type[T]
    _methods: Dict[str, Any]

    def __init__(self, vat: "Vat", protocol: type[T]):
        self.log = logger.bind(capability_type=protocol.__name__)
        self._vat = vat
        self._protocol = protocol
        self._methods = {}

        for name, method in inspect.getmembers(protocol):
            if hasattr(method, "_is_capability_method"):
                self._methods[name] = method


def method(interface_id: int, method_id: int) -> Callable[..., Any]:
    """Decorator to mark methods that can be called remotely"""

    def decorator(func):
        func._is_capability_method = True
        func._interface_id = interface_id
        func._method_id = method_id
        return func

    return decorator


class RemoteCapability[T](CapRef[T]):
    """Represents a capability hosted by another vat"""

    def __init__(self, vat: "Vat", protocol: type[T], import_id: int):
        super().__init__(vat=vat, protocol=protocol)
        self._import_id = import_id

    def __getattr__(self, name):
        """Handle method calls by forwarding them to the remote vat"""

        async def call_method(*args, **kwargs):
            params = {"args": args, "kwargs": kwargs}
            return await self._call_remote(name, params)

        return call_method

    async def _call_remote(self, method_name: str, params: Any):
        """Call a method on a remote capability"""
        self.log.debug(
            "Calling remote method",
            remote_method_name=method_name,
            params=params,
        )

        m = self._methods.get(method_name)
        if m is None:
            raise Exception(f"Unknown method: {method_name}")

        return await self._vat.call_method(
            self._import_id,
            m._interface_id,
            m._method_id,
            params,
        )


class LocalCapability[T](CapRef[T]):
    """Represents a capability hosted by this vat"""

    def __init__(self, vat: "Vat", protocol: type[T], instance: T):
        super().__init__(vat=vat, protocol=protocol)
        self._instance = instance

    def __getattr__(self, name):
        return getattr(self._instance, name)


# Example capability implementation:
class ChatRoom(Protocol):
    INTERFACE_ID = 0x1234  # Unique ID for this interface

    @method(INTERFACE_ID, 0)
    async def send_message(self, content: str) -> None: ...

    @method(INTERFACE_ID, 1)
    async def get_history(self) -> Dict[str, Any]: ...


class ChatRoomImpl(ChatRoom):
    def __init__(self):
        self.history = []

    async def send_message(self, content: str) -> None:
        """Send a message to the chat room"""
        # Implementation for local calls
        print(f"Message received: {content}")
        self.history.append(content)

    async def get_history(self):
        """Get chat history"""
        # Implementation for local calls
        return {"messages": ["msg1", "msg2"]}


class Side(Enum):
    SERVER = "server"
    CLIENT = "client"


class WebSocketAdapter(Protocol):
    """Protocol for WebSocket connections"""

    async def send_message(self, message: bytes) -> None: ...
    async def get_message(self) -> bytes: ...
    async def aclose(self) -> None: ...


class WebSocketClosed(Exception):
    """Exception raised when the WebSocket is closed"""


class StarletteWebSocketWrapper:
    """Wrapper for Starlette WebSocket to match our protocol"""

    def __init__(self, websocket: StarletteWebSocket):
        self.websocket = websocket

    async def send_message(self, message: bytes) -> None:
        try:
            await self.websocket.send_bytes(message)
        except StarletteConnectionClosed:
            raise WebSocketClosed

    async def get_message(self) -> bytes:
        try:
            return await self.websocket.receive_bytes()
        except StarletteConnectionClosed:
            raise WebSocketClosed

    async def aclose(self) -> None:
        await self.websocket.close()


class TrioWebSocketWrapper:
    """Wrapper for Trio WebSocket to match our protocol"""

    def __init__(self, websocket: TrioWebSocket):
        self.websocket = websocket

    async def send_message(self, message: bytes) -> None:
        try:
            await self.websocket.send_message(message)
        except TrioConnectionClosed:
            raise WebSocketClosed

    async def get_message(self) -> bytes:
        try:
            return await self.websocket.get_message()
        except TrioConnectionClosed:
            raise WebSocketClosed

    async def aclose(self) -> None:
        await self.websocket.aclose()


class Vat:
    """A vat is a collection of objects and their capabilities"""

    def __init__(
        self,
        websocket: Union[StarletteWebSocket, TrioWebSocket],
        side: Side,
    ):
        self.log = logger.bind(side=side)
        self.log.info("Creating vat")

        self._closing = False

        # Wrap the websocket in appropriate adapter
        if isinstance(websocket, StarletteWebSocket):
            self.websocket = StarletteWebSocketWrapper(websocket)
            self.log.debug("Using Starlette WebSocket")
        else:
            self.websocket = TrioWebSocketWrapper(websocket)
            self.log.debug("Using Trio WebSocket")

        # The four tables from the RPC protocol
        self.questions = {}  # QuestionId -> (SendChannel, ReceiveChannel)
        self.answers = {}  # AnswerId -> Interface
        self.exports = {}  # ExportId -> Interface
        self.imports = {}  # ImportId -> Interface

        # Counter for generating new IDs
        self._next_question_id = 0
        self._next_export_id = 0

        self.side = side

        # Bootstrap interface for this vat
        self.bootstrap_interface = None

    async def run(self):
        """Main message loop"""
        self.log.info("Starting vat message loop")
        try:
            while True:
                try:
                    message = await self.receive_message()
                except WebSocketClosed:
                    if self._closing:
                        break
                    else:
                        if self.side == Side.SERVER:
                            if len(self.questions) == 0:
                                self.log.info(
                                    "client disconnected with no pending questions"
                                )
                                break
                            else:
                                raise
                        else:
                            # we're the client, so the server
                            # closing the connection is an error
                            raise
                if message is None:
                    break
                msg_type = message.get("type")
                self.log.debug("Received message", message_type=msg_type)
                await self.handle_message(message)
        except Exception as e:
            self.log.exception("Error in message loop", error=str(e))
            abort = {"type": "abort", "reason": str(e)}
            await self.send_message(abort)
            raise

    async def close(self):
        """Clean up the vat"""
        self._closing = True

        # Close websocket
        await self.websocket.aclose()

    async def bootstrap(self):
        """Get the bootstrap interface from the remote vat"""
        qid = self._next_question()
        message = {"type": "bootstrap", "questionId": qid}
        return await self.ask_question(message)

    async def call_method(self, target_id, interface_id, method_id, params):
        """Make an outgoing method call"""
        self.log.debug(
            "Calling remote method",
            target_id=target_id,
            interface_id=interface_id,
            method_id=method_id,
        )
        qid = self._next_question()
        message = {
            "type": "call",
            "questionId": qid,
            "target": {"importedCap": target_id},
            "interfaceId": interface_id,
            "methodId": method_id,
            "params": params,
        }

        return await self.ask_question(message)

    async def ask_question(self, message):
        qid = message["questionId"]
        send_channel, receive_channel = trio.open_memory_channel(1)
        self.questions[qid] = (send_channel, receive_channel)
        await self.send_message(message)
        self.log.debug("Waiting for call response")
        result = await receive_channel.receive()
        self.log.debug("Call response received")
        if isinstance(result, Exception):
            raise result
        return result

    async def send_message(self, message):
        """Send a message over the websocket"""
        self.log.debug("Sending message", message_type=message.get("type"))
        message_bytes = cbor2.dumps(message)
        await self.websocket.send_message(message_bytes)

    async def receive_message(self):
        """Receive a message from the websocket"""
        message_bytes = await self.websocket.get_message()
        message = cbor2.loads(message_bytes)
        return message

    def set_bootstrap_interface(self, interface):
        """Set the bootstrap interface for this vat"""
        self.bootstrap_interface = interface

    async def handle_message(self, message):
        """Handle an incoming RPC message"""

        msg_type = message.get("type")

        if msg_type == "unimplemented":
            pass

        elif msg_type == "abort":
            reason = message.get("reason", "Unknown")
            raise Exception(f"Remote aborted: {reason}")

        elif msg_type == "bootstrap":
            await self._handle_bootstrap(message)

        elif msg_type == "call":
            await self._handle_call(message)

        elif msg_type == "return":
            await self._handle_return(message)

        elif msg_type == "finish":
            await self._handle_finish(message)

        else:
            # Send unimplemented in response
            await self._send_unimplemented(message)

    async def _send_unimplemented(self, message):
        """Send an unimplemented message in response to an unsupported message"""
        unimplemented = {"type": "unimplemented", "original": message}
        await self.send_message(unimplemented)

    async def _handle_bootstrap(self, message):
        """Handle a bootstrap message"""
        qid = message["questionId"]
        self.log.debug(
            "Handling bootstrap request", question_id=qid, msg=message
        )
        if self.bootstrap_interface is None:
            self.log.warning("No bootstrap interface available")
            return_msg = {
                "type": "return",
                "answerId": qid,
                "exception": {"reason": "No bootstrap interface available"},
            }
            await self.send_message(return_msg)
            return

        # Export the bootstrap interface
        export_id = self._next_export()
        self.exports[export_id] = self.bootstrap_interface

        # Return the capability
        return_msg = {
            "type": "return",
            "answerId": qid,
            "results": {"capTable": [{"senderHosted": export_id}]},
        }
        await self.send_message(return_msg)

    async def _handle_call(self, message):
        """Handle a method call"""
        self.log.debug("Handling call", msg=message)
        qid = message["questionId"]
        self.answers[qid] = None
        try:
            target_info = message["target"]
            if "importedCap" in target_info:
                cap_id = target_info["importedCap"]
                target = self.exports.get(cap_id)
                if target is None:
                    raise Exception("Invalid capability")

                interface_id = message["interfaceId"]
                method_id = message["methodId"]
                params = message.get("params", {})

                # Find the method
                m = None
                for name, m in target._methods.items():
                    if (
                        m._method_id == method_id
                        and m._interface_id == interface_id
                    ):
                        m = getattr(target, name)
                        break

                if m is None:
                    raise Exception(f"Method {method_id} not found")

                # Call the method (unpack params from dict)
                # We assumed params as {"args": [...], "kwargs": {...}}
                args = params.get("args", [])
                kwargs = params.get("kwargs", {})
                result = await m(*args, **kwargs)

                # Send successful return
                return_msg = {
                    "type": "return",
                    "answerId": qid,
                    "results": result,
                }
                await self.send_message(return_msg)
            else:
                raise Exception("Unsupported target type")

        except Exception as e:
            # Send error return
            return_msg = {
                "type": "return",
                "answerId": qid,
                "exception": {"reason": str(e)},
            }
            await self.send_message(return_msg)
        finally:
            del self.answers[qid]

    async def _handle_return(self, message):
        """Handle a return message"""
        answer_id = message["answerId"]
        self.log.debug("Handling return", answer_id=answer_id)
        channel = self.questions.get(answer_id)
        if channel is None:
            return

        send_channel, receive_channel = channel

        # Send result or exception through channel
        if "results" in message:
            await send_channel.send(message["results"])
        elif "exception" in message:
            await send_channel.send(
                Exception(message["exception"]["reason"])
            )

        del self.questions[answer_id]

    async def _handle_finish(self, message):
        """Handle a finish message"""
        qid = message["questionId"]
        if qid in self.answers:
            del self.answers[qid]

    def _next_question(self):
        """Get the next available question ID"""
        qid = self._next_question_id
        self._next_question_id += 1
        return qid

    def _next_export(self):
        """Get the next available export ID"""
        eid = self._next_export_id
        self._next_export_id += 1
        return eid

    def export_capability(self, capability: LocalCapability) -> int:
        """Export a capability to be used by other vats"""
        export_id = self._next_export()
        self.log.debug(
            "Exporting capability",
            export_id=export_id,
            capability_type=type(capability).__name__,
        )
        capability._vat = self
        self.exports[export_id] = capability
        return export_id

    def import_capability[T](self, import_id: int, protocol: type[T]) -> Any:
        """Import a capability from another vat"""
        self.log.debug(
            "Importing capability",
            import_id=import_id,
            interface_class=protocol.__name__,
        )
        cap = RemoteCapability(self, protocol, import_id)
        self.imports[import_id] = cap
        return cap


@asynccontextmanager
async def connect_vat(url: str):
    """Connect to a remote vat as a client"""
    logger.info("Connecting to remote vat", url=url)
    async with open_websocket_url(url) as websocket:
        vat = Vat(websocket, Side.CLIENT)
        try:
            yield vat
        finally:
            logger.info("Closing vat connection")
            await vat.close()


async def client_example():
    """Example of using a vat as a client"""
    async with trio.open_nursery() as nursery:
        async with connect_vat("ws://localhost:8000/ws") as vat:
            nursery.start_soon(vat.run)

            # Get the remote chat room capability
            remote_chat = await vat.bootstrap()

            # Assuming remote_chat is something like {"capTable": [{"senderHosted": <exportId>}]}
            # We would then import that capability using vat.import_capability:
            if (
                "capTable" in remote_chat
                and len(remote_chat["capTable"]) > 0
            ):
                import_id = remote_chat["capTable"][0]["senderHosted"]
                chat_cap = vat.import_capability(import_id, ChatRoom)
                await chat_cap.send_message("Hello from client!")
                history = await chat_cap.get_history()
                print(f"Chat history: {history}")
                await trio.sleep(3)
            else:
                print("No bootstrap capability returned.")


async def main():
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "client":
        await client_example()
        return

    # Server code
    from fastapi import FastAPI

    app = FastAPI()

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()  # Need to accept the connection first
        vat = Vat(websocket, Side.SERVER)
        chat = ChatRoomImpl()
        vat.set_bootstrap_interface(LocalCapability(vat, ChatRoom, chat))
        await vat.run()

    import hypercorn

    from hypercorn.trio import serve

    config = hypercorn.Config()
    config.bind = ["localhost:8000"]
    await serve(app, config)  # type: ignore


if __name__ == "__main__":
    trio.run(main)
