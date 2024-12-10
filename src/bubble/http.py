import pathlib

from typing import Annotated
from contextlib import asynccontextmanager

import rich
import trio
import structlog
import hypercorn.trio

from rdflib import URIRef
from fastapi import Form, Path, Query, FastAPI, Request, Response, WebSocket
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import bubble.blob
import bubble.opus
import swash.rdfa

from swash.html import (
    HypermediaResponse,
    tag,
    classes,
    document,
)
from swash.prfx import NT
from swash.util import is_a, get_single_subject
from swash.vars import Parameter
from bubble.page import base_html
from bubble.repo import BubbleRepo, save_bubble, using_bubble

logger = structlog.get_logger()

bubble_path = Parameter("bubble_path", str(pathlib.Path.home() / "bubble"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    static_dir = pathlib.Path(__file__).parent / "static"
    mount_static(app, str(static_dir))

    logger.info("The Bubble HTTP server is starting.")

    bubble = await BubbleRepo.open(trio.Path(bubble_path.get()))

    app.state.bubble = bubble

    await bubble.load_surfaces()
    await bubble.load_rules()
    await bubble.load_ontology()
    logger.info(f"Loaded {len(bubble.graph)} bubble triples")
    logger.info(f"Loaded {len(bubble.vocab)} ontology triples")

    yield

    logger.info("The Bubble HTTP server is shutting down.")


"""
Create and configure the FastAPI application with standard middleware and routers.
"""
app = FastAPI(
    lifespan=lifespan,
    debug=True,
    default_response_class=HypermediaResponse,
)


@app.middleware("websocket")
async def websocket_middleware(websocket: WebSocket, call_next):
    with using_bubble(websocket.app.state.bubble):
        return await call_next(websocket)


@app.middleware("http")
async def bubble_context_middleware(request: Request, call_next):
    with using_bubble(request.app.state.bubble):
        try:
            return await call_next(request)
        finally:
            logger.info("Leaving graph context")


# @app.middleware("http")
# async def reload_ontology(request: Request, call_next):
#     repo: BubbleRepo = request.app.state.bubble
#     logger.info("Reloading ontology")
#     await repo.load_ontology()
#     return await call_next(request)


def mount_static(app: FastAPI, directory: str, mount_path: str = "/static"):
    """
    Mount a static files directory to the FastAPI application.
    """
    app.mount(mount_path, StaticFiles(directory=directory), name="static")


@app.post("/blob")
async def create_blob_stream(
    request: Request, type: Annotated[str, Form()]
):
    stream = await bubble.blob.create_stream(request, URIRef(type))
    swash.rdfa.rdf_resource(stream)
    await save_bubble()
    return HypermediaResponse()


@app.websocket("/{id:path}")
async def websocket_endpoint(websocket: WebSocket, id: str):
    await websocket.accept()
    bubble: BubbleRepo = websocket.app.state.bubble
    entity = URIRef(str(websocket.url))
    with using_bubble(bubble):
        if is_a(entity, NT.UploadCapability):
            stream = get_single_subject(NT.hasPart, entity)
            assert isinstance(stream, URIRef)
            raise Exception("Not implemented")
        #            await handle_websocket_voice_ingress(websocket, stream, bubble)
        else:
            await websocket.close(code=1008, reason="No capability")


app.include_router(swash.rdfa.router)
app.include_router(bubble.opus.router)


@app.middleware("http")
async def context_middleware(request, call_next):
    with document():
        return await call_next(request)


@app.get("/", response_class=HypermediaResponse)
def get_dashboard():
    with base_html("Bubble"):
        with tag("div", classes="flex flex-col gap-4"):
            with tag("div"):
                classes(
                    "font-serif px-1 py-1",
                    "m-2",
                    "rounded-2",
                )
                voice_writer()


def voice_writer():
    tag(
        "voice-recorder-writer",
        language="en-US",
        endpoint=app.url_path_for("create_stream"),
    )


@app.get("/{bubble_id}/sparql")
async def get_sparql(
    request: Request,
    query: str = Query(default=""),
    bubble_id: str = Path(),
):
    console = rich.console.Console()
    bubble = request.app.state.bubble
    assert isinstance(bubble, BubbleRepo)
    if bubble_id != "foo":
        return JSONResponse(
            status_code=404, content={"error": "Bubble not found"}
        )
    console.print(f"Query: {query}")
    if query:
        try:
            results = bubble.dataset.query(query)
            return Response(
                content=results.serialize(format="json"),
                media_type="application/sparql-results+json",
            )
        except Exception as e:
            console.print_exception()
            return JSONResponse(status_code=500, content={"error": str(e)})
    else:
        return JSONResponse(
            status_code=400, content={"error": "No query provided"}
        )


@app.post("/{bubble_id}/sparql")
async def post_sparql(
    request: Request,
    query: str = Form(),
    bubble_id: str = Path(),
):
    return await get_sparql(request, query, bubble_id)


async def serve(config: hypercorn.Config) -> None:
    await hypercorn.trio.serve(app, config, mode="asgi")  # type: ignore


if __name__ == "__main__":
    trio.run(serve, hypercorn.Config())
