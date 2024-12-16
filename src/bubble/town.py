import base64
import io
import json
import uuid
import pathlib
from datetime import datetime

from io import BytesIO
from base64 import b64encode
from typing import (
    Any,
    Dict,
    List,
    Optional,
    AsyncGenerator,
)
from contextlib import (
    contextmanager,
    redirect_stderr,
    redirect_stdout,
)
from collections import defaultdict

import trio
import structlog

from rdflib import (
    DCAT,
    RDF,
    XSD,
    Graph,
    URIRef,
    Dataset,
    Literal,
    Namespace,
    PROV,
)
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
from rdflib.graph import QuotedGraph
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from swash import mint, rdfa, vars
from swash.html import HypermediaResponse, tag, html, text, document
from swash.json import pyld
from swash.prfx import NT, DID, Schema
from swash.rdfa import (
    rdf_resource,
    autoexpanding,
    get_subject_data,
    visited_resources,
)
from swash.util import P, S, add, new
from bubble.data import Repository, context
from bubble.mesh import (
    ActorContext,
    Vat,
    call,
    create_graph,
    record_message,
    send,
    this,
    txgraph,
    vat,
    with_transient_graph,
)
from bubble.icon import favicon
from bubble.keys import (
    build_did_document,
    parse_public_key_hex,
    verify_signed_data,
)
from bubble.page import base_html, base_shell
from bubble.word import describe_word
from bubble.replicate.make import Replicate

logger = structlog.get_logger(__name__)


