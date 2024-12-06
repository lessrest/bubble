import inspect
import uuid
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    Union,
    Protocol,
    List,
    overload,
)
from contextlib import asynccontextmanager

import trio
import cbor2
import structlog
from pydantic import BaseModel, Field

from fastapi import FastAPI, WebSocket
from starlette.websockets import (
    WebSocketDisconnect as StarletteConnectionClosed,
)

from trio_websocket import (
    WebSocketConnection as TrioWebSocket,
    ConnectionClosed as TrioConnectionClosed,
    open_websocket_url,
)

logger = structlog.stdlib.get_logger()


############################################################
# RPC Method Decorator & Capability References
############################################################


def remote_method(interface_id: int, method_id: int) -> Callable[..., Any]:
    """Decorator to mark methods as remotely callable."""

    def decorator(func):
        func._is_capability_method = True
        func._interface_id = interface_id
        func._method_id = method_id
        return func

    return decorator


class CapabilityReference:
    """Base class for capability references (local or remote)."""

    def __init__(self, vat: "CapabilityVat", protocol: type):
        self.log = logger.bind(capability_type=protocol.__name__)
        self._vat = vat
        self._protocol = protocol
        self._methods = {
            name: method
            for name, method in inspect.getmembers(protocol)
            if hasattr(method, "_is_capability_method")
        }


class RemoteServiceProxy(CapabilityReference):
    """A proxy to a capability hosted by a remote vat connection."""

    def __init__(
        self,
        connection: "CapabilityConnection",
        protocol: type,
        import_id: int,
    ):
        super().__init__(vat=connection._vat, protocol=protocol)
        self._connection = connection
        self._import_id = import_id

    def __getattr__(self, name):
        """Dynamically create async methods that invoke remote calls."""

        async def call_remote_method(*args, **kwargs):
            params = {"args": args, "kwargs": kwargs}
            return await self._call_remote(name, params)

        return call_remote_method

    async def _call_remote(self, method_name: str, params: Any):
        self.log.debug(
            "Invoking remote method",
            connection_id=self._connection.connection_id,
            remote_method_name=method_name,
            params=params,
        )
        method = self._methods.get(method_name)
        if method is None:
            raise Exception(f"Unknown method: {method_name}")
        return await self._connection.call_method(
            target_id=self._import_id,
            interface_id=method._interface_id,
            method_id=method._method_id,
            params=params,
        )


class LocalServiceInstance(CapabilityReference):
    """Represents a capability hosted by this vat (local implementation)."""

    def __init__(self, vat: "CapabilityVat", protocol: type, instance: Any):
        super().__init__(vat=vat, protocol=protocol)
        self._instance = instance

    def __getattr__(self, name):
        return getattr(self._instance, name)


############################################################
# Example Protocol and Services
############################################################


class ChatRoomProtocol(Protocol):
    INTERFACE_ID = 0x1234

    @remote_method(INTERFACE_ID, 0)
    async def send_message(self, content: str) -> None: ...

    @remote_method(INTERFACE_ID, 1)
    async def get_history(self) -> Dict[str, Any]: ...


class ChatRoomService(ChatRoomProtocol):
    def __init__(self, room_name: str):
        self.history: List[str] = []
        self.name = room_name
        self.log = logger.bind(room=self.name)

    async def send_message(self, content: str) -> None:
        self.log.info("Message received", content=content)
        self.history.append(content)

    async def get_history(self) -> Dict[str, Any]:
        self.log.debug("Returning chat history")
        return {"messages": self.history, "room": self.name}


class RoomFactoryProtocol(Protocol):
    INTERFACE_ID = 0x2345

    @remote_method(INTERFACE_ID, 0)
    async def create_room(self, name: str) -> ChatRoomProtocol: ...


class RoomFactoryService(RoomFactoryProtocol):
    def __init__(self, vat: "CapabilityVat"):
        self.vat = vat
        self.log = logger.bind(factory="RoomFactory")

    async def create_room(self, name: str) -> LocalServiceInstance:
        self.log.info("Creating new chat room", room_name=name)
        chat_impl = ChatRoomService(name)
        return LocalServiceInstance(self.vat, ChatRoomProtocol, chat_impl)


############################################################
# Messages and Pydantic Models
############################################################


class MessageType(str, Enum):
    UNIMPLEMENTED = "unimplemented"
    ABORT = "abort"
    BOOTSTRAP = "bootstrap"
    CALL = "call"
    RETURN = "return"
    FINISH = "finish"


