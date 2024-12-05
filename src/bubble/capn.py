# Simple implementation of Cap'n Proto RPC Level 1
# via WebSocket using FastAPI and Trio structured concurrency.

import capnp
import rich
import structlog

import trio
from fastapi import WebSocket
from enum import Enum
from typing import Any, Dict, Optional, Protocol, Union
import inspect
from contextlib import asynccontextmanager
from trio_websocket import (
    open_websocket_url,
    WebSocketConnection as TrioWebSocket,
)
from starlette.websockets import WebSocket as StarletteWebSocket


# Import the RPC schemas
rpc_capnp = capnp.load("src/proto/rpc.capnp")  # type: ignore
two_party_capnp = capnp.load("src/proto/two-party-rpc.capnp")  # type: ignore

# Add logger at module level
logger = structlog.get_logger()


class Capability:
    """Base class for all capabilities that can be shared between vats"""

    def __init__(self, vat: "Vat", export_id: Optional[int] = None):
        self.log = logger.bind(
            capability_type=type(self).__name__, export_id=export_id
        )
        self.log.debug("Creating capability")
        self._vat = vat
        self._export_id = export_id
        # Store method schemas for this capability
        self._methods: Dict[str, Any] = {}

        # Register all methods marked with @capability_method
        for name, method in inspect.getmembers(self.__class__):
            if hasattr(method, "_is_capability_method"):
                self._methods[name] = method

    @staticmethod
    def method(interface_id: int, method_id: int):
        """Decorator to mark methods that can be called remotely"""

        def decorator(func):
            func._is_capability_method = True
            func._interface_id = interface_id
            func._method_id = method_id
            return func

        return decorator

    async def _call_remote(self, method_name: str, params: Any):
        """Call a method on a remote capability"""
        self.log.debug(
            "Calling remote method",
            method_name=method_name,
            export_id=self._export_id,
        )
        if self._vat is None:
            raise Exception("Capability not attached to a vat")

        method = self._methods.get(method_name)
        if method is None:
            raise Exception(f"Unknown method: {method_name}")

        return await self._vat.call_method(
            self._export_id, method._method_id, params
        )


class RemoteCapability(Capability):
    """Represents a capability hosted by another vat"""

    def __init__(self, vat: "Vat", import_id: int):
        super().__init__(vat=vat)
        self._import_id = import_id

    def __getattr__(self, name):
        """Handle method calls by forwarding them to the remote vat"""

        async def method(*args, **kwargs):
            # Convert args/kwargs to Cap'n Proto params
            params = self._pack_params(args, kwargs)
            return await self._call_remote(name, params)

        return method

    def _pack_params(self, args, kwargs):
        """Pack method parameters into Cap'n Proto format"""
        # TODO: Implement parameter packing
        pass


# Example capability implementation:
class ChatRoom(Capability):
    """A chat room capability that can be shared between vats"""

    INTERFACE_ID = 0x1234  # Unique ID for this interface

    @Capability.method(INTERFACE_ID, 0)
    async def send_message(self, content: str):
        """Send a message to the chat room"""
        # Implementation for local calls
        print(f"Message received: {content}")
        return {"status": "sent"}

    @Capability.method(INTERFACE_ID, 1)
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


class StarletteWebSocketWrapper:
    """Wrapper for Starlette WebSocket to match our protocol"""

    def __init__(self, websocket: StarletteWebSocket):
        self.websocket = websocket

    async def send_message(self, message: bytes) -> None:
        await self.websocket.send_bytes(message)

    async def get_message(self) -> bytes:
        return await self.websocket.receive_bytes()

    async def aclose(self) -> None:
        await self.websocket.close()