class LinkedDataResponse(HypermediaResponse):
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
            graph = vars.graph.get()

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
            graph = vars.graph.get()

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
    def __init__(
        self,
        base_url: str,
        bind: str,
        repo: Repository,
    ):
        self.base_url = base_url
        self.base = URIRef(base_url)
        self.bind = bind
        self.repo = repo
        self.site = Namespace(base_url)
        self.yell = structlog.get_logger(__name__).bind(bind=bind)
        self.app = FastAPI()

        self._setup_error_handlers()
        self._setup_middleware()
        self._setup_routes()

        self.vat = Vat(str(self.site), self.yell)
        vat.set(self.vat)

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

    def _setup_routes(self):
        self.app.include_router(rdfa.router)
        self.app.mount(
            "/static",
            StaticFiles(
                directory=str(pathlib.Path(__file__).parent / "static")
            ),
        )

        self.app.get("/favicon.ico")(self.favicon)
        self.app.get("/health")(self.health_check)
        self.app.get("/.well-known/did.json")(self.get_did_document)
        self.app.get("/.well-known/did.html")(self.get_did_document_html)
        self.app.get("/graphs")(graphs_view)
        self.app.get("/graph")(graph_view)
        self.app.get("/eval")(self.eval_form)
        self.app.post("/eval")(self.eval_code)
        self.app.get("/")(self.root)

        self.app.post("/{id}/message")(self.actor_message)
        self.app.post("/{id}")(self.actor_post)
        self.app.put("/{id}")(self.actor_put)

        self.app.websocket("/{id}/upload")(self.ws_upload)
        self.app.websocket("/{id}/jsonld")(self.ws_jsonld)

        self.app.websocket("/join/{key}")(self.ws_actor_join)

        self.app.get("/word")(self.word_lookup)
        self.app.get("/words")(self.word_lookup_form)

        self.app.get("/files/{path:path}")(self.file_get)
        self.app.get("/blobs/{sha256}")(self.blob_get)
        self.app.get("/images")(self.image_gallery)

        # this is at the bottom because it matches too broadly
        self.app.get("/{path:path}")(self.actor_get)

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
                with tag("div", classes="p-4"):
                    with tag("h1", classes="text-2xl font-bold mb-4"):
                        text("DID Document")
                    render_graph_view(vars.graph.get())
        return HypermediaResponse()

    async def actor_message(self, id: str, request: Request):
        async with request.form() as form:
            type = form.get("type")
            assert isinstance(type, str)
            actor = self.site[id]
            properties: Dict[P, Any] = {
                URIRef(k): Literal(v)
                for k, v in form.items()
                if isinstance(v, str) and k != "type"
            }
            async with txgraph() as g:
                record_message(type, actor, g, properties=properties)
            result = await call(actor, g)
            return LinkedDataResponse(result)

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

    # Route handlers
    async def all_exception_handler(self, request: Request, exc: Exception):
        self.yell.error("Unhandled exception", error=exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "details": str(exc)},
        )

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

    # Add uptime actor URI to the HTML template
    async def root(self):
        with base_shell("Bubble"):
            with tag("main", classes="flex flex-col gap-4 p-4"):
                render_graph_view(vars.graph.get())
        return HypermediaResponse()

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
        # Here we let an actor join the town remotely.
        #
        # The key should be the hex-encoded Ed25519 public key
        # of the actor's identity.
        #
        # We first send a handshake message signed by the town's
        # Ed25519 private key. The actor then verifies the signature
        # and sends a signed message back.
        #
        # If the signature is valid, we add the actor to the town
        # and send a welcome message.
        #
        # Then, messages are relayed between the actor and the town.

        await websocket.accept()
        try:
            with with_transient_graph() as outgoing_handshake:
                new(
                    NT.Handshake,
                    {
                        NT.signedQuestion: Literal(
                            base64.b64encode(self.vat.sign_data(b"hello")),
                            datatype=XSD.base64Binary,
                        )
                    },
                    outgoing_handshake,
                )
                msg = vars.graph.get().serialize(format="turtle")
                logger.info("sending handshake", graph=msg)
                await websocket.send_text(msg)
                response = await websocket.receive_text()
                response_graph = Graph()
                response_graph.parse(data=response, format="turtle")
                logger.info("received response", graph=response_graph)

                # Extract and verify the signature from response
                signed_message = response_graph.value(
                    outgoing_handshake, NT.signedAnswer
                )
                if not signed_message:
                    raise ValueError("No signed message in response")

                # Convert key from hex to bytes
                try:
                    public_key = parse_public_key_hex(key)
                except ValueError:
                    raise ValueError("Invalid public key format")

                signed_message_bytes = signed_message.toPython()
                assert isinstance(signed_message_bytes, bytes)

                # Verify signature using provided public key
                if not verify_signed_data(
                    b"hello", signed_message_bytes, public_key
                ):
                    raise ValueError("Invalid signature")

                logger.info("signature verified", public_key=public_key)

                # The URI of the actor is derived from its public key
                # by Base32 encoding the public key and prefixing it with
                # the site namespace.
                remote_actor_uri = self.site[
                    base64.b32encode(public_key.public_bytes_raw())
                    .decode("ascii")
                    .rstrip("=")
                    .upper()
                ]

                # We mint a new process URI for this session
                proc = mint.fresh_uri(self.site)

                # We create a send and receive channel for the remote actor
                send, recv = trio.open_memory_channel[Graph](8)

                remote_actor_context = ActorContext(
                    boss=self.vat.get_identity_uri(),
                    addr=remote_actor_uri,
                    proc=proc,
                    send=send,
                    recv=recv,
                )

                self.vat.deck[remote_actor_uri] = remote_actor_context

                new(
                    NT.RemoteActor,
                    {
                        NT.publicKey: Literal(
                            key,
                            datatype=XSD.base64Binary,
                        ),
                        PROV.wasAssociatedWith: proc,
                    },
                    remote_actor_uri,
                )

                new(
                    NT.RemoteActorSession,
                    {
                        NT.remoteActor: remote_actor_uri,
                        NT.remoteActorContext: remote_actor_context,
                        PROV.startedAtTime: context.clock.get()(),
                    },
                    proc,
                )

                logger.info(
                    "remote actor joined",
                    addr=remote_actor_uri,
                    proc=proc,
                )

                async def forward_messages_to_remote_actor():
                    async for message in recv:
                        msg_json = message.serialize(format="trig")
                        await websocket.send_text(msg_json)

                async def forward_messages_to_town():
                    while True:
                        try:
                            data = await websocket.receive_text()
                            msg_graph = Graph()
                            msg_graph.parse(data=data, format="trig")
                            await send.send(msg_graph)
                        except Exception as e:
                            logger.error("websocket receive error", error=e)
                            break

                try:
                    async with trio.open_nursery() as nursery:
                        nursery.start_soon(forward_messages_to_remote_actor)
                        nursery.start_soon(forward_messages_to_town)
                except Exception as e:
                    logger.error("websocket handler error", error=e)
                    raise
                finally:
                    add(proc, {PROV.endedAtTime: context.clock.get()()})
        except Exception as e:
            logger.error("websocket handler error", error=e)
            raise

    @contextmanager
    def install_context(self):
        """Install the actor system and bubble context for request handling."""
        with vat.bind(self.vat):
            with context.repo.bind(self.repo):
                with vars.dataset.bind(self.repo.dataset):
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
        with base_shell("Python Evaluator"):
            with tag("div", classes="p-4"):
                with tag("h1", classes="text-2xl font-bold mb-4"):
                    text("Python Code Evaluator")

                self.render_exec_form()

        return HypermediaResponse()

    def render_exec_form(self, code: str = ""):
        with tag(
            "form",
            hx_post="/eval",
            hx_target="this",
            classes="space-y-4",
        ):
            with tag("div"):
                with tag(
                    "textarea",
                    name="code",
                    placeholder="Enter Python code here...",
                    classes=[
                        "w-full h-48 p-2 border font-mono",
                        "dark:bg-gray-800 dark:text-white",
                        "dark:border-gray-700 dark:focus:border-blue-500 dark:focus:ring-blue-500 dark:focus:outline-none",
                    ],
                ):
                    text(code)

            with tag(
                "button",
                type="submit",
                classes=[
                    "px-4 py-2 bg-blue-500 text-white hover:bg-blue-600",
                    "dark:bg-blue-600 dark:hover:bg-blue-700",
                    "dark:text-white",
                    "dark:focus:outline-none dark:focus:ring-2 dark:focus:ring-blue-500 dark:focus:ring-offset-2",
                    "dark:border-blue-500",
                ],
            ):
                text("Run")

    async def eval_code(self, code: str = Form(...)):
        """Evaluate Python code and return the results."""
        # Capture stdout and stderr
        stdout = io.StringIO()
        stderr = io.StringIO()

        try:
            # Redirect output
            with redirect_stdout(stdout), redirect_stderr(stderr):
                # Execute the code in a restricted environment
                exec_globals = {"print": print}
                exec(code, exec_globals, {"town": self})

            output = stdout.getvalue()
            errors = stderr.getvalue()

            # Format the input form again
            self.render_exec_form(code)

            # Format the response
            with tag(
                "div", classes="font-mono whitespace-pre-wrap p-4 rounded"
            ):
                if output:
                    with tag("div", classes="bg-gray-100 p-2 rounded"):
                        with tag(
                            "div", classes="text-sm text-gray-600 mb-1"
                        ):
                            text("Output:")
                        text(output)

                if errors:
                    with tag("div", classes="bg-red-100 p-2 rounded mt-2"):
                        with tag(
                            "div", classes="text-sm text-red-600 mb-1"
                        ):
                            text("Errors:")
                        text(errors)

                if not output and not errors:
                    with tag("div", classes="text-gray-500 italic"):
                        text("No output")

            # Render the next form
            self.render_exec_form()

        except Exception as e:
            with tag("div", classes="bg-red-100 p-2 rounded"):
                with tag("div", classes="text-sm text-red-600 mb-1"):
                    text("Error:")
                text(str(e))

        return HypermediaResponse()

    async def word_lookup_form(
        self, word: Optional[str] = None, error: Optional[str] = None
    ):
        """Render the word lookup form and results if any."""
        with base_shell("Word Lookup"):
            with tag("div", classes="p-4"):
                with tag("h1", classes="text-2xl font-bold mb-4"):
                    text("WordNet Lookup")

                # Form
                with tag(
                    "form",
                    hx_get="/word",
                    hx_target="this",
                    hx_params="*",
                    classes="mb-6",
                ):
                    with tag("div", classes="flex gap-2"):
                        with tag(
                            "input",
                            type="text",
                            name="word",
                            value=word or "",
                            placeholder="Enter a word...",
                            classes=[
                                "flex-grow p-2 border rounded",
                                "dark:bg-gray-800 dark:text-white",
                                "dark:border-gray-700 focus:border-blue-500",
                                "focus:ring-blue-500 focus:outline-none",
                            ],
                        ):
                            pass

                        with tag(
                            "button",
                            type="submit",
                            classes=[
                                "px-4 py-2 bg-blue-500 text-white rounded",
                                "hover:bg-blue-600",
                                "dark:bg-blue-600 dark:hover:bg-blue-700",
                                "focus:outline-none focus:ring-2",
                                "focus:ring-blue-500 focus:ring-offset-2",
                            ],
                        ):
                            text("Look up")

        return HypermediaResponse()

    async def word_lookup(self, word: str, pos: Optional[str] = None):
        """Handle word lookup form submission."""
        if not word.strip():
            return await self.word_lookup_form(error="Please enter a word")

        pos = pos if pos and pos.strip() else None

        with vars.graph.bind(create_graph()):
            for word_node in describe_word(word, pos):
                pass

            render_graph_view(vars.graph.get())
            logger.info("word lookup", graph=vars.graph.get())

            return HypermediaResponse()

    async def image_gallery(self):
        """Display a gallery of all NT.Image resources and the prompt affordance."""
        with base_shell("Image Gallery"):
            with tag("div", classes="p-4"):
                with tag("h1", classes="text-2xl font-bold mb-4"):
                    text("Image Gallery")

                # Find the Replicate client through the supervisor
                replicate_client = None
                dataset = context.repo.get().dataset
                identity = vat.get().get_identity_uri()

                # Find supervised actors through NT.environs
                for supervisor in dataset.objects(identity, PROV.started):
                    # Find Replicate.Client instances among supervised actors
                    for actor in dataset.objects(supervisor, NT.supervises):
                        if (
                            actor,
                            RDF.type,
                            Replicate.Client,
                        ) in dataset:
                            replicate_client = actor
                            break
                    if replicate_client:
                        break

                # Show the prompt affordance if we found the client
                if replicate_client:
                    with tag(
                        "div",
                        classes="mb-8 p-4 bg-white dark:bg-gray-800 rounded-lg shadow-sm",
                    ):
                        rdf_resource(replicate_client)
                else:
                    with tag("div", classes="p-4"):
                        text("No Replicate client found")

                # Query for all NT.Image resources
                images = []
                for graph in dataset.graphs():
                    for subject in graph.subjects(
                        RDF.type, DCAT.Distribution
                    ):
                        href = graph.value(subject, DCAT.downloadURL)
                        generated_time = graph.value(
                            subject, PROV.generatedAtTime
                        )
                        if href:
                            images.append(
                                {
                                    "id": subject,
                                    "href": str(href),
                                    "time": generated_time,
                                }
                            )

                # Sort images by generation time (newest first)
                images.sort(
                    key=lambda x: x["time"] if x["time"] else "",
                    reverse=True,
                )

                # Display images in a grid
                with tag(
                    "div",
                    classes="flex flex-row flex-wrap gap-2",
                ):
                    for img in images:
                        with tag(
                            "div",
                            classes="border rounded-lg overflow-hidden shadow-sm hover:shadow-md transition-shadow",
                        ):
                            # Image container with fixed aspect ratio
                            with tag("div", classes="relative pt-[100%]"):
                                with tag(
                                    "img",
                                    src=img["href"],
                                    alt="Generated image",
                                ):
                                    pass

                            # Image metadata
                            with tag(
                                "div",
                                classes="p-3 bg-white dark:bg-gray-800",
                            ):
                                with tag(
                                    "div",
                                    classes="text-sm text-gray-600 dark:text-gray-400",
                                ):
                                    if img["time"]:
                                        text(
                                            f"Generated: {img['time'].strftime('%Y-%m-%d %H:%M:%S')}"
                                            if isinstance(
                                                img["time"], datetime
                                            )
                                            else str(img["time"])
                                        )

        return HypermediaResponse()


