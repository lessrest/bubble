"""Tool Instantiation: Where Tools Come Together

This module instantiates and manages all the specific tools in the system.
It imports the tool implementations and provides them to the sheet editor.
"""

import os
import tempfile
from datetime import UTC, datetime
from typing import cast, List, Tuple, Sequence

import httpx
import structlog
from rdflib import PROV, Graph, Literal, URIRef

from bubble.mesh.base import (
    boss,
    persist,
    spawn,
    this,
    txgraph,
    with_transient_graph,
)
from bubble.http.tool import (
    AsyncReadable,
    DispatchingActor,
    create_button,
    create_prompt,
    handler,
    add_affordance_to_sheet,
    DispatchContext,
    store_generated_assets,
    new_persistent_graph,
    persist_graph_changes,
    spawn_actor,
)
from bubble.youtube.tool import YouTubeDownloader
from bubble.deepgram.talk import DeepgramClientActor
from bubble.apis.recraft import RecraftAPI
from bubble.apis.replicate import make_image, make_video
from bubble.repo.repo import context, timestamp
from swash.prfx import NT
from swash.util import add, get_single_object, is_a, new

logger = structlog.get_logger()


class BytesReadable(AsyncReadable):
    """A simple AsyncReadable that reads from bytes in memory."""

    def __init__(self, data: bytes):
        self.data = data

    async def aread(self) -> bytes:
        return self.data


class NoteEditor(DispatchingActor):
    async def setup(self, actor_uri: URIRef):
        """Initialize by creating a TextEditor affordance."""
        new(
            NT.TextEditor,
            {
                NT.placeholder: Literal("Type something...", "en"),
                NT.message: URIRef(NT.TextUpdate),
                NT.text: Literal("", "en"),
            },
            actor_uri,
        )

    @handler(NT.TextUpdate)
    async def handle_text_update(self, ctx: DispatchContext):
        new_text = get_single_object(ctx.request_id, NT.text, ctx.buffer)
        async with persist_graph_changes(this()) as graph:
            graph.set((this(), NT.text, Literal(new_text, lang="en")))
            graph.set((this(), NT.modifiedAt, timestamp()))
        with with_transient_graph() as graph:
            add(graph, {PROV.revisedEntity: this()})
            return context.buffer.get()


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
        prompt = get_single_object(ctx.request_id, NT.prompt, ctx.buffer)
        readables = await make_image(prompt)
        assets: List[Tuple[AsyncReadable, str]] = [
            (readable, "image/webp") for readable in readables
        ]
        thing = await store_generated_assets(boss(), assets)
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: thing})
            return context.buffer.get()


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
        prompt = get_single_object(ctx.request_id, NT.prompt, ctx.buffer)
        readables = await make_video(prompt)
        assets: List[Tuple[AsyncReadable, str]] = [
            (readable, "video/mp4") for readable in readables
        ]
        thing = await store_generated_assets(boss(), assets)
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: thing})
            return context.buffer.get()


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
        file_node = get_single_object(
            ctx.request_id, NT.fileData, ctx.buffer
        )
        file_data = get_single_object(file_node, NT.data, ctx.buffer)
        mime_type = get_single_object(file_node, NT.mimeType, ctx.buffer)
        file_bytes = cast(bytes, file_data.toPython())

        assets: List[Tuple[AsyncReadable, str]] = [
            (BytesReadable(file_bytes), str(mime_type))
        ]
        distribution = await store_generated_assets(boss(), assets)
        add(
            distribution,
            {
                PROV.wasGeneratedBy: this(),
                PROV.generatedAtTime: timestamp(),
            },
        )

        bg_option = get_single_object(
            ctx.request_id, NT.backgroundOption, ctx.buffer
        )

        if bg_option and bg_option != Literal("none"):
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False
                ) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = tmp.name

                try:
                    recraft = RecraftAPI()
                    processed_url = None
                    if bg_option == Literal("remove"):
                        processed_url = await recraft.remove_background(
                            tmp_path
                        )
                    elif bg_option == Literal("modify"):
                        bg_prompt = get_single_object(
                            ctx.request_id, NT.backgroundPrompt, ctx.buffer
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

                    async with httpx.AsyncClient() as client:
                        response = await client.get(processed_url)
                        response.raise_for_status()
                        processed_data = response.content

                    processed_assets: List[Tuple[AsyncReadable, str]] = [
                        (BytesReadable(processed_data), str(mime_type))
                    ]
                    processed_dist = await store_generated_assets(
                        boss(), processed_assets
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
                    os.unlink(tmp_path)

            except Exception as e:
                logger.error("Failed to process background", error=e)

        with with_transient_graph() as graph:
            add(graph, {PROV.generated: distribution})
            return context.buffer.get()


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
                    create_button(
                        "Download Video",
                        icon="⬇️",
                        message_type=NT.AddYouTubeDownloader,
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
            return context.buffer.get()

    @handler(NT.MakeImage)
    async def handle_make_image(self, ctx: DispatchContext):
        actor_uri = await spawn_actor(
            ctx.nursery, ImageGenerator, "image generator"
        )
        await add_affordance_to_sheet(this(), actor_uri)
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: actor_uri})
            return context.buffer.get()

    @handler(NT.MakeVideo)
    async def handle_make_video(self, ctx: DispatchContext):
        actor_uri = await spawn_actor(
            ctx.nursery, VideoGenerator, "video generator"
        )
        await add_affordance_to_sheet(this(), actor_uri)
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: actor_uri})
            return context.buffer.get()

    @handler(NT.RecordVoice)
    async def handle_record_voice(self, ctx: DispatchContext):
        actor_uri = await spawn_actor(
            ctx.nursery, DeepgramClientActor, "voice recorder"
        )
        await add_affordance_to_sheet(this(), actor_uri)
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: actor_uri})
            return context.buffer.get()

    @handler(NT.AddImageUploader)
    async def handle_add_image_uploader(self, ctx: DispatchContext):
        actor_uri = await spawn_actor(
            ctx.nursery, ImageUploader, "image uploader"
        )
        await add_affordance_to_sheet(this(), actor_uri)
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: actor_uri})
            return context.buffer.get()

    @handler(NT.AddYouTubeDownloader)
    async def handle_add_youtube_downloader(self, ctx: DispatchContext):
        actor_uri = await spawn_actor(
            ctx.nursery, YouTubeDownloader, "youtube downloader"
        )
        await add_affordance_to_sheet(this(), actor_uri)
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: actor_uri})
            return context.buffer.get()


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
            return context.buffer.get()
