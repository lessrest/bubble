"""
Simple Text Typing Actor
=======================

This module implements a simple actor that receives text messages and updates
the text value of an NT.Note resource. It's designed to provide real-time
text editing functionality within the semantic graph structure.
"""

import structlog
from typing import Optional
from rdflib import Graph, URIRef, Literal, PROV

from swash.prfx import NT
from swash.util import add, get_single_object, is_a, new
from bubble.mesh import (
    ServerActor,
    persist,
    with_transient_graph,
    spawn,
    txgraph,
    this,
)
from bubble.data import context, timestamp
from bubble.replicate.make import make_image, make_video

logger = structlog.get_logger()


class TextTypingActor(ServerActor[None]):
    """Actor that handles text typing events for a specific note."""

    graph_id: URIRef

    def __init__(self, graph_id: URIRef):
        """Initialize the actor with the ID of the note to update.

        Args:
            note_id: URIRef identifying the note this actor will update
        """
        super().__init__(None)
        self.graph_id = graph_id

    async def init(self):
        """Initialize the actor by marking it as a TextTypingActor."""
        with context.bind_graph(self.graph_id) as sheet:
            new(
                NT.TextEditor,
                {
                    NT.placeholder: Literal("Type something...", "en"),
                    NT.message: URIRef(NT.TextUpdate),
                    NT.target: this(),
                    NT.text: Literal("", "en"),
                },
                this(),
            )

            await persist(sheet)

    async def handle(self, nursery, graph: Graph) -> Graph:
        """Handle incoming text update messages.

        The actor expects messages with an NT.text predicate containing
        the new text value.

        Args:
            nursery: Trio nursery for spawning child tasks
            graph: Input message graph

        Returns:
            Graph containing the response message
        """
        logger.info("Text typing actor handling message", graph=graph)
        request_id = graph.identifier

        if is_a(request_id, NT.TextUpdate, graph):
            new_text = get_single_object(request_id, NT.text, graph)
            with context.bind_graph(self.graph_id) as sheet:
                sheet.set((this(), NT.text, Literal(new_text, lang="en")))
                sheet.set((this(), NT.modifiedAt, timestamp()))
                await persist(sheet)

                return context.graph.get()
        else:
            raise ValueError(f"Unexpected message type: {request_id}")


class ImageGenerationActor(ServerActor[None]):
    def __init__(self, graph_id: URIRef):
        super().__init__(None)
        self.graph_id = graph_id

    async def init(self):
        with context.bind_graph(self.graph_id) as sheet:
            new(
                NT.Prompt,
                {
                    NT.label: Literal("Image Prompt", "en"),
                    NT.placeholder: Literal(
                        "Enter an image prompt...", "en"
                    ),
                    NT.message: URIRef(NT.GenerateImage),
                    NT.target: this(),
                },
                this(),
            )

            await persist(sheet)

    async def handle(self, nursery, graph: Graph) -> Graph:
        logger.info("Image generation actor handling message", graph=graph)
        request_id = graph.identifier

        if is_a(request_id, NT.GenerateImage, graph):
            prompt = get_single_object(request_id, NT.prompt, graph)
            with context.bind_graph(self.graph_id) as sheet:
                readables = await make_image(prompt)

                # Store the generated images and add them to the response
                for readable in readables:
                    img = await readable.aread()
                    distribution = await context.repo.get().save_blob(
                        img, "image/webp"
                    )
                    add(
                        distribution,
                        {
                            PROV.wasGeneratedBy: this(),
                            PROV.generatedAtTime: timestamp(),
                        },
                    )
                    add(self.graph_id, {PROV.hadMember: distribution})

                await persist(sheet)
                return context.graph.get()
        else:
            raise ValueError(f"Unexpected message type: {request_id}")


class VideoGenerationActor(ServerActor[None]):
    def __init__(self, graph_id: URIRef):
        super().__init__(None)
        self.graph_id = graph_id

    async def init(self):
        with context.bind_graph(self.graph_id) as sheet:
            new(
                NT.Prompt,
                {
                    NT.label: Literal("Video Prompt", "en"),
                    NT.placeholder: Literal(
                        "Enter a video prompt...", "en"
                    ),
                    NT.message: URIRef(NT.GenerateVideo),
                    NT.target: this(),
                },
                this(),
            )

            await persist(sheet)

    async def handle(self, nursery, graph: Graph) -> Graph:
        logger.info("Video generation actor handling message", graph=graph)
        request_id = graph.identifier

        if is_a(request_id, NT.GenerateVideo, graph):
            prompt = get_single_object(request_id, NT.prompt, graph)
            with context.bind_graph(self.graph_id) as sheet:
                readables = await make_video(prompt)

                # Store the generated videos and add them to the response
                for readable in readables:
                    video = await readable.aread()
                    distribution = await context.repo.get().save_blob(
                        video, "video/mp4"
                    )
                    add(
                        distribution,
                        {
                            PROV.wasGeneratedBy: this(),
                            PROV.generatedAtTime: timestamp(),
                        },
                    )
                    add(self.graph_id, {PROV.hadMember: distribution})

                await persist(sheet)
                return context.graph.get()
        else:
            raise ValueError(f"Unexpected message type: {request_id}")