class CapRefEntry(BaseModel):
    interfaceId: int
    senderHosted: Optional[int] = None
    importedCap: Optional[int] = None


class BaseMessage(BaseModel):
    type: MessageType

    class Config:
        allow_extra = True


class UnimplementedMessage(BaseMessage):
    type: MessageType = MessageType.UNIMPLEMENTED
    original: dict


class AbortMessage(BaseMessage):
    type: MessageType = MessageType.ABORT
    reason: str


class BootstrapMessage(BaseMessage):
    type: MessageType = MessageType.BOOTSTRAP
    questionId: int


class CallMessage(BaseMessage):
    type: MessageType = MessageType.CALL
    questionId: int
    target: dict
    interfaceId: int
    methodId: int
    params: dict = Field(default_factory=dict)
    capTable: List[CapRefEntry] = Field(default_factory=list)


class ReturnMessage(BaseMessage):
    type: MessageType = MessageType.RETURN
    answerId: int
    results: Optional[dict] = None
    exception: Optional[dict] = None
    capTable: List[CapRefEntry] = Field(default_factory=list)


class FinishMessage(BaseMessage):
    type: MessageType = MessageType.FINISH
    questionId: int


############################################################
# WebSocket Adapters
############################################################


class WebSocketClosed(Exception):
    pass


class WebSocketAdapter(Protocol):
    async def send_message(self, message: bytes) -> None: ...
    async def get_message(self) -> bytes: ...
    async def aclose(self) -> None: ...


class StarletteWebSocketWrapper(WebSocketAdapter):
    def __init__(self, websocket: WebSocket):
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


class TrioWebSocketWrapper(WebSocketAdapter):
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


############################################################
# The Vat and Connection
############################################################


class CapabilityVat:
    """
    A CapabilityVat is a container for capabilities and their implementations.
    It holds a registry of interface_ids to protocol classes and may have a bootstrap capability.
    """

    def __init__(self):
        self.log = logger.bind(component="vat")
        self.log.info("Creating shared vat")
        self.bootstrap_interface: Optional[LocalServiceInstance] = None
        self.protocol_registry: Dict[int, type] = {}

    def set_bootstrap_interface(self, interface: LocalServiceInstance):
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


