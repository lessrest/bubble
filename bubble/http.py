from contextlib import asynccontextmanager, contextmanager
import json
import logging
import pathlib

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import hypercorn.trio
import trio

from bubble.html import (
    ErrorMiddleware,
    HypermediaResponse,
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
                tag("script", src=script)
            json_assignment_script("htmx.config", htmx_config)

        with tag(
            "body",
            classes="bg-white dark:bg-slate-900 text-gray-900 dark:text-white",
        ):
            yield


def mount_static(
    app: FastAPI, directory: str, mount_path: str = "/static"
):
    """
    Mount a static files directory to the FastAPI application.
    """
    app.mount(
        mount_path, StaticFiles(directory=directory), name="static"
    )


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
        with tag("div", classes="flex flex-col gap-4 p-4"):
            iri = get_single_subject(RDF.type, NT.ComputerMachine)
            if iri:
                with bubble.rdfa.autoexpanding(2):
                    rdf_resource(iri)
            else:
                with tag(
                    "div", classes="text-red-600 dark:text-red-500"
                ):
                    text("No active session found. Please log in.")


async def _serve_app(app: FastAPI, config: hypercorn.Config) -> None:
    await hypercorn.trio.serve(app, config)  # type: ignore


def run_server(app: FastAPI):
    config = hypercorn.Config()
    trio.run(_serve_app, app, config)


if __name__ == "__main__":
    run_server(app)
