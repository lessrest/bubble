import inspect
import uuid
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
            "Invoking remote method",
            connection_id=self._connection.connection_id,
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


class ChatRoom(Protocol):
    INTERFACE_ID = 0x1234

    @method(INTERFACE_ID, 0)
    async def send_message(self, content: str) -> None: ...

    @method(INTERFACE_ID, 1)
    async def get_history(self) -> Dict[str, Any]: ...


class ChatRoomImpl(ChatRoom):
    def __init__(self, room_name: str):
        self.history = []
        self.name = room_name
        self.log = logger.bind(room=self.name)

    async def send_message(self, content: str) -> None:
        self.log.info("Message received in chat room", content=content)
        self.history.append(content)

    async def get_history(self):
        self.log.debug("Returning chat history")
        return {"messages": self.history, "room": self.name}


class RoomFactory(Protocol):
    INTERFACE_ID = 0x2345

    @method(INTERFACE_ID, 0)
    async def create_room(self, name: str) -> ChatRoom: ...


class RoomFactoryImpl(RoomFactory):
    def __init__(self, vat: "Vat"):
        self.vat = vat
        self.log = logger.bind(factory="RoomFactory")

    async def create_room(self, name: str) -> LocalCapability[ChatRoom]:
        self.log.info("Creating new chat room", room_name=name)
        chat_impl = ChatRoomImpl(name)
        return LocalCapability(self.vat, ChatRoom, chat_impl)


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
        self.log = logger.bind(component="vat")
        self.log.info("Creating shared vat")
        self.bootstrap_interface = None
        self.protocol_registry: Dict[int, type] = {}

    def set_bootstrap_interface(self, interface: LocalCapability):
        self.log.info(
            "Setting bootstrap interface",
            interface=interface._protocol.__name__,
        )
        self.bootstrap_interface = interface

    def register_protocol(self, interface_id: int, protocol: type):
        self.log.debug(
            "Registering protocol",
            interface_id=hex(interface_id),
            protocol=protocol.__name__,
        )
        self.protocol_registry[interface_id] = protocol

    def lookup_protocol(self, interface_id: int) -> Optional[type]:
        proto = self.protocol_registry.get(interface_id)
        if proto:
            self.log.debug(
                "Protocol found",
                interface_id=hex(interface_id),
                protocol=proto.__name__,
            )
        else:
            self.log.warning(
                "Protocol not found", interface_id=hex(interface_id)
            )
        return proto