class CapabilityConnection:
    """
    Represents a connection between vats for capability-based RPC.
    Handles sending/receiving messages and maintaining capability references.
    """

    def __init__(
        self,
        vat: CapabilityVat,
        websocket: Union[WebSocket, TrioWebSocket],
        side: "Side",
    ):
        self._vat = vat
        self.connection_id = str(uuid.uuid4())[:8]
        self.side = side
        self.log = logger.bind(
            side=side.value, connection_id=self.connection_id
        )
        self.log.info("Creating vat connection")

        self._closing = False

        if isinstance(websocket, WebSocket):
            self.websocket = StarletteWebSocketWrapper(websocket)
        else:
            self.websocket = TrioWebSocketWrapper(websocket)

        self.questions: Dict[int, Any] = {}
        self.answers: Dict[int, Any] = {}
        self.exports: Dict[int, LocalServiceInstance] = {}
        self.imports: Dict[int, RemoteServiceProxy] = {}
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

                self.log.debug(
                    "Message received", message_type=message.get("type")
                )
                await self.handle_raw_message(message)
        except Exception as e:
            self.log.exception(
                "Error encountered during message loop", error=str(e)
            )
            abort = AbortMessage(reason=str(e))
            await self.send_message(abort.model_dump())
            raise

    async def close(self):
        self.log.info("Closing vat connection")
        self._closing = True
        await self.websocket.aclose()

    async def bootstrap(self):
        qid = self._next_question()
        msg = BootstrapMessage(questionId=qid)
        self.log.debug("Sending bootstrap request", question_id=qid)
        return await self.ask_question(msg.model_dump())

    async def call_method(
        self,
        target_id: int,
        interface_id: int,
        method_id: int,
        params: dict,
    ):
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
        msg = CallMessage(
            questionId=qid,
            target={"importedCap": target_id},
            interfaceId=interface_id,
            methodId=method_id,
            params=encoded_params,
            capTable=[CapRefEntry(**c) for c in cap_table],
        )
        return await self.ask_question(msg.model_dump())

    async def ask_question(self, message: dict):
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

    async def send_message(self, message: dict):
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

    async def handle_raw_message(self, message: dict):
        msg_type = message.get("type")
        if msg_type == MessageType.UNIMPLEMENTED.value:
            # Just log this, typically
            self.log.warning("Received 'unimplemented' message from remote")

        elif msg_type == MessageType.ABORT.value:
            msg = AbortMessage(**message)
            self.log.error("Remote aborted connection", reason=msg.reason)
            raise Exception(f"Remote aborted: {msg.reason}")

        elif msg_type == MessageType.BOOTSTRAP.value:
            msg = BootstrapMessage(**message)
            await self._handle_bootstrap(msg)

        elif msg_type == MessageType.CALL.value:
            msg = CallMessage(**message)
            await self._handle_call(msg)

        elif msg_type == MessageType.RETURN.value:
            msg = ReturnMessage(**message)
            await self._handle_return(msg)

        elif msg_type == MessageType.FINISH.value:
            msg = FinishMessage(**message)
            await self._handle_finish(msg)

        else:
            self.log.warning(
                "Received unknown message type", message_type=msg_type
            )
            unimpl = UnimplementedMessage(original=message)
            await self.send_message(unimpl.model_dump())

    async def _handle_bootstrap(self, message: BootstrapMessage):
        qid = message.questionId
        self.log.debug("Handling bootstrap request", question_id=qid)
        if self._vat.bootstrap_interface is None:
            self.log.warning("No bootstrap interface available")
            return_msg = ReturnMessage(
                answerId=qid,
                exception={"reason": "No bootstrap interface available"},
            )
            await self.send_message(return_msg.model_dump())
            return

        export_id = self._next_export()
        self.exports[export_id] = self._vat.bootstrap_interface
        self.log.info("Providing bootstrap capability", export_id=export_id)
        return_msg = ReturnMessage(
            answerId=qid,
            capTable=[
                CapRefEntry(
                    interfaceId=self._vat.bootstrap_interface._protocol.INTERFACE_ID,
                    senderHosted=export_id,
                )
            ],
            results={"capRef": 0},
        )
        await self.send_message(return_msg.model_dump())

    async def _handle_call(self, message: CallMessage):
        qid = message.questionId
        self.answers[qid] = None
        self.log.debug(
            "Handling call",
            question_id=qid,
            interface_id=hex(message.interfaceId),
            method_id=message.methodId,
        )
        try:
            target_info = message.target
            if "importedCap" in target_info:
                cap_id = target_info["importedCap"]
                target = self.exports.get(cap_id)
                if target is None:
                    raise Exception("Invalid capability")

                cap_table = [
                    entry.model_dump() for entry in message.capTable
                ]
                params = self.decode_value(message.params, cap_table)

                assert isinstance(params, dict)

                # Find the method
                m = None
                for name, meth in target._methods.items():
                    if (
                        meth._method_id == message.methodId
                        and meth._interface_id == message.interfaceId
                    ):
                        m = getattr(target, name)
                        break

                if m is None:
                    raise Exception(f"Method {message.methodId} not found")

                args = params.get("args", [])
                kwargs = params.get("kwargs", {})
                self.log.debug(
                    "Invoking local method",
                    question_id=qid,
                    method=m.__name__,
                    args=args,
                    kwargs=kwargs,
                )
                result = await m(*args, **kwargs)

                result_cap_table = []
                encoded_result = self.encode_value(result, result_cap_table)

                return_msg = ReturnMessage(
                    answerId=qid,
                    results=encoded_result,
                    capTable=[CapRefEntry(**c) for c in result_cap_table]
                    if result_cap_table
                    else [],
                )
                await self.send_message(return_msg.model_dump())
            else:
                raise Exception("Unsupported target type")

        except Exception as e:
            self.log.exception(
                "Error handling call", question_id=qid, error=str(e)
            )
            return_msg = ReturnMessage(
                answerId=qid, exception={"reason": str(e)}
            )
            await self.send_message(return_msg.model_dump())
        finally:
            if qid in self.answers:
                del self.answers[qid]

    async def _handle_return(self, message: ReturnMessage):
        answer_id = message.answerId
        self.log.debug("Handling return", answer_id=answer_id)
        channel = self.questions.get(answer_id)
        if channel is None:
            self.log.warning(
                "No pending question for answer", answer_id=answer_id
            )
            return

        send_channel, receive_channel = channel

        if message.results is not None:
            decoded_results = self.decode_value(
                message.results, [c.model_dump() for c in message.capTable]
            )
            await send_channel.send(decoded_results)
        elif message.exception is not None:
            await send_channel.send(Exception(message.exception["reason"]))

        del self.questions[answer_id]

    async def _handle_finish(self, message: FinishMessage):
        qid = message.questionId
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

    def export_capability(self, capability: LocalServiceInstance) -> int:
        eid = self._next_export()
        self.exports[eid] = capability
        self.log.debug(
            "Exporting capability",
            export_id=eid,
            protocol=capability._protocol.__name__,
        )
        return eid

    def import_capability(
        self, import_id: int, interface_id: int
    ) -> RemoteServiceProxy:
        protocol = self._vat.lookup_protocol(interface_id)
        if protocol is None:
            raise Exception(
                f"No known protocol for interface_id: {interface_id}"
            )
        cap = RemoteServiceProxy(self, protocol, import_id)
        self.imports[import_id] = cap
        self.log.debug(
            "Importing capability",
            import_id=import_id,
            protocol=protocol.__name__,
        )
        return cap

    @overload
    def encode_value(self, value: dict, caps: list[dict]) -> dict: ...

    @overload
    def encode_value(self, value: list, caps: list[dict]) -> list: ...

    @overload
    def encode_value(self, value: int, caps: list[dict]) -> int: ...

    @overload
    def encode_value(self, value: str, caps: list[dict]) -> str: ...

    @overload
    def encode_value(self, value: float, caps: list[dict]) -> float: ...

    @overload
    def encode_value(
        self, value: LocalServiceInstance, caps: list[dict]
    ) -> dict: ...

    @overload
    def encode_value(
        self, value: RemoteServiceProxy, caps: list[dict]
    ) -> dict: ...

    def encode_value(
        self,
        value: dict
        | list
        | int
        | str
        | float
        | LocalServiceInstance
        | RemoteServiceProxy,
        caps: list[dict],
    ) -> dict | list | int | str | float:
        """Recursively encode values for transmission, exporting capabilities."""
        if isinstance(value, dict):
            return {k: self.encode_value(v, caps) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.encode_value(v, caps) for v in value]
        elif isinstance(value, LocalServiceInstance):
            eid = self.export_capability(value)
            index = len(caps)
            caps.append(
                {
                    "senderHosted": eid,
                    "interfaceId": value._protocol.INTERFACE_ID,
                }
            )
            return {"capRef": index}
        elif isinstance(value, RemoteServiceProxy):
            index = len(caps)
            caps.append(
                {
                    "importedCap": value._import_id,
                    "interfaceId": value._protocol.INTERFACE_ID,
                }
            )
            return {"capRef": index}
        else:
            return value

    def decode_value(
        self, value, cap_table
    ) -> (
        RemoteServiceProxy | dict[Any, Any] | list[Any] | int | str | float
    ):
        """Recursively decode values from received messages, importing capabilities."""
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