@contextmanager
def in_request_graph(g: Graph):
    with vars.graph.bind(g):
        yield g


def town_app(
    base_url: str, bind: str, repo: Repository, root_actor=None
) -> FastAPI:
    """Create and return a FastAPI app for the town."""
    app = Site(base_url, bind, repo)
    return app.get_fastapi_app()


def count_outbound_links(graph: Graph, node: S) -> int:
    """Count outbound links from a node, excluding rdf:type."""
    return len(list(graph.triples((node, None, None))))


def count_inbound_links(graph: Graph, node: S) -> int:
    """Count inbound links to a node."""
    return len(list(graph.subjects(None, node)))


def get_traversal_order(graph: Graph) -> List[S]:
    """Get nodes in traversal order - prioritizing resources with fewer inbound links and more outbound links."""
    # Count inbound and outbound links for each subject
    link_scores = {}
    for subject in graph.subjects():
        inbound = count_inbound_links(graph, subject)
        outbound = count_outbound_links(graph, subject)
        link_scores[subject] = outbound / 2 - inbound * 2

    # Group nodes by type (URIRef vs BNode)
    typed_nodes = defaultdict(list)
    for node in link_scores:
        if isinstance(node, URIRef):
            typed_nodes["uri"].append(node)
        else:
            typed_nodes["bnode"].append(node)

    # Sort each group by score (descending)
    sorted_nodes = []

    # URIRefs first, sorted by score
    sorted_nodes.extend(
        sorted(
            typed_nodes["uri"], key=lambda x: link_scores[x], reverse=True
        )
    )

    # Then BNodes, sorted by score
    sorted_nodes.extend(
        sorted(
            typed_nodes["bnode"], key=lambda x: link_scores[x], reverse=True
        )
    )

    return sorted_nodes