class VatConnection:
    def __init__(
        self,
        vat: Vat,
        websocket: Union[StarletteWebSocket, TrioWebSocket],
        side: Side,
    ):
        self._vat = vat
        self.connection_id = str(uuid.uuid4())[:8]
        self.side = side
        self.log = logger.bind(
            side=side.value, connection_id=self.connection_id
        )
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

    async def run(self):
        self.log.info("Starting vat connection message loop")
        try:
            while True:
                try:
                    message = await self.receive_message()
                except WebSocketClosed:
                    if self._closing:
                        self.log.info("WebSocket closed intentionally")
                        break
                    else:
                        if (
                            self.side == Side.SERVER
                            and len(self.questions) == 0
                        ):
                            self.log.info(
                                "Client disconnected with no pending questions"
                            )
                            break
                        raise

                if message is None:
                    self.log.debug("No more messages; ending loop")
                    break

                msg_type = message.get("type")
                self.log.debug("Message received", message_type=msg_type)
                await self.handle_message(message)
        except Exception as e:
            self.log.exception(
                "Error encountered during message loop", error=str(e)
            )
            abort = {"type": "abort", "reason": str(e)}
            await self.send_message(abort)
            raise

    async def close(self):
        self.log.info("Closing vat connection")
        self._closing = True
        await self.websocket.aclose()

    async def bootstrap(self):
        qid = self._next_question()
        message = {"type": "bootstrap", "questionId": qid}
        self.log.debug("Sending bootstrap request", question_id=qid)
        return await self.ask_question(message)

    async def call_method(self, target_id, interface_id, method_id, params):
        self.log.debug(
            "Calling remote method",
            target_id=target_id,
            interface_id=hex(interface_id),
            method_id=method_id,
            params=params,
        )
        qid = self._next_question()

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
        self.log.debug("Waiting for response", question_id=qid)
        result = await receive_channel.receive()
        self.log.debug("Response received", question_id=qid)
        if isinstance(result, Exception):
            self.log.warning(
                "Remote returned exception",
                question_id=qid,
                error=str(result),
            )
            raise result
        return result

    async def send_message(self, message):
        msg_type = message.get("type")
        self.log.debug("Sending message", message_type=msg_type)
        message_bytes = cbor2.dumps(message)
        await self.websocket.send_message(message_bytes)

    async def receive_message(self):
        try:
            message_bytes = await self.websocket.get_message()
        except WebSocketClosed:
            self.log.info("WebSocket closed during receive")
            return None

        message = cbor2.loads(message_bytes)
        return message

    async def handle_message(self, message):
        msg_type = message.get("type")

        if msg_type == "unimplemented":
            self.log.warning("Received 'unimplemented' message from remote")
            # Not much to do here

        elif msg_type == "abort":
            reason = message.get("reason", "Unknown")
            self.log.error("Remote aborted connection", reason=reason)
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
            self.log.warning(
                "Received unknown message type", message_type=msg_type
            )
            await self._send_unimplemented(message)

    async def _send_unimplemented(self, message):
        self.log.debug("Sending unimplemented response")
        unimplemented = {"type": "unimplemented", "original": message}
        await self.send_message(unimplemented)

    async def _handle_bootstrap(self, message):
        qid = message["questionId"]
        self.log.debug("Handling bootstrap request", question_id=qid)
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
        self.log.info("Providing bootstrap capability", export_id=export_id)
        return_msg = {
            "type": "return",
            "answerId": qid,
            "capTable": [
                {
                    "senderHosted": export_id,
                    "interfaceId": self._vat.bootstrap_interface._protocol.INTERFACE_ID,
                }
            ],
            "results": {"capRef": 0},
        }
        await self.send_message(return_msg)

    async def _handle_call(self, message):
        qid = message["questionId"]
        interface_id = message.get("interfaceId")
        method_id = message.get("methodId")
        self.answers[qid] = None
        self.log.debug(
            "Handling call",
            question_id=qid,
            interface_id=hex(interface_id) if interface_id else None,
            method_id=method_id,
        )
        try:
            target_info = message["target"]
            if "importedCap" in target_info:
                cap_id = target_info["importedCap"]
                target = self.exports.get(cap_id)
                if target is None:
                    raise Exception("Invalid capability")

                cap_table = message.get("capTable", [])
                encoded_params = message.get("params", {})
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
                self.log.debug(
                    "Invoking local method",
                    question_id=qid,
                    local_method_name=m.__name__,
                    args=args,
                    kwargs=kwargs,
                )
                result = await m(*args, **kwargs)

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
            self.log.exception(
                "Error handling call", question_id=qid, error=str(e)
            )
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
        self.log.debug("Handling return", answer_id=answer_id)
        channel = self.questions.get(answer_id)
        if channel is None:
            self.log.warning(
                "No pending question for answer", answer_id=answer_id
            )
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
        self.log.debug("Handling finish", question_id=qid)
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
        eid = self._next_export()
        self.exports[eid] = capability
        self.log.debug(
            "Exporting capability",
            export_id=eid,
            protocol=capability._protocol.__name__,
        )
        return eid

    def import_capability(self, import_id: int, interface_id: int) -> Any:
        protocol = self._vat.lookup_protocol(interface_id)
        if protocol is None:
            raise Exception(
                f"No known protocol for interface_id: {interface_id}"
            )
        cap = RemoteCapability(self, protocol, import_id)
        self.imports[import_id] = cap
        self.log.debug(
            "Importing capability",
            import_id=import_id,
            protocol=protocol.__name__,
        )
        return cap

    def encode_value(self, value, cap_table):
        if isinstance(value, dict):
            return {
                k: self.encode_value(v, cap_table) for k, v in value.items()
            }
        elif isinstance(value, list):
            return [self.encode_value(v, cap_table) for v in value]
        elif isinstance(value, tuple):
            return [self.encode_value(v, cap_table) for v in value]
        elif isinstance(value, LocalCapability):
            eid = self.export_capability(value)
            index = len(cap_table)
            cap_table.append(
                {
                    "senderHosted": eid,
                    "interfaceId": value._protocol.INTERFACE_ID,
                }
            )
            return {"capRef": index}
        elif isinstance(value, RemoteCapability):
            index = len(cap_table)
            cap_table.append(
                {
                    "importedCap": value._import_id,
                    "interfaceId": value._protocol.INTERFACE_ID,
                }
            )
            return {"capRef": index}
        else:
            return value

    def decode_value(self, value, cap_table):
        if isinstance(value, dict):
            if "capRef" in value:
                ref_index = value["capRef"]
                cap_entry = cap_table[ref_index]
                interface_id = cap_entry["interfaceId"]
                if "senderHosted" in cap_entry:
                    eid = cap_entry["senderHosted"]
                    return self.import_capability(eid, interface_id)
                elif "importedCap" in cap_entry:
                    iid = cap_entry["importedCap"]
                    return self.import_capability(iid, interface_id)
                else:
                    raise Exception("Unknown capRef type")
            else:
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
        vat.register_protocol(ChatRoom.INTERFACE_ID, ChatRoom)
        vat.register_protocol(RoomFactory.INTERFACE_ID, RoomFactory)
        connection = VatConnection(vat, websocket, Side.CLIENT)
        try:
            yield connection
        finally:
            logger.info(
                "Closing vat connection to remote",
                connection_id=connection.connection_id,
            )
            await connection.close()


async def client_example():
    async with trio.open_nursery() as nursery:
        async with connect_vat("ws://localhost:8000/ws") as connection:
            nursery.start_soon(connection.run)
            remote_factory = await connection.bootstrap()
            if isinstance(remote_factory, RemoteCapability):
                new_room = await remote_factory.create_room("TestRoom1")
                await new_room.send_message("Hello from client!")
                history = await new_room.get_history()
                logger.info("Received chat history", history=history)

                await trio.sleep(1)
                another_room = await remote_factory.create_room("TestRoom2")
                await another_room.send_message("Hello second room!")
                history2 = await another_room.get_history()
                logger.info(
                    "Received second room history", history=history2
                )
                await trio.sleep(3)
            else:
                logger.warning("No bootstrap capability returned.")


async def main():
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "client":
        await client_example()
        return

    from fastapi import FastAPI

    app = FastAPI()

    vat = Vat()
    vat.register_protocol(ChatRoom.INTERFACE_ID, ChatRoom)
    vat.register_protocol(RoomFactory.INTERFACE_ID, RoomFactory)

    factory_impl = RoomFactoryImpl(vat)
    vat.set_bootstrap_interface(
        LocalCapability(vat, RoomFactory, factory_impl)
    )

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
