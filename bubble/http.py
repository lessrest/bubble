from contextlib import asynccontextmanager, contextmanager
import json
import logging
import pathlib

from fastapi import FastAPI
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
from bubble.repo import BubbleRepo
from bubble.util import get_single_subject
from bubble.vars import using_graph
from bubble.html import live_router
from bubble.vars import current_graph

import bubble.rdfa

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("The application is starting.")
    bubble = await BubbleRepo.open(
        trio.Path(pathlib.Path.home() / "bubble")
    )
    current_graph.set(bubble.graph)

    with using_graph(bubble.graph):
        await bubble.load_surfaces()
        await bubble.load_rules()
        await bubble.load_ontology()
        logger.info(f"Loaded {len(bubble.graph)} triples")
        yield


"""
Create and configure the FastAPI application with standard middleware and routers.
"""
app = FastAPI(
    lifespan=lifespan,
    debug=True,
    default_response_class=HypermediaResponse,
)

# # Add CORS middleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

cdn_scripts = [
    "https://cdn.tailwindcss.com/?plugins=forms",
    "https://unpkg.com/htmx.org@2",
]

tailwind_config = {
    "theme": {
        "extend": {
            "fontFamily": {
                "mono": ["iosevka extended", "monospace"],
            },
        },
    },
}

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
            for script in cdn_scripts:
                tag("script", src=script)
            tag("script", src="/live/index.js")
            json_assignment_script("htmx.config", htmx_config)
            json_assignment_script("tailwind.config", tailwind_config)

        with tag("body", classes="bg-slate-900 text-white"):
            yield


# Include the live router for websocket/live updates
app.include_router(live_router)
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
                rdf_resource(iri)
            else:
                with tag("div", classes="text-red-500"):
                    text("No active session found. Please log in.")


def mount_static(
    app: FastAPI, directory: str, mount_path: str = "/static"
):
    """
    Mount a static files directory to the FastAPI application.
    """
    app.mount(
        mount_path, StaticFiles(directory=directory), name="static"
    )


def run_server(app: FastAPI):
    config = hypercorn.Config()
    trio.run(hypercorn.trio.serve, app, config)


if __name__ == "__main__":
    run_server(app)