class Side(Enum):
    SERVER = "server"
    CLIENT = "client"


############################################################
# Client connection helper and example
############################################################


@asynccontextmanager
async def connect_vat(url: str):
    logger.info("Connecting to remote vat", url=url)
    async with open_websocket_url(url) as websocket:
        vat = CapabilityVat()
        vat.register_protocol(
            ChatRoomProtocol.INTERFACE_ID, ChatRoomProtocol
        )
        vat.register_protocol(
            RoomFactoryProtocol.INTERFACE_ID, RoomFactoryProtocol
        )
        connection = CapabilityConnection(vat, websocket, Side.CLIENT)
        try:
            yield connection
        finally:
            logger.info(
                "Closing vat connection",
                connection_id=connection.connection_id,
            )
            await connection.close()


async def client_example():
    async with trio.open_nursery() as nursery:
        async with connect_vat("ws://localhost:8000/ws") as connection:
            nursery.start_soon(connection.run)
            remote_factory = await connection.bootstrap()
            if isinstance(remote_factory, RemoteServiceProxy):
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


############################################################
# Main entrypoint - server
############################################################


async def main():
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "client":
        await client_example()
        return

    app = FastAPI()
    vat = CapabilityVat()
    vat.register_protocol(ChatRoomProtocol.INTERFACE_ID, ChatRoomProtocol)
    vat.register_protocol(
        RoomFactoryProtocol.INTERFACE_ID, RoomFactoryProtocol
    )

    factory_impl = RoomFactoryService(vat)
    vat.set_bootstrap_interface(
        LocalServiceInstance(vat, RoomFactoryProtocol, factory_impl)
    )

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        connection = CapabilityConnection(vat, websocket, Side.SERVER)
        await connection.run()

    import hypercorn
    from hypercorn.trio import serve

    config = hypercorn.Config()
    config.bind = ["localhost:8000"]
    await serve(app, config)  # type: ignore


if __name__ == "__main__":
    trio.run(main)
