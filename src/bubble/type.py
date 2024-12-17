"""
Simple Text Typing Actor
=======================

This module implements a simple actor that receives text messages and updates
the text value of an NT.Note resource. It's designed to provide real-time
text editing functionality within the semantic graph structure.
"""

import structlog
from typing import Optional
from rdflib import Graph, URIRef, Literal

from swash.prfx import NT
from swash.util import add, get_single_object, is_a
from bubble.mesh import ServerActor, persist, with_transient_graph, spawn
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
        return graph


class SheetCreatingActor(ServerActor[None]):
    def __init__(self, graph_id: URIRef):
        super().__init__(None)
        self.graph_id = graph_id

    async def handle(self, nursery, graph: Graph) -> Graph:
        logger.info("Sheet creating actor handling message", graph=graph)
        request_id = graph.identifier

        if not is_a(request_id, NT.CreateSheet, graph):
            raise ValueError(f"Unexpected message type: {request_id}")

        # Create response graph
        with with_transient_graph() as result:
            # Spawn new sheet editing actor
            editor = await spawn(
                nursery,
                SheetEditingActor(self.graph_id),
                name=f"Sheet editor for {self.graph_id}"
            )
            
            # Return success response with editor reference
            add(
                result,
                {
                    NT.isResponseTo: request_id,
                    NT.status: NT.Success,
                    NT.editor: editor
                }
            )
            return context.graph.get()
