from rdflib import PROV, URIRef, Literal

from swash.prfx import NT
from swash.util import add, new, get_single_object
from bubble.http.tool import (
    DispatchContext,
    DispatchingActor,
    handler,
    persist_graph_changes,
)
from bubble.mesh.base import this, with_transient_graph
from bubble.repo.repo import context, timestamp


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
