import inspect
from enum import Enum
from typing import Any, Callable, Dict, Optional, Union, Protocol
from contextlib import asynccontextmanager

import trio
import cbor2
import structlog

from fastapi import WebSocket
from trio_websocket import (
    WebSocketConnection as TrioWebSocket,
    ConnectionClosed as TrioConnectionClosed,
)
from trio_websocket import open_websocket_url
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
    """Represents a capability hosted by another vat connection"""

    def __init__(
        self, connection: "VatConnection", protocol: type[T], import_id: int
    ):
        super().__init__(vat=connection._vat, protocol=protocol)
        self._connection = connection
        self._import_id = import_id

    def __getattr__(self, name):
        async def call_method(*args, **kwargs):
            params = {"args": args, "kwargs": kwargs}
            return await self._call_remote(name, params)

        return call_method

    async def _call_remote(self, method_name: str, params: Any):
        self.log.debug(
            "Calling remote method",
            remote_method_name=method_name,
            params=params,
        )
        m = self._methods.get(method_name)
        if m is None:
            raise Exception(f"Unknown method: {method_name}")

        return await self._connection.call_method(
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
    INTERFACE_ID = 0x1234

    @method(INTERFACE_ID, 0)
    async def send_message(self, content: str) -> None: ...

    @method(INTERFACE_ID, 1)
    async def get_history(self) -> Dict[str, Any]: ...


class ChatRoomImpl(ChatRoom):
    def __init__(self):
        self.history = []

    async def send_message(self, content: str) -> None:
        print(f"Message received: {content}")
        self.history.append(content)

    async def get_history(self):
        return {"messages": self.history}


class Side(Enum):
    SERVER = "server"
    CLIENT = "client"


class WebSocketAdapter(Protocol):
    async def send_message(self, message: bytes) -> None: ...
    async def get_message(self) -> bytes: ...
    async def aclose(self) -> None: ...


class WebSocketClosed(Exception):
    pass


class StarletteWebSocketWrapper:
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
    """A vat is a collection of objects and their capabilities, independent of connections."""

    def __init__(self):
        self.log = logger.bind(side="server_vat")
        self.log.info("Creating shared vat")
        self.bootstrap_interface = None

    def set_bootstrap_interface(self, interface: LocalCapability):
        self.bootstrap_interface = interface


class VatConnection:
    def __init__(
        self,
        vat: Vat,
        websocket: Union[StarletteWebSocket, TrioWebSocket],
        side: Side,
    ):
        self._vat = vat
        self.log = logger.bind(side=side)
        self.log.info("Creating vat connection")

        self._closing = False

        if isinstance(websocket, StarletteWebSocket):
            self.websocket = StarletteWebSocketWrapper(websocket)
        else:
            self.websocket = TrioWebSocketWrapper(websocket)

        self.questions = {}
        self.answers = {}
        self.exports = {}  # export_id -> LocalCapability
        self.imports = {}  # import_id -> RemoteCapability

        self._next_question_id = 0
        self._next_export_id = 0

        self.side = side

    async def run(self):
        self.log.info("Starting vat connection message loop")
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
        self._closing = True
        await self.websocket.aclose()

    async def bootstrap(self):
        qid = self._next_question()
        message = {"type": "bootstrap", "questionId": qid}
        return await self.ask_question(message)

    async def call_method(self, target_id, interface_id, method_id, params):
        self.log.debug(
            "Calling remote method",
            target_id=target_id,
            interface_id=interface_id,
            method_id=method_id,
        )
        qid = self._next_question()

        # Encode params including capabilities
        cap_table = []
        encoded_params = self.encode_value(params, cap_table)

        message = {
            "type": "call",
            "questionId": qid,
            "target": {"importedCap": target_id},
            "interfaceId": interface_id,
            "methodId": method_id,
            "params": encoded_params,
        }
        if cap_table:
            message["capTable"] = cap_table

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
        self.log.debug("Sending message", message_type=message.get("type"))
        message_bytes = cbor2.dumps(message)
        await self.websocket.send_message(message_bytes)

    async def receive_message(self):
        message_bytes = await self.websocket.get_message()
        message = cbor2.loads(message_bytes)
        return message

    async def handle_message(self, message):
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
            await self._send_unimplemented(message)

    async def _send_unimplemented(self, message):
        unimplemented = {"type": "unimplemented", "original": message}
        await self.send_message(unimplemented)

    async def _handle_bootstrap(self, message):
        qid = message["questionId"]
        if self._vat.bootstrap_interface is None:
            self.log.warning("No bootstrap interface available")
            return_msg = {
                "type": "return",
                "answerId": qid,
                "exception": {"reason": "No bootstrap interface available"},
            }
            await self.send_message(return_msg)
            return

        export_id = self._next_export()
        self.exports[export_id] = self._vat.bootstrap_interface
        return_msg = {
            "type": "return",
            "answerId": qid,
            "capTable": [{"senderHosted": export_id}],
            "results": {
                "capRef": 0
            },  # The bootstrap capability is the first in capTable
        }
        await self.send_message(return_msg)

    async def _handle_call(self, message):
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
                cap_table = message.get("capTable", [])
                encoded_params = message.get("params", {})

                # Decode params (replace capRefs)
                params = self.decode_value(encoded_params, cap_table)

                assert isinstance(params, dict)

                # Find the method
                m = None
                for name, meth in target._methods.items():
                    if (
                        meth._method_id == method_id
                        and meth._interface_id == interface_id
                    ):
                        m = getattr(target, name)
                        break

                if m is None:
                    raise Exception(f"Method {method_id} not found")

                args = params.get("args", [])
                kwargs = params.get("kwargs", {})
                result = await m(*args, **kwargs)

                # Encode result (including capabilities)
                result_cap_table = []
                encoded_result = self.encode_value(result, result_cap_table)

                return_msg = {
                    "type": "return",
                    "answerId": qid,
                    "results": encoded_result,
                }
                if result_cap_table:
                    return_msg["capTable"] = result_cap_table
                await self.send_message(return_msg)
            else:
                raise Exception("Unsupported target type")

        except Exception as e:
            return_msg = {
                "type": "return",
                "answerId": qid,
                "exception": {"reason": str(e)},
            }
            await self.send_message(return_msg)
        finally:
            del self.answers[qid]

    async def _handle_return(self, message):
        answer_id = message["answerId"]
        cap_table = message.get("capTable", [])
        channel = self.questions.get(answer_id)
        if channel is None:
            return

        send_channel, receive_channel = channel

        if "results" in message:
            decoded_results = self.decode_value(
                message["results"], cap_table
            )
            await send_channel.send(decoded_results)
        elif "exception" in message:
            await send_channel.send(
                Exception(message["exception"]["reason"])
            )

        del self.questions[answer_id]

    async def _handle_finish(self, message):
        qid = message["questionId"]
        if qid in self.answers:
            del self.answers[qid]

    def _next_question(self):
        qid = self._next_question_id
        self._next_question_id += 1
        return qid

    def _next_export(self):
        eid = self._next_export_id
        self._next_export_id += 1
        return eid

    def export_capability(self, capability: LocalCapability) -> int:
        export_id = self._next_export()
        self.exports[export_id] = capability
        return export_id

    def import_capability(
        self, import_id: int, protocol: Optional[type] = None
    ) -> Any:
        # Here we assume protocol known or a default
        # In a real system, you'd have a registry mapping interface IDs to protocol classes
        if protocol is None:
            # Use a default protocol or handle differently
            protocol = ChatRoom
        cap = RemoteCapability(self, protocol, import_id)
        self.imports[import_id] = cap
        return cap

    def encode_value(self, value, cap_table):
        """Recursively encode values.
        If a capability is found, export/import it and replace with {"capRef": index}."""
        if isinstance(value, dict):
            return {
                k: self.encode_value(v, cap_table) for k, v in value.items()
            }
        elif isinstance(value, list):
            return [self.encode_value(v, cap_table) for v in value]
        elif isinstance(value, tuple):
            return [self.encode_value(v, cap_table) for v in value]
        elif isinstance(value, LocalCapability):
            # Export this capability
            eid = self.export_capability(value)
            index = len(cap_table)
            cap_table.append({"senderHosted": eid})
            return {"capRef": index}
        elif isinstance(value, RemoteCapability):
            # This capability was imported from the other side; reference its import_id
            index = len(cap_table)
            cap_table.append({"importedCap": value._import_id})
            return {"capRef": index}
        else:
            return value

    def decode_value(self, value, cap_table):
        """Recursively decode values. If {"capRef": n} is found, replace with a capability."""
        if isinstance(value, dict):
            if "capRef" in value:
                ref_index = value["capRef"]
                cap_entry = cap_table[ref_index]
                # Determine if this is senderHosted or importedCap
                if "senderHosted" in cap_entry:
                    # The remote side hosts this capability; we must import it
                    eid = cap_entry["senderHosted"]
                    # Import as a remote capability
                    return self.import_capability(eid)
                elif "importedCap" in cap_entry:
                    # This references a capability we previously exported and now is being sent back?
                    # Actually, if "importedCap" is seen on decoding, that means the remote references
                    # a capability that we originally exported or they imported from us.
                    # For simplicity, treat it the same as senderHosted but reversed.
                    # In a real system, you'd handle differently. Here we just import again:
                    iid = cap_entry["importedCap"]
                    return self.import_capability(iid)
                else:
                    raise Exception("Unknown capRef type")
            else:
                # decode recursively
                return {
                    k: self.decode_value(v, cap_table)
                    for k, v in value.items()
                }
        elif isinstance(value, list):
            return [self.decode_value(v, cap_table) for v in value]
        else:
            return value


@asynccontextmanager
async def connect_vat(url: str):
    logger.info("Connecting to remote vat", url=url)
    async with open_websocket_url(url) as websocket:
        vat = Vat()
        connection = VatConnection(vat, websocket, Side.CLIENT)
        try:
            yield connection
        finally:
            logger.info("Closing vat connection")
            await connection.close()


async def client_example():
    async with trio.open_nursery() as nursery:
        async with connect_vat("ws://localhost:8000/ws") as connection:
            nursery.start_soon(connection.run)
            remote_chat = await connection.bootstrap()

            # remote_chat might contain a capRef referring to a capability in the capTable
            # decode_value is already called for results in _handle_return
            # so we have the real object now
            # Assuming remote_chat is a capability
            if isinstance(remote_chat, RemoteCapability):
                await remote_chat.send_message("Hello from client!")
                history = await remote_chat.get_history()
                print(f"Chat history: {history}")
                await trio.sleep(3)
            else:
                print("No bootstrap capability returned.")


async def main():
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "client":
        await client_example()
        return

    from fastapi import FastAPI

    app = FastAPI()

    vat = Vat()
    chat_impl = ChatRoomImpl()
    vat.set_bootstrap_interface(LocalCapability(vat, ChatRoom, chat_impl))

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        connection = VatConnection(vat, websocket, Side.SERVER)
        await connection.run()

    import hypercorn
    from hypercorn.trio import serve

    config = hypercorn.Config()
    config.bind = ["localhost:8000"]
    await serve(app, config)  # type: ignore


if __name__ == "__main__":
    trio.run(main)
