from typing import (
    Dict,
    Self,
    Callable,
    ClassVar,
    Iterable,
    Optional,
    Awaitable,
    AsyncGenerator,
)
from contextlib import asynccontextmanager
from dataclasses import dataclass

import structlog

from trio import Nursery
from rdflib import PROV, Graph, URIRef, Literal

from swash.prfx import NT
from swash.util import add, new, is_a, get_single_object
from bubble.mesh.mesh import (
    ServerActor,
    boss,
    this,
    spawn,
    persist,
    txgraph,
    with_transient_graph,
)
from bubble.repo.repo import context, timestamp
from bubble.deepgram.talk import DeepgramClientActor
from bubble.replicate.make import AsyncReadable, make_image, make_video
from bubble.apis.recraft import RecraftAPI

import httpx
from pathlib import Path
from typing import cast
import tempfile
import os

logger = structlog.get_logger()


@dataclass
class DispatchContext:
    """Context for message dispatch handling."""

    nursery: Nursery
    graph: Graph
    request_id: URIRef


# ------------------------------------
# Helper Functions
# ------------------------------------


@asynccontextmanager
async def persist_graph_changes(graph_id: URIRef):
    """Context manager to bind to a graph, apply updates, and persist changes."""
    with context.bind_graph(graph_id) as sheet:
        try:
            yield sheet
            await persist(sheet)
        finally:
            pass  # Any cleanup if needed


@asynccontextmanager
async def new_persistent_graph() -> AsyncGenerator[URIRef, None]:
    async with txgraph() as graph:
        assert isinstance(graph.identifier, URIRef)
        yield graph.identifier


def create_button(
    label: str,
    icon: Optional[str],
    message_type: URIRef,
    target: Optional[URIRef] = None,
) -> URIRef:
    """Create a button affordance with a given label and message type."""
    return new(
        NT.Button,
        {
            NT.label: Literal(label, "en"),
            NT.icon: icon,
            NT.message: message_type,
            NT.target: target or this(),
        },
    )


def create_prompt(
    label: str,
    placeholder: str,
    message_type: URIRef,
    target: Optional[URIRef] = None,
) -> URIRef:
    """Create a prompt affordance for text, image, or video generation."""
    return new(
        NT.Prompt,
        {
            NT.label: Literal(label, "en"),
            NT.placeholder: Literal(placeholder, "en"),
            NT.message: message_type,
            NT.target: target or this(),
        },
    )


async def add_affordance_to_sheet(graph_id: URIRef, affordance: URIRef):
    """Add an affordance to the sheet and persist."""
    async with persist_graph_changes(graph_id):
        add(graph_id, {NT.affordance: affordance})


async def spawn_actor(nursery, actor_class, name: str) -> URIRef:
    """Spawn a new actor and return the actor's URIRef."""
    actor = actor_class()
    actor_uri = await spawn(nursery, actor, name=name)
    #    await actor.setup(actor_uri)
    return actor_uri


async def store_generated_assets(
    graph_id: URIRef, readables: Iterable[AsyncReadable], mime_type: str
):
    """Store binary assets in the repository and link them to the graph."""
    async with persist_graph_changes(graph_id):
        distributions = []
        for readable in readables:
            data = await readable.aread()
            distribution = await context.repo.get().save_blob(
                data, mime_type
            )
            add(
                distribution,
                {
                    PROV.wasGeneratedBy: this(),
                    PROV.generatedAtTime: timestamp(),
                },
            )
            distributions.append(distribution)

        if len(distributions) > 1:
            thing = new(
                PROV.Collection, {PROV.hadMember: set(distributions)}
            )
        elif len(distributions) == 1:
            thing = distributions[0]
        else:
            raise ValueError("No distributions to store")

        add(graph_id, {PROV.hadMember: thing})

        return thing


# ------------------------------------
# Dispatching Actor
# ------------------------------------


def handler[T](msg_type: URIRef) -> Callable[[T], T]:
    """
    A decorator to register a handler method for a given message type.
    The decorator attaches the message type to the function so it can be
    picked up by the class-level introspection.
    """

    def decorator(fn: T) -> T:
        setattr(fn, "_handler_msg_type", msg_type)
        return fn

    return decorator


