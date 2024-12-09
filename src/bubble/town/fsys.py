from pydantic import BaseModel
from bubble.town.town import (
    Actor,
    ActorContext,
    ActorHttpRequest,
    HttpResponseData,
)

from starlette.types import Message

import trio
from rdflib import URIRef
from starlette.responses import JSONResponse


class FSRequest(BaseModel):
    """
    A general request format to the filesystem actors.
    You can customize this as needed.
    """

    action: str  # e.g. "list", "open"
    name: str | None = None  # For "open" requests


class FileActor(Actor[trio.Path]):
    """
    A file actor that serves a single file in a read-only manner.
    """

    async def run(self, context: ActorContext):
        while True:
            try:
                message = await context.receive()
                await self.handle_message(message, context)
            except trio.Cancelled:
                self.logger.info("file actor cancelled")
                return

    async def handle_message(self, message: Message, context: ActorContext):
        if message["type"] == "http.request":
            request = ActorHttpRequest.model_validate(message)
            await self.handle_http_request(request, context)

    async def handle_http_request(
        self,
        request: ActorHttpRequest,
        context: ActorContext,
    ):
        req = request.request

        if req.method == "GET":
            if req.query_params.get("action") == "read":
                if await self.param.is_file():
                    content = await self.param.read_bytes()
                    response = HttpResponseData(
                        status=200,
                        headers={
                            "Content-Type": "application/octet-stream"
                        },
                        body=content,
                    )
                    await context.send_model(request.response, response)
                    return

            # Respond with a capability descriptor
            response = HttpResponseData(
                status=200,
                headers={"Content-Type": "application/json"},
                body=JSONResponse(
                    {
                        "@context": ["https://node.town/2024/"],
                        "@type": "File",
                        "@id": context.actor,
                        "name": self.param.name,
                    }
                ).body,
            )
            await context.send_model(request.response, response)
            return

        try:
            fs_req = FSRequest.model_validate_json(
                req.body.decode("utf-8") or "{}"
            )

            if fs_req.action == "open":
                if await self.param.is_file():
                    content = await self.param.read_bytes()
                    response = HttpResponseData(
                        status=200,
                        headers={
                            "Content-Type": "application/octet-stream"
                        },
                        body=content,
                    )
                else:
                    response = HttpResponseData(
                        status=400,
                        headers={},
                        body=b"This actor does not represent a file",
                    )
            else:
                response = HttpResponseData(
                    status=400,
                    headers={},
                    body=b"Unsupported action on a file actor",
                )

            await context.send_model(request.response, response)

        except Exception as e:
            self.logger.warning("error handling request", error=str(e))
            response = HttpResponseData(
                status=400,
                headers={},
                body=b"Invalid request",
            )
            await context.send_model(request.response, response)


class FilesystemActor(Actor[trio.Path]):
    """
    A filesystem actor that represents a directory.
    """

    async def run(self, context: ActorContext):
        self.logger.info(
            "filesystem_actor spawned", directory=str(self.param)
        )
        self.entries: dict[str, URIRef] = {}

        for entry in await self.param.iterdir():
            child_actor = await context.spawn(FileActor, entry)
            self.entries[entry.name] = child_actor

        while True:
            try:
                message = await context.receive()
                await self.handle_message(message, context)
            except trio.Cancelled:
                self.logger.info("filesystem actor cancelled")
                return

    async def handle_message(self, message: Message, context: ActorContext):
        if message["type"] == "http.request":
            request = ActorHttpRequest.model_validate(message)
            await self.handle_http_request(request, context)

    async def handle_http_request(
        self,
        request: ActorHttpRequest,
        context: ActorContext,
    ):
        try:
            fs_req = FSRequest.model_validate_json(
                request.request.body.decode("utf-8") or "{}"
            )
        except Exception:
            fs_req = FSRequest(action="list")

        if fs_req.action == "list":
            listing = {name: str(uri) for name, uri in self.entries.items()}
            response = HttpResponseData(
                status=200,
                headers={"Content-Type": "application/json"},
                body=JSONResponse(listing).body,
            )
            await context.send_model(request.response, response)

        elif fs_req.action == "open" and fs_req.name is not None:
            if fs_req.name in self.entries:
                target_actor = self.entries[fs_req.name]
                await context.send_model(target_actor, request.model_dump())
            else:
                response = HttpResponseData(
                    status=404,
                    headers={},
                    body=b"No such file or directory",
                )
                await context.send_model(request.response, response)

        else:
            response = HttpResponseData(
                status=400,
                headers={},
                body=b"Unsupported action or missing parameters",
            )
            await context.send_model(request.response, response)
