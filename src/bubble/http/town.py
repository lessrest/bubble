"""Digital Town Square: Where Code Meets Community

In the physical world, towns grow organically around gathering places -
markets, churches, town halls. In our digital realm, we build structured
spaces for interaction, where WebSockets replace town criers and
linked data forms the streets and signposts of our virtual community.

This module implements a digital town square, complete with:
- Identity management (our digital citizens)
- Real-time communication (our virtual conversations)
- Linked data responses (our semantic signposts)
- Health monitoring (our town's vital signs)

Historical note: The web started as a simple document sharing system,
but evolved into rich interactive spaces. This town square continues
that evolution, adding real-time capabilities while staying true to
the web's linked data heritage.
"""

import json
import uuid
import pathlib

from io import BytesIO
from base64 import b64encode
from typing import Any, Dict, Optional, AsyncGenerator
from contextlib import contextmanager

import trio
import structlog

from rdflib import RDF, XSD, Graph, URIRef, Literal, Namespace
from fastapi import (
    Body,
    Form,
    FastAPI,
    Request,
    Response,
    WebSocket,
    HTTPException,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import UploadFile

from swash import here, mint, rdfa
from swash.html import HypermediaResponse, tag, html, text, document
from swash.json import pyld
from swash.prfx import NT, DID
from swash.rdfa import (
    rdf_resource,
    autoexpanding,
    get_subject_data,
    render_affordance_resource,
)
from swash.util import P, new
from bubble.keys import build_did_document, parse_public_key_hex
from bubble.mesh.otp import record_message
from bubble.http.eval import eval_code, eval_form
from bubble.http.icon import favicon
from bubble.http.page import base_html, base_shell
from bubble.http.word import word_lookup, word_lookup_form
from bubble.mesh.base import (
    Vat,
    vat,
    send,
    this,
    txgraph,
    create_graph,
    with_transient_graph,
)
from bubble.mesh.call import call
from bubble.repo.repo import Repository, context
from bubble.http.render import render_graph_view, render_graphs_overview

logger = structlog.get_logger(__name__)


class LinkedDataResponse(HypermediaResponse):
    """A response that speaks the language of linked data.

    Like a town crier who knows multiple languages, this response
    can present information in both human-readable HTML and
    machine-readable RDF formats. It's the digital equivalent
    of posting a notice that both humans and computers can understand.
    """

    def __init__(
        self,
        graph: Optional[Graph] = None,
        *,
        vocab: Optional[Namespace] = None,
        context: Optional[Dict] = None,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ):
        if graph is None:
            graph = here.graph.get()

        if headers is None:
            headers = {}

        headers["Link"] = f'<{str(graph.identifier)}>; rel="self"'

        with base_html("Bubble"):
            rdf_resource(graph.identifier)

        super().__init__(
            status_code=status_code,
            headers=headers,
        )


class JSONLinkedDataResponse(JSONResponse):
    def __init__(
        self,
        graph: Optional[Graph] = None,
        *,
        vocab: Optional[Namespace] = None,
        context: Optional[Dict] = None,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ):
        if graph is None:
            graph = here.graph.get()

        if context is None:
            context = {
                "nt": str(NT),
                "w3": "https://www.w3.org/ns/",
                "@base": str(graph.base),
            }

        if vocab is not None:
            context["@vocab"] = str(vocab)

        jsonld = json.loads(graph.serialize(format="json-ld"))
        compacted = pyld.jsonld.compact(
            jsonld, context, {"base": str(graph.base)}
        )

        if headers is None:
            headers = {}

        headers["Content-Type"] = "application/ld+json"
        headers["Link"] = f'<{str(graph.identifier)}>; rel="self"'

        super().__init__(
            content=compacted,
            status_code=status_code,
            headers=headers,
            media_type="application/ld+json",
        )


#    print_n3(current_bubble.get().graph, "current_bubble.get().graph")
#    print_n3(vars.graph.get(), "vars.graph.get()")
#    print_n3(graph, "graph")


def generate_health_status(id: URIRef):
    """Generate health status information."""
    new(
        NT.HealthCheck,
        {
            NT.status: Literal("ok"),
            NT.actorSystem: this(),
        },
        subject=id,
    )


class Site:
    """A digital town square where actors gather and interact.

    Like a well-planned city, this class provides the infrastructure
    for digital interaction - from WebSocket connections (our streets)
    to session management (our citizen registry) to error handling
    (our safety nets).

    Think of it as a virtual municipality where every connection is
    a citizen, every message a conversation, and every response a
    carefully crafted piece of our shared digital space.
    """

    def __init__(
        self,
        base_url: str,
        bind: str,
        repo: Repository,
        nats_url: str = "nats://localhost:4222",
    ):
        self.base_url = base_url
        self.base = URIRef(base_url)
        self.bind = bind
        self.repo = repo
        self.site = Namespace(base_url)
        self.yell = structlog.get_logger(__name__)
        self.app = FastAPI()

        self._setup_error_handlers()
        self._setup_middleware()
        self._setup_routes()

        self.vat = Vat(str(self.site), self.yell)

        # Add session tracking
        self.websocket_sessions: Dict[str, WebSocket] = {}
        self.session_actors: Dict[str, URIRef] = {}
        self.actor_sessions: Dict[URIRef, str] = {}

    def _setup_error_handlers(self):
        """Setup comprehensive error handling for the web layer."""

        @self.app.exception_handler(Exception)
        async def handle_generic_error(request: Request, exc: Exception):
            logger.error(
                "unhandled web error", error=exc, path=request.url.path
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "details": str(exc),
                },
            )

    def _setup_middleware(self):
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.app.middleware("http")(self.bind_document)
        self.app.middleware("http")(self.bind_actor_system)
        self.app.middleware("http")(self.bind_bubble)

    # Middleware
    async def bind_document(self, request, call_next):
        with document():
            return await call_next(request)

    async def bind_actor_system(self, request, call_next):
        with vat.bind(self.vat):
            return await call_next(request)

    async def bind_bubble(self, request, call_next):
        with context.repo.bind(self.repo):
            return await call_next(request)

    async def all_exception_handler(self, request: Request, exc: Exception):
        self.yell.error("Unhandled exception", error=exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "details": str(exc)},
        )

    def _setup_routes(self):
        self.app.include_router(rdfa.router)
        self.app.mount(
            "/static",
            StaticFiles(
                directory=str(pathlib.Path(__file__).parent / "static")
            ),
        )

        self.app.get("/")(self.root)
        self.app.get("/health")(self.health_check)
        self.app.get("/favicon.ico")(self.favicon)
        self.app.get("/.well-known/did.json")(self.get_did_document)
        self.app.get("/.well-known/did.html")(self.get_did_document_html)
        self.app.get("/graphs")(graphs_view)
        self.app.get("/graph")(graph_view)

        self.app.get("/eval")(self.eval_form)
        self.app.post("/eval")(self.eval_code)

        self.app.post("/{id}/message")(self.actor_message)
        self.app.post("/{id}")(self.actor_post)
        self.app.put("/{id}")(self.actor_put)

        self.app.websocket("/{id}/upload")(self.ws_upload)
        self.app.websocket("/{id}/jsonld")(self.ws_jsonld)

        self.app.websocket("/join/{key}")(self.ws_actor_join)
        self.app.websocket("/join")(self.ws_anonymous_join)

        self.app.get("/word")(self.word_lookup)
        self.app.get("/words")(self.word_lookup_form)

        self.app.get("/files/{path:path}")(self.file_get)
        self.app.get("/blobs/{sha256}")(self.blob_get)

        # this is at the bottom because it matches too broadly
        self.app.get("/{id:path}")(self.resource_get)

    async def root(self):
        with base_shell("Bubble"):
            with tag("div", classes="p-4"):
                graph = here.graph.get()

                resources_with_affordances = set(
                    graph.subjects(NT.affordance, None)
                )

                with autoexpanding(depth=2):
                    if resources_with_affordances:
                        with tag("div", classes="flex flex-col gap-4"):
                            for subject in resources_with_affordances:
                                data = get_subject_data(
                                    here.dataset.get(), subject
                                )
                                render_affordance_resource(subject, data)
                    else:
                        render_graph_view(graph)

        return HypermediaResponse()

    async def file_get(self, path: str):
        file = self.repo.open_existing_file(URIRef(path))
        return Response(content=await file.read())

    async def blob_get(self, sha256: str):
        blob = await self.repo.open_blob(sha256)
        return Response(content=await blob.read())

    async def health_check(self):
        with with_transient_graph("health") as id:
            generate_health_status(id)
            return JSONLinkedDataResponse()

    async def get_did_document(self):
        did_uri = URIRef(
            str(self.site).replace("https://", "did:web:").rstrip("/")
        )

        with with_transient_graph(".well-known/did.json") as id:
            build_did_document(did_uri, id, self.vat.public_key)
            return JSONLinkedDataResponse(vocab=DID)

    async def get_did_document_html(self):
        """Serve the DID document as an HTML page."""
        did_uri = URIRef(
            str(self.site).replace("https://", "did:web:").rstrip("/")
        )

        with with_transient_graph(".well-known/did.html") as id:
            build_did_document(did_uri, id, self.vat.public_key)
            with base_shell("DID Document"):
                with tag.div(classes="p-4"):
                    with tag.h1(classes="text-2xl font-bold mb-4"):
                        text("DID Document")
                    render_graph_view(here.graph.get())

        return HypermediaResponse()

    async def actor_message(self, id: str, request: Request):
        async with request.form() as form:
            logger.info("actor message", id=id, form=form)
            type = form.get("type")
            assert isinstance(type, str)
            actor = self.site[id]

            with with_transient_graph():
                properties: Dict[P, Any] = {}

                # Handle each form field
                for k, v in form.items():
                    if k == "type":
                        continue

                    if isinstance(v, UploadFile):
                        # Handle file upload as a structured NT.File object
                        file_data = await v.read()
                        properties[URIRef(k)] = new(
                            NT.File,
                            {
                                NT.data: file_data,
                                NT.mimeType: Literal(
                                    v.content_type
                                    or "application/octet-stream"
                                ),
                            },
                        )
                        logger.info(
                            "file upload", file=properties[URIRef(k)]
                        )
                    elif isinstance(v, str):
                        # Handle regular string values
                        properties[URIRef(k)] = Literal(v)
                    else:
                        raise ValueError("Unknown form field type", v)

                g = here.graph.get()
                record_message(type, actor, g, properties=properties)
                result = await call(actor, g)
                return LinkedDataResponse(result)

    async def favicon(self):
        img = await favicon()
        ico_buffer = BytesIO()
        img.save(ico_buffer, format="ICO")
        ico_data = ico_buffer.getvalue()

        return Response(content=ico_data, media_type="image/x-icon")

    async def actor_post(self, id: str, body: dict = Body(...)):
        actor = self.site[id]
        async with txgraph() as g:
            body["@id"] = str(g.identifier)
            g.parse(data=json.dumps(body), format="json-ld")
            result = await call(actor, g)
            return LinkedDataResponse(result)

    async def actor_put(self, id: str, request: Request):
        actor = self.site[id]

        async def request_stream():
            async for chunk in request.stream():
                yield chunk

        result = await self._handle_upload_stream(actor, request_stream())
        return LinkedDataResponse(result)

    async def ws_upload(self, websocket: WebSocket, id: str):
        """WebSocket handler with proper error handling."""
        try:
            await websocket.accept()
            actor = self.site[id]
            logger.info("starting websocket upload", actor=actor)

            async def receive_messages():
                while True:
                    try:
                        message = await websocket.receive_bytes()
                        yield message
                    except Exception as e:
                        logger.error("websocket receive error", error=e)
                        break

            with self.install_context():
                result = await self._handle_upload_stream(
                    actor, receive_messages()
                )

            await websocket.send_json(result.serialize(format="json-ld"))

        except Exception as e:
            logger.error("websocket handler error", error=e)
            try:
                await websocket.close(code=1011, reason=str(e))
            except Exception:
                pass  # Connection might already be closed
            raise
        finally:
            await websocket.close()

    async def resource_get(self, id: str):
        with base_shell("Resource"):
            with autoexpanding(depth=2):
                render_affordance_resource(
                    URIRef(id),
                    get_subject_data(here.dataset.get(), URIRef(id)),
                )
        return HypermediaResponse()

    async def actor_get(self, id: str):
        actor = vat.get().deck[self.site[id]]

        async def stream_messages():
            try:
                while True:
                    try:
                        graph: Graph = await actor.recv.receive()
                        jsonld = graph.serialize(format="json-ld")
                        yield f"event: message\ndata: {jsonld}\n\n"
                    except (
                        trio.BrokenResourceError,
                        trio.ClosedResourceError,
                    ):
                        break
            except Exception as e:
                logger.error("Error in message stream", error=e)
                return

        return StreamingResponse(
            stream_messages(), media_type="text/event-stream"
        )

    def get_websocket_base(self):
        return self.base_url.replace("https://", "wss://")

    async def ws_jsonld(self, websocket: WebSocket, id: str):
        """WebSocket handler for JSON-LD messages with session management."""
        session_id = self._generate_session_id()

        try:
            await websocket.accept()
            self.websocket_sessions[session_id] = websocket
            logger.info(
                "starting jsonld websocket connection",
                session_id=session_id,
            )

            # Create an actor for this session
            session_actor = mint.fresh_uri(self.site)
            self.session_actors[session_id] = session_actor
            self.actor_sessions[session_actor] = session_id

            while True:
                try:
                    data = await websocket.receive_json()
                    logger.info(
                        "received json-ld message",
                        data=data,
                        session=session_id,
                    )

                    # Create a graph from the JSON-LD message
                    g = Graph(identifier=data["@id"])
                    g.parse(data=json.dumps(data), format="json-ld")

                    # Add session actor as source
                    g.add((g.identifier, NT.source, session_actor))

                    logger.info("parsed json-ld message", graph=g)

                    # Find target actor and send message
                    target = list(g.objects(g.identifier, NT.target))
                    if target:
                        response = await call(URIRef(target[0]), g)
                        await websocket.send_json(
                            json.loads(response.serialize(format="json-ld"))
                        )
                    else:
                        await websocket.send_json(
                            {"error": "No target actor specified"}
                        )

                except WebSocketDisconnect as e:
                    logger.error("websocket disconnect", error=e)
                    break

                except Exception as e:
                    logger.error(
                        "error processing websocket message",
                        error=e,
                        session=session_id,
                    )
                    await websocket.send_json({"error": str(e)})

        except Exception as e:
            logger.error(
                "websocket handler error", error=e, session=session_id
            )
            try:
                await websocket.close(code=1011, reason=str(e))
            except Exception:
                pass
        finally:
            # Clean up session
            if session_id in self.session_actors:
                actor = self.session_actors[session_id]
                del self.actor_sessions[actor]
                del self.session_actors[session_id]
            if session_id in self.websocket_sessions:
                del self.websocket_sessions[session_id]
            await websocket.close()

    async def ws_actor_join(self, websocket: WebSocket, key: str):
        """Handle a remote actor joining the town with a provided identity key."""
        from bubble.sock.peer import handle_actor_join

        # Parse the hex key string into an Ed25519PublicKey object before passing to handle_actor_join
        public_key = parse_public_key_hex(key)
        await handle_actor_join(websocket, public_key, self.vat)

    async def ws_anonymous_join(self, websocket: WebSocket):
        """Handle an anonymous/transient actor joining the town."""
        from bubble.sock.peer import handle_anonymous_join

        await handle_anonymous_join(websocket, self.vat)

    @contextmanager
    def install_context(self):
        """Install the actor system and bubble context for request handling."""
        with vat.bind(self.vat):
            with context.repo.bind(self.repo):
                with here.dataset.bind(self.repo.dataset):
                    yield

    async def _handle_upload_stream(
        self, actor: URIRef, stream: AsyncGenerator[bytes, None]
    ) -> Graph:
        """Handle upload stream with proper error handling."""
        try:
            async for chunk in stream:
                try:
                    await self._send_chunk_to_actor(actor, chunk)
                except Exception as e:
                    logger.error("chunk processing error", error=e)
                    raise RuntimeError(
                        f"Failed to process chunk: {str(e)}"
                    ) from e

            # Send end marker
            async with txgraph() as g:
                assert isinstance(g.identifier, URIRef)
                new(NT.End, {}, g.identifier)
                await send(actor)

            # Return completion message
            g = create_graph()
            g.add((g.identifier, RDF.type, NT.Done))
            return g

        except Exception as e:
            logger.error("upload stream error", error=e)
            g = create_graph()
            g.add((g.identifier, RDF.type, NT.Error))
            g.add((g.identifier, NT.message, Literal(str(e))))
            return g

    async def _send_chunk_to_actor(
        self, actor: URIRef, message: bytes
    ) -> URIRef:
        with with_transient_graph() as id:
            new(
                NT.Chunk,
                {
                    NT.bytes: Literal(
                        b64encode(message),
                        datatype=XSD.base64Binary,
                    )
                },
                id,
            )
            await send(actor)
        return id

    def get_fastapi_app(self) -> FastAPI:
        return self.app

    def _generate_session_id(self) -> str:
        """Generate a random session ID for WebSocket connections."""
        return str(uuid.uuid4())

    async def send_to_client(
        self, actor_uri: URIRef, message: Graph
    ) -> bool:
        """Send a message to a client if it's connected."""
        session_id = self.actor_sessions.get(actor_uri)
        if not session_id:
            logger.warning("No session found for actor", actor=actor_uri)
            return False

        websocket = self.websocket_sessions.get(session_id)
        if not websocket:
            logger.warning(
                "No websocket found for session", session=session_id
            )
            return False

        try:
            await websocket.send_json(
                json.loads(message.serialize(format="json-ld"))
            )
            return True
        except Exception as e:
            logger.error(
                "Error sending message to client",
                error=e,
                session=session_id,
                actor=actor_uri,
            )
            return False

    async def eval_form(self):
        """Render the Python code evaluation form."""
        return await eval_form()

    async def eval_code(self, code: str = Form(...)):
        """Evaluate Python code and return the results."""
        return await eval_code(code, town=self)

    async def word_lookup_form(
        self, word: Optional[str] = None, error: Optional[str] = None
    ):
        """Render the word lookup form and results if any."""
        return await word_lookup_form(word, error)

    async def word_lookup(self, word: str, pos: Optional[str] = None):
        """Handle word lookup form submission."""
        return await word_lookup(word, pos)

    async def setup_nats(self, nats_url: str):
        """Set up NATS clustering."""
        await self.vat.setup_nats(nats_url)


@contextmanager
def in_request_graph(g: Graph):
    with here.graph.bind(g):
        yield g


def town_app(
    base_url: str, bind: str, repo: Repository, root_actor=None
) -> FastAPI:
    """Create and return a FastAPI app for the town."""
    app = Site(base_url, bind, repo)
    return app.get_fastapi_app()


@html.div("min-h-screen bg-gray-50 dark:bg-gray-900")
def graphs_view(request: Request):
    """Handler for viewing all graphs in the bubble."""
    repo = context.repo.get()
    with base_shell("Graphs"):
        render_graphs_overview(repo.dataset)
        return HypermediaResponse()


def graph_view(request: Request):
    """Handler for viewing complete graphs."""
    graph_id = request.query_params.get("graph")
    if not graph_id:
        raise HTTPException(status_code=400, detail="No graph ID provided")

    graph = None
    repo = context.repo.get()

    # Try to find the graph in the bubble's dataset
    for g in repo.dataset.graphs():
        if str(g.identifier) == graph_id:
            graph = g
            break

    if not graph:
        raise HTTPException(status_code=404, detail="Graph not found")

    with base_shell("Graph"):
        render_graph_view(graph)
        return HypermediaResponse()