class DispatchingActor(ServerActor[None]):
    """A base actor that provides structured message handling via decorators.

    This class is intended to be subclassed by actors that need to handle
    messages and persist changes to their own identity graphs, which we call
    sheets because they are mutable containers for content.
    """

    _message_handlers: ClassVar[
        Dict[URIRef, Callable[[Self, DispatchContext], Awaitable[Graph]]]
    ] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # Collect all handler methods from this class.
        handlers: Dict[
            URIRef, Callable[[Self, DispatchContext], Awaitable[Graph]]
        ] = {}

        for name, method in cls.__dict__.items():
            msg_type = getattr(method, "_handler_msg_type", None)
            if msg_type is not None and callable(method):
                handlers[msg_type] = method

        # Merge this class's handlers with any inherited ones
        # so that derived classes don't lose their parent class handlers.
        cls._message_handlers = {
            **getattr(cls, "_message_handlers", {}),
            **handlers,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(None)

    async def setup(self, actor_uri: URIRef):
        pass

    async def handle(self, nursery: Nursery, graph: Graph) -> Graph:
        request_id = graph.identifier
        if not isinstance(request_id, URIRef):
            raise ValueError(
                f"Expected URIRef identifier, got {type(request_id)}"
            )

        ctx = DispatchContext(
            nursery=nursery,
            graph=graph,
            request_id=request_id,
        )

        for msg_type, handler_method in self._message_handlers.items():
            if is_a(request_id, msg_type, graph):
                return await handler_method(self, ctx)

        raise ValueError(f"Unexpected message type: {request_id}")

    def current_graph(self) -> Graph:
        """Convenience to return the current context graph."""
        return context.graph.get()


# ------------------------------------
# Specific Actors
# ------------------------------------


class NoteEditor(DispatchingActor):
    async def setup(self, actor_uri: URIRef):
        """Initialize by creating a TextEditor affordance."""
        new(
            NT.TextEditor,
            {
                NT.placeholder: Literal("Type something...", "en"),
                NT.message: URIRef(NT.TextUpdate),
                #                NT.target: actor_uri,
                NT.text: Literal("", "en"),
            },
            actor_uri,
        )

    @handler(NT.TextUpdate)
    async def handle_text_update(self, ctx: DispatchContext):
        new_text = get_single_object(ctx.request_id, NT.text, ctx.graph)
        async with persist_graph_changes(this()) as graph:
            graph.set((this(), NT.text, Literal(new_text, lang="en")))
            graph.set((this(), NT.modifiedAt, timestamp()))
        with with_transient_graph() as graph:
            add(graph, {PROV.revisedEntity: this()})
            return context.graph.get()


class ImageGenerator(DispatchingActor):
    async def setup(self, actor_uri: URIRef):
        new(
            NT.ImageGenerator,
            {
                NT.affordance: create_prompt(
                    "Image Prompt",
                    "Enter an image prompt...",
                    NT.GenerateImage,
                    actor_uri,
                )
            },
            actor_uri,
        )

    @handler(NT.GenerateImage)
    async def handle_generate_image(self, ctx: DispatchContext):
        prompt = get_single_object(ctx.request_id, NT.prompt, ctx.graph)
        readables = await make_image(prompt)
        thing = await store_generated_assets(
            boss(), readables, "image/webp"
        )
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: thing})
            return context.graph.get()


class VideoGenerator(DispatchingActor):
    async def setup(self, actor_uri: URIRef):
        new(
            NT.VideoGenerator,
            {
                NT.affordance: create_prompt(
                    "Video Prompt",
                    "Enter a video prompt...",
                    NT.GenerateVideo,
                    actor_uri,
                )
            },
            actor_uri,
        )

    @handler(NT.GenerateVideo)
    async def handle_generate_video(self, ctx: DispatchContext):
        prompt = get_single_object(ctx.request_id, NT.prompt, ctx.graph)
        readables = await make_video(prompt)
        thing = await store_generated_assets(boss(), readables, "video/mp4")
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: thing})
            return context.graph.get()


class ImageUploader(DispatchingActor):
    async def setup(self, actor_uri: URIRef):
        """Initialize by creating an ImageUploader with upload affordance."""
        new(
            NT.ImageUploader,
            {
                NT.affordance: new(
                    NT.ImageUploadForm,
                    {
                        NT.label: Literal("Upload Image", "en"),
                        NT.message: NT.UploadImage,
                        NT.target: actor_uri,
                        NT.accept: Literal("image/*"),
                    },
                )
            },
            actor_uri,
        )

    @handler(NT.UploadImage)
    async def handle_upload_image(self, ctx: DispatchContext):
        """Handle image upload by saving to repo and optionally modifying the background."""
        # Get the uploaded file from the message
        file_node = get_single_object(
            ctx.request_id, NT.fileData, ctx.graph
        )

        # Extract file data and mime type from NT.File structure
        file_data = get_single_object(file_node, NT.data, ctx.graph)
        mime_type = get_single_object(file_node, NT.mimeType, ctx.graph)

        # Convert file_data to bytes
        file_bytes = cast(bytes, file_data.toPython())

        # Save the original image to the repository
        distribution = await context.repo.get().save_blob(
            file_bytes, mime_type
        )

        # Add provenance information
        add(
            distribution,
            {
                PROV.wasGeneratedBy: this(),
                PROV.generatedAtTime: timestamp(),
            },
        )

        # Get background option
        bg_option = get_single_object(
            ctx.request_id, NT.backgroundOption, ctx.graph
        )

        if bg_option and bg_option != Literal("none"):
            try:
                # Create temporary file for Recraft API
                with tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False
                ) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = tmp.name

                try:
                    # Process the image using Recraft API
                    recraft = RecraftAPI()

                    processed_url = None
                    if bg_option == Literal("remove"):
                        processed_url = await recraft.remove_background(
                            tmp_path
                        )
                    elif bg_option == Literal("modify"):
                        bg_prompt = get_single_object(
                            ctx.request_id, NT.backgroundPrompt, ctx.graph
                        )
                        if not bg_prompt:
                            raise ValueError(
                                "Background prompt is required for modification"
                            )
                        processed_url = await recraft.modify_background(
                            tmp_path, str(bg_prompt)
                        )

                    if not processed_url:
                        raise ValueError(
                            f"Invalid background option: {bg_option}"
                        )

                    # Add the processed version
                    async with httpx.AsyncClient() as client:
                        response = await client.get(processed_url)
                        response.raise_for_status()
                        processed_data = response.content

                    processed_dist = await context.repo.get().save_blob(
                        processed_data, mime_type
                    )
                    add(
                        processed_dist,
                        {
                            PROV.wasGeneratedBy: this(),
                            PROV.generatedAtTime: timestamp(),
                            NT.backgroundModified: Literal(True),
                            NT.backgroundOption: bg_option,
                        },
                    )
                    distribution = processed_dist
                finally:
                    # Clean up the temporary file
                    os.unlink(tmp_path)

            except Exception as e:
                logger.error("Failed to process background", error=e)
                # Continue with original image if background processing fails

        with with_transient_graph() as graph:
            add(graph, {PROV.generated: distribution})
            return context.graph.get()