class TrioWebSocketWrapper:
    """Wrapper for Trio WebSocket to match our protocol"""

    def __init__(self, websocket: TrioWebSocket):
        self.websocket = websocket

    async def send_message(self, message: bytes) -> None:
        await self.websocket.send_message(message)

    async def get_message(self) -> bytes:
        return await self.websocket.get_message()

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

        # Wrap the websocket in appropriate adapter
        if isinstance(websocket, StarletteWebSocket):
            self.websocket = StarletteWebSocketWrapper(websocket)
            self.log.debug("Using Starlette WebSocket")
        else:
            self.websocket = TrioWebSocketWrapper(websocket)
            self.log.debug("Using Trio WebSocket")

        # The four tables from the Cap'n Proto RPC protocol
        self.questions = {}  # QuestionId -> ReceiveChannel
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
                message = await self.receive_message()
                self.log.debug(
                    "Received message", message_type=message.which()
                )
                await self.handle_message(message)
        except Exception as e:
            self.log.exception("Error in message loop", error=str(e))
            abort = rpc_capnp.Message.new_message()
            abort_struct = abort.init("abort")
            abort_struct.reason = str(e)
            await self.send_message(abort)
            raise

    async def close(self):
        """Clean up the vat"""
        # Send abort message
        abort = rpc_capnp.Message.new_message()
        abort_struct = abort.init("abort")
        abort_struct.reason = "Vat closing"
        await self.send_message(abort)

        # Close websocket
        await self.websocket.aclose()

    async def bootstrap(self):
        """Get the bootstrap interface from the remote vat"""
        message = rpc_capnp.Message.new_message()
        bootstrap = message.init("bootstrap")
        bootstrap.questionId = self._next_question()

        # Create channel to receive response
        send_channel, receive_channel = trio.open_memory_channel(1)
        self.questions[bootstrap.questionId] = (
            send_channel,
            receive_channel,
        )

        await self.send_message(message)
        self.log.debug("Waiting for bootstrap response")
        result = await receive_channel.receive()
        self.log.debug("Bootstrap response received")

        if isinstance(result, Exception):
            raise result
        return result

    async def call_method(self, target_id, method_id, params):
        """Make an outgoing method call"""
        self.log.debug(
            "Calling remote method",
            target_id=target_id,
            method_id=method_id,
        )
        # Create call message
        message = rpc_capnp.Message.new_message()
        call = message.init("call")
        call.questionId = self._next_question()

        # Set up target
        call.target.importedCap = target_id
        call.methodId = method_id
        call.params = params

        # Create channel to receive response
        send_channel, receive_channel = trio.open_memory_channel(1)
        self.questions[call.questionId] = (send_channel, receive_channel)

        # Send call and await response
        await self.send_message(message)
        self.log.debug("Waiting for call response")
        result = await receive_channel.receive()
        self.log.debug("Call response received")

        if isinstance(result, Exception):
            raise result
        return result

    async def send_message(self, message):
        """Send a message over the websocket"""
        self.log.debug("Sending message", message_type=message.which())
        message_bytes = message.to_bytes()
        await self.websocket.send_message(message_bytes)

    async def receive_message(self):
        """Receive a message from the websocket"""
        message_bytes = await self.websocket.get_message()
        with rpc_capnp.Message.from_bytes(message_bytes) as message:
            return message

    def set_bootstrap_interface(self, interface):
        """Set the bootstrap interface for this vat"""
        self.bootstrap_interface = interface

    async def handle_message(self, message):
        """Handle an incoming RPC message"""

        if message.which() == "unimplemented":
            pass

        elif message.which() == "abort":
            raise Exception(f"Remote aborted: {message.abort}")

        elif message.which() == "bootstrap":
            await self._handle_bootstrap(message.bootstrap)

        elif message.which() == "call":
            await self._handle_call(message.call)

        elif message.which() == "return":
            await self._handle_return(message.__getattr__("return"))

        elif message.which() == "finish":
            await self._handle_finish(message.finish)

        else:
            # For two-party protocol, we don't need resolve/release
            await self._send_unimplemented(message)

    async def _send_unimplemented(self, message):
        """Send an unimplemented message in response to an unsupported message"""
        unimplemented = rpc_capnp.Message.new_message()
        unimplemented.unimplemented = message
        await self.send_message(unimplemented)

    async def _handle_bootstrap(self, bootstrap):
        """Handle a bootstrap message"""
        self.log.debug(
            "Handling bootstrap request", question_id=bootstrap.questionId
        )
        if self.bootstrap_interface is None:
            self.log.warning("No bootstrap interface available")
            return_msg = rpc_capnp.Message.new_message()
            return_struct = return_msg.init("return")
            return_struct.answerId = bootstrap.questionId
            exception = return_struct.init("exception")
            exception.reason = "No bootstrap interface available"
            await self.send_message(return_msg)
            return

        # Create return message with bootstrap capability
        return_msg = rpc_capnp.Message.new_message()
        return_struct = return_msg.init("return")
        return_struct.answerId = bootstrap.questionId

        # Export the bootstrap interface
        export_id = self._next_export()
        self.exports[export_id] = self.bootstrap_interface

        # Set up the results payload with the capability
        results = return_struct.init("results")
        cap_table = results.init("capTable", 1)
        cap = cap_table[0]
        cap.senderHosted = export_id

        await self.send_message(return_msg)

    async def _handle_call(self, call):
        """Handle a method call"""
        self.answers[call.questionId] = None

        try:
            if call.target.which() == "importedCap":
                target = self.exports.get(call.target.importedCap)
                if target is None:
                    raise Exception("Invalid capability")

                # Find the method
                method = None
                for name, m in target._methods.items():
                    if m._method_id == call.methodId:
                        method = getattr(target, name)
                        break

                if method is None:
                    raise Exception(f"Method {call.methodId} not found")

                # Call the method
                result = await method(**call.params.to_dict())

                # Send successful return
                return_msg = rpc_capnp.Message.new_message()
                return_struct = return_msg.init("return")
                return_struct.answerId = call.questionId

                # Pack result into Cap'n Proto format
                results = return_struct.init("results")
                # TODO: Implement proper result packing
                results.content = result

                await self.send_message(return_msg)

            else:
                raise Exception("Unsupported target type")

        except Exception as e:
            # Send error return
            return_msg = rpc_capnp.Message.new_message()
            return_struct = return_msg.init("return")
            return_struct.answerId = call.questionId
            exception = return_struct.init("exception")
            exception.reason = str(e)
            await self.send_message(return_msg)

        finally:
            del self.answers[call.questionId]

    async def _handle_return(self, return_):
        """Handle a return message"""
        self.log.debug(
            "Handling return",
            answer_id=return_.answerId,
            return_type=return_.which(),
        )
        channel = self.questions.get(return_.answerId)
        if channel is None:
            return

        send_channel, receive_channel = channel

        # Send result or exception through channel
        if return_.which() == "results":
            await send_channel.send(return_.results)
        elif return_.which() == "exception":
            await send_channel.send(Exception(return_.exception.reason))

        del self.questions[return_.answerId]

    async def _handle_finish(self, finish):
        """Handle a finish message"""
        if finish.questionId in self.answers:
            del self.answers[finish.questionId]

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

    def export_capability(self, capability: Capability) -> int:
        """Export a capability to be used by other vats"""
        export_id = self._next_export()
        self.log.debug(
            "Exporting capability",
            export_id=export_id,
            capability_type=type(capability).__name__,
        )
        capability._vat = self
        capability._export_id = export_id
        self.exports[export_id] = capability
        return export_id

    def import_capability(
        self, import_id: int, interface_class
    ) -> Capability:
        """Import a capability from another vat"""
        self.log.debug(
            "Importing capability",
            import_id=import_id,
            interface_class=interface_class.__name__,
        )
        cap = RemoteCapability(self, import_id)
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

            rich.inspect(remote_chat)

            # Call methods on it
            await remote_chat.send_message("Hello from client!")
            history = await remote_chat.get_history()
            print(f"Chat history: {history}")


async def main():
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
        chat = ChatRoom(vat)
        vat.set_bootstrap_interface(chat)
        await vat.run()

    import hypercorn
    from hypercorn.trio import serve

    config = hypercorn.Config()
    config.bind = ["localhost:8000"]
    await serve(app, config)  # type: ignore


if __name__ == "__main__":
    import sys

    trio.run(main)
