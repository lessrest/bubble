from contextlib import asynccontextmanager, contextmanager
import json
import logging
import pathlib

from fastapi import FastAPI, Form, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import hypercorn.trio
import rich
import trio

from bubble.html import (
    ErrorMiddleware,
    HypermediaResponse,
    attr,
    classes,
    log_middleware,
    document,
    tag,
    text,
)
from bubble.prfx import NT, RDF
from bubble.rdfa import rdf_resource
from bubble.repo import BubbleRepo, using_bubble
from bubble.util import get_single_subject

import bubble.rdfa

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("The Bubble HTTP server is starting.")

    bubble = await BubbleRepo.open(
        trio.Path(pathlib.Path.home() / "bubble")
    )

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


@app.middleware("http")
async def bubble_graph(request: Request, call_next):
    with using_bubble(request.app.state.bubble):
        logger.info(
            f"Using graph with {len(request.app.state.bubble.graph)} triples"
        )
        try:
            return await call_next(request)
        finally:
            logger.info("Leaving graph context")


@app.middleware("http")
async def reload_ontology(request: Request, call_next):
    repo: BubbleRepo = request.app.state.bubble
    logger.info("Reloading ontology")
    await repo.load_ontology()
    return await call_next(request)


cdn_scripts = [
    "https://unpkg.com/htmx.org@2",
]

htmx_config = {
    "globalViewTransitions": True,
}


def json_assignment_script(variable_name: str, value: dict):
    with tag("script"):
        text(
            f"Object.assign({variable_name}, {json.dumps(value, indent=2)});"
        )


@contextmanager
def base_html(title: str):
    with tag("html"):
        with tag("head"):
            with tag("title"):
                text(title)
            tag("link", rel="stylesheet", href="/static/css/output.css")
            for script in cdn_scripts:
                with tag("script", src=script):
                    attr("async")
            tag("script", type="module", src="/static/type-writer.js")
            tag("script", type="module", src="/static/voice-writer.js")
            json_assignment_script("htmx.config", htmx_config)

        with tag(
            "body",
            classes="bg-white dark:bg-slate-950 text-gray-900 dark:text-stone-50",
        ):
            yield


def mount_static(
    app: FastAPI, directory: str, mount_path: str = "/static"
):
    """
    Mount a static files directory to the FastAPI application.
    """
    app.mount(mount_path, StaticFiles(directory=directory), name="static")


mount_static(app, "bubble/static")

app.include_router(bubble.rdfa.router)


@app.middleware("http")
async def context_middleware(request, call_next):
    with document():
        return await call_next(request)


# Add error handling middleware
app.add_middleware(ErrorMiddleware)

# Add request logging
app.middleware("http")(log_middleware)


@app.get("/", response_class=HypermediaResponse)
def get_dashboard():
    with base_html("Bubble"):
        with tag("div", classes="flex flex-col gap-4"):
            with tag("div"):
                classes(
                    "font-serif px-4 py-1 bg-white dark:bg-slate-800",
                    "border-b border-gray-200 dark:border-slate-700",
                )
                tag(
                    "voice-writer",
                    language="en-US",
                    server="wss://swa.sh",
                )
            with tag("div", classes="p-2"):
                iri = get_single_subject(RDF.type, NT.ServiceAccount)
                if iri:
                    with bubble.rdfa.autoexpanding(2):
                        rdf_resource(iri)


@app.get("/voice", response_class=HypermediaResponse)
def get_voice_page():
    with base_html("Voice Writer"):
        with tag(
            "div",
            classes="flex font-serif",
        ):
            tag(
                "voice-writer",
                language="en-US",
                server="wss://swa.sh",
                debug=True,
                classes="w-full",
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
            return JSONResponse(
                status_code=500, content={"error": str(e)}
            )
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


async def _serve_app(app: FastAPI, config: hypercorn.Config) -> None:
    await hypercorn.trio.serve(app, config)  # type: ignore


def run_server(app: FastAPI):
    config = hypercorn.Config()
    trio.run(_serve_app, app, config)


if __name__ == "__main__":
    run_server(app)
