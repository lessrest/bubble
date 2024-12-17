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

logger = structlog.get_logger()


class TextTypingActor(ServerActor[None]):
    """Actor that handles text typing events for a specific note."""

    note_id: URIRef
    graph_id: URIRef

    def __init__(self, note_id: URIRef, graph_id: URIRef):
        """Initialize the actor with the ID of the note to update.

        Args:
            note_id: URIRef identifying the note this actor will update
        """
        super().__init__(None)
        self.note_id = note_id
        self.graph_id = graph_id

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
                sheet.set(
                    (self.note_id, NT.text, Literal(new_text, lang="en"))
                )
                sheet.set((self.note_id, NT.modifiedAt, timestamp()))
                await persist(sheet)

            with with_transient_graph() as result:
                add(
                    result,
                    {NT.isResponseTo: request_id, NT.status: NT.Success},
                )
                return context.graph.get()
        else:
            raise ValueError(f"Unexpected message type: {request_id}")


class SheetEditingActor(ServerActor[None]):
    def __init__(self, graph_id: URIRef):
        super().__init__(None)
        self.graph_id = graph_id

    async def handle(self, nursery, graph: Graph) -> Graph:
        logger.info("Sheet actor handling message", graph=graph)
        request_id = graph.identifier

        if not is_a(request_id, NT.AddNote, graph):
            raise ValueError(f"Unexpected message type: {request_id}")

        # Create a new note in the sheet graph
        with context.bind_graph(self.graph_id) as sheet:
            note = new(
                NT.Note,
                {
                    NT.text: Literal("", lang="en"),
                    NT.createdAt: timestamp(),
                }
            )
            
            # Add the note to the sheet
            add(
                self.graph_id,
                {
                    PROV.hadMember: note,
                }
            )
            await persist(sheet)

            # Spawn a text typing actor for the new note
            typing_actor = await spawn(
                nursery,
                TextTypingActor(note, self.graph_id),
                name=f"Text typing actor for {note}",
            )

            # Return success response with note and actor references
            with with_transient_graph() as result:
                add(
                    result,
                    {
                        NT.isResponseTo: request_id,
                        NT.status: NT.Success,
                        NT.note: note,
                        NT.editor: typing_actor,
                    },
                )
                return context.graph.get()


class SheetCreatingActor(ServerActor[None]):
    def __init__(self, graph_id: URIRef):
        super().__init__(None)
        self.graph_id = graph_id
        
    async def init(self):
        """Initialize the actor by marking it as a SheetCreator."""
        async with txgraph():
            new(NT.SheetCreator, {}, this())

    async def handle(self, nursery, graph: Graph) -> Graph:
        logger.info("Sheet creating actor handling message", graph=graph)
        request_id = graph.identifier

        if not is_a(request_id, NT.CreateSheet, graph):
            raise ValueError(f"Unexpected message type: {request_id}")

        # Create a new sheet graph
        async with txgraph() as sheet_graph:
            assert isinstance(sheet_graph.identifier, URIRef)
            new(
                NT.Sheet,
                {
                    PROV.generatedAtTime: timestamp(),
                },
                sheet_graph.identifier,
            )

            # Spawn new sheet editing actor for this sheet
            editor = await spawn(
                nursery,
                SheetEditingActor(sheet_graph.identifier),
                name=f"Sheet editor for {sheet_graph.identifier}",
            )

            # Return success response with editor reference and sheet id
            with with_transient_graph() as result:
                add(
                    result,
                    {
                        NT.isResponseTo: request_id,
                        NT.status: NT.Success,
                        NT.editor: editor,
                        NT.sheet: sheet_graph.identifier,
                    },
                )
                return context.graph.get()