class SheetEditingActor(ServerActor[None]):
    def __init__(self, graph_id: URIRef):
        super().__init__(None)
        self.graph_id = graph_id

    async def init(self):
        """Initialize the actor by marking it as a SheetEditor."""
        async with txgraph():
            new(
                NT.SheetEditor,
                {
                    NT.affordance: set(
                        [
                            new(
                                NT.Button,
                                {
                                    NT.label: Literal("Type", "en"),
                                    NT.message: URIRef(NT.AddNote),
                                    NT.target: this(),
                                },
                            ),
                            new(
                                NT.Button,
                                {
                                    NT.label: Literal("Make Image", "en"),
                                    NT.message: URIRef(NT.MakeImage),
                                    NT.target: this(),
                                },
                            ),
                            new(
                                NT.Button,
                                {
                                    NT.label: Literal("Make Video", "en"),
                                    NT.message: URIRef(NT.MakeVideo),
                                    NT.target: this(),
                                },
                            ),
                        ]
                    ),
                },
                this(),
            )

    async def handle(self, nursery, graph: Graph) -> Graph:
        logger.info("Sheet actor handling message", graph=graph)
        request_id = graph.identifier

        if is_a(request_id, NT.AddNote, graph):
            # Create a new note in the sheet graph
            with context.bind_graph(self.graph_id) as sheet:
                add(
                    self.graph_id,
                    {
                        NT.affordance: await spawn(
                            nursery,
                            TextTypingActor(self.graph_id),
                            name="note editor",
                        ),
                    },
                )

                await persist(sheet)
                return context.graph.get()

        elif is_a(request_id, NT.MakeImage, graph):
            with context.bind_graph(self.graph_id) as sheet:
                add(
                    self.graph_id,
                    {
                        NT.affordance: await spawn(
                            nursery,
                            ImageGenerationActor(self.graph_id),
                            name="image generator",
                        ),
                    },
                )
                await persist(sheet)
                return context.graph.get()

        elif is_a(request_id, NT.MakeVideo, graph):
            with context.bind_graph(self.graph_id) as sheet:
                add(
                    self.graph_id,
                    {
                        NT.affordance: await spawn(
                            nursery,
                            VideoGenerationActor(self.graph_id),
                            name="video generator",
                        ),
                    },
                )
                await persist(sheet)
                return context.graph.get()

        else:
            raise ValueError(f"Unexpected message type: {request_id}")


class SheetCreatingActor(ServerActor[None]):
    def __init__(self, graph_id: URIRef):
        super().__init__(None)
        self.graph_id = graph_id

    async def init(self):
        """Initialize the actor by marking it as a SheetCreator."""
        async with txgraph():
            new(
                NT.SheetCreator,
                {
                    NT.affordance: new(
                        NT.Button,
                        {
                            NT.label: Literal("New Sheet", "en"),
                            NT.message: URIRef(NT.CreateSheet),
                            NT.target: this(),
                        },
                    )
                },
                this(),
            )

    async def handle(self, nursery, graph: Graph) -> Graph:
        logger.info("Sheet creating actor handling message", graph=graph)
        request_id = graph.identifier

        if not is_a(request_id, NT.CreateSheet, graph):
            raise ValueError(f"Unexpected message type: {request_id}")

        # Create a new sheet graph
        async with txgraph() as sheet_graph:
            assert isinstance(sheet_graph.identifier, URIRef)

            # Spawn new sheet editing actor for this sheet
            editor = await spawn(
                nursery,
                SheetEditingActor(sheet_graph.identifier),
                name=f"Sheet editor for {sheet_graph.identifier}",
            )

            new(
                NT.Sheet,
                {
                    PROV.generatedAtTime: timestamp(),
                    NT.affordance: editor,
                },
                sheet_graph.identifier,
            )

            return context.graph.get()