def is_did_key(graph: Graph, node: S) -> bool:
    """Check if a node is a DID key."""
    return node in Namespace("did:")


def is_current_identity(node: S) -> bool:
    """Check if a node is the current town's identity."""
    try:
        return node == vat.get().get_identity_uri()
    except Exception:
        return False


def get_node_classes(graph: Graph, node: S) -> str:
    """Get the CSS classes for a node based on its type and identity status."""
    is_key = is_did_key(graph, node)
    is_current = is_current_identity(node)

    classes = "border-l-4 pl-2 "
    if is_key:
        if is_current:
            classes += "border-blue-500"
        else:
            classes += "border-gray-300 opacity-50 hidden"
    else:
        classes += "border-blue-500"

    return classes


def render_node(graph: Graph, node: S) -> None:
    """Render a single node with appropriate styling."""
    visited = visited_resources.get()
    if node in visited:
        return

    with vars.in_graph(graph):
        with tag("div", classes=get_node_classes(graph, node)):
            dataset = vars.dataset.get()
            dataset.add_graph(graph)
            data = get_subject_data(dataset, node, context=graph)
            rdf_resource(node, data)


def render_graph_view(graph: Graph) -> None:
    """Render a complete view of a graph with smart traversal ordering."""
    nodes = get_traversal_order(graph)
    typed_nodes = []
    untyped_nodes = []

    # Sort nodes into typed and untyped
    for node in nodes:
        if list(graph.objects(node, RDF.type)):
            typed_nodes.append(node)
        else:
            untyped_nodes.append(node)

    logger.info(
        "rendering graph",
        graph=graph,
        typed_nodes=typed_nodes,
        untyped_nodes=untyped_nodes,
    )

    with autoexpanding(3):
        with tag("div", classes="flex flex-col gap-4"):
            # First pass - render typed nodes
            for node in typed_nodes:
                render_node(graph, node)

            # Second pass - render untyped nodes
            if untyped_nodes:
                with tag(
                    "div",
                    classes="mt-4 border-t border-gray-300 dark:border-gray-700 pt-4",
                ):
                    with tag(
                        "h3",
                        classes="text-lg font-semibold mb-2 text-gray-600 dark:text-gray-400",
                    ):
                        text("Additional Resources")
                    for node in untyped_nodes:
                        render_node(graph, node)