class SheetEditor(DispatchingActor):
    async def setup(self, actor_uri: URIRef):
        """Initialize by creating a SheetEditor with affordances."""
        new(
            NT.SheetEditor,
            {
                NT.affordance: {
                    create_button(
                        "New Note",
                        icon="✏️",
                        message_type=NT.AddNote,
                        target=actor_uri,
                    ),
                    create_button(
                        "New Speech",
                        icon="🎤",
                        message_type=NT.RecordVoice,
                        target=actor_uri,
                    ),
                    create_button(
                        "New Image",
                        icon="🖼️",
                        message_type=NT.MakeImage,
                        target=actor_uri,
                    ),
                    create_button(
                        "Upload Image",
                        icon="📤",
                        message_type=NT.AddImageUploader,
                        target=actor_uri,
                    ),
                    create_button(
                        "New Video",
                        icon="🎥",
                        message_type=NT.MakeVideo,
                        target=actor_uri,
                    ),
                },
            },
            actor_uri,
        )

    @handler(NT.AddNote)
    async def handle_add_note(self, ctx: DispatchContext):
        actor_uri = await spawn_actor(
            ctx.nursery, NoteEditor, "note editor"
        )
        await add_affordance_to_sheet(this(), actor_uri)
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: actor_uri})
            return context.graph.get()

    @handler(NT.MakeImage)
    async def handle_make_image(self, ctx: DispatchContext):
        actor_uri = await spawn_actor(
            ctx.nursery, ImageGenerator, "image generator"
        )
        await add_affordance_to_sheet(this(), actor_uri)
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: actor_uri})
            return context.graph.get()

    @handler(NT.MakeVideo)
    async def handle_make_video(self, ctx: DispatchContext):
        actor_uri = await spawn_actor(
            ctx.nursery, VideoGenerator, "video generator"
        )
        await add_affordance_to_sheet(this(), actor_uri)
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: actor_uri})
            return context.graph.get()

    @handler(NT.RecordVoice)
    async def handle_record_voice(self, ctx: DispatchContext):
        actor_uri = await spawn_actor(
            ctx.nursery, DeepgramClientActor, "voice recorder"
        )
        await add_affordance_to_sheet(this(), actor_uri)
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: actor_uri})
            return context.graph.get()

    @handler(NT.AddImageUploader)
    async def handle_add_image_uploader(self, ctx: DispatchContext):
        actor_uri = await spawn_actor(
            ctx.nursery, ImageUploader, "image uploader"
        )
        await add_affordance_to_sheet(this(), actor_uri)
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: actor_uri})
            return context.graph.get()


class SheetCreator(DispatchingActor):
    async def setup(self, actor_uri: URIRef):
        """Initialize by creating a SheetCreator with a 'New Sheet' button."""
        new(
            NT.SheetCreator,
            {
                NT.affordance: create_button(
                    "New Sheet",
                    icon="📝",
                    message_type=NT.CreateSheet,
                    target=actor_uri,
                )
            },
            actor_uri,
        )

    @handler(NT.CreateSheet)
    async def handle_create_sheet(self, ctx: DispatchContext):
        async with new_persistent_graph():
            editor_uri = await spawn_actor(
                ctx.nursery,
                SheetEditor,
                name="sheet editor",
            )

        with with_transient_graph() as graph:
            add(graph, {PROV.generated: editor_uri})
            return context.graph.get()