def render_graphs_overview(dataset: Dataset) -> None:
    """Render an overview of all graphs in the dataset."""
    with tag("div", classes="p-4 flex flex-col gap-6"):
        with tag(
            "h2",
            classes="text-2xl font-bold text-gray-800 dark:text-gray-200",
        ):
            text("Available Graphs")

        with tag("div", classes="grid gap-4"):
            # Get all non-formula graphs and sort by triple count (largest first)
            graphs = [
                g
                for g in dataset.graphs()
                if not isinstance(g, QuotedGraph)
            ]

            for graph in sorted(graphs, key=len, reverse=True):
                render_graph_summary(graph)


def render_graph_summary(graph: Graph) -> None:
    """Render a summary card for a single graph."""
    subject_count = len(set(graph.subjects()))
    triple_count = len(graph)

    with tag(
        "div",
        classes="border rounded-lg p-4 bg-white dark:bg-gray-800 shadow-sm hover:shadow-md transition-shadow",
    ):
        # Header with graph ID and stats
        with tag("div", classes="flex justify-between items-start mb-4"):
            # Graph ID as link
            with tag(
                "a",
                href=f"/graph?graph={str(graph.identifier)}",
                classes="text-lg font-medium text-blue-600 dark:text-blue-400 hover:underline",
            ):
                text(str(graph.identifier))

            # Stats
            with tag(
                "div", classes="text-sm text-gray-500 dark:text-gray-400"
            ):
                text(f"{subject_count} subjects, {triple_count} triples")

        # Preview of typed resources
        typed_subjects = {s for s in graph.subjects(RDF.type, None)}
        if typed_subjects:
            with tag("div", classes="mt-2"):
                with tag(
                    "h4",
                    classes="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2",
                ):
                    text("Resource Types")

                type_counts = defaultdict(int)
                for s in typed_subjects:
                    for t in graph.objects(s, RDF.type):
                        type_counts[t] += 1

                with tag("div", classes="flex flex-wrap gap-2"):
                    for rdf_type, count in sorted(
                        type_counts.items(),
                        key=lambda x: (-x[1], str(x[0])),
                    ):
                        with tag(
                            "span",
                            classes="px-2 py-1 text-xs rounded-full bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200",
                        ):
                            text(
                                f"{str(rdf_type).split('#')[-1].split('/')[-1]} ({count})"
                            )


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
