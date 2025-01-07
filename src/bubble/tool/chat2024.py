from rdflib import PROV, URIRef, Literal

from swash.prfx import AS, NT
from swash.util import add, new, get_single_object
from bubble.http.tool import (
    DispatchContext,
    DispatchingActor,
    handler,
    spawn_actor,
    create_button,
    new_persistent_graph,
    persist_graph_changes,
)
from bubble.mesh.base import this, with_transient_graph
from bubble.repo.repo import context, timestamp


class DiscussionParticipant(DispatchingActor):
    def __init__(self, name: str, chat: URIRef):
        super().__init__()
        self.name = name
        self.chat = chat

    async def setup(self, actor_uri: URIRef):
        """Initialize by creating a DiscussionParticipation with message prompt."""
        new(
            NT.Participant,
            {
                NT.name: self.name,
                NT.affordance: [
                    new(
                        NT.Prompt,
                        {
                            NT.placeholder: Literal(
                                "Type a message...", "en"
                            ),
                            NT.message: NT.AddMessage,
                            NT.target: actor_uri,
                            NT.label: Literal("Send", "en"),
                        },
                    ),
                ],
            },
            actor_uri,
        )

    @handler(NT.AddMessage)
    async def handle_add_message(self, ctx: DispatchContext):
        message = get_single_object(ctx.request_id, NT.prompt, ctx.buffer)
        async with persist_graph_changes(this()):
            add(
                self.chat,
                {
                    NT.hasPart: new(
                        AS.Note,
                        {
                            AS.content: Literal(message, lang="en"),
                            AS.published: timestamp(),
                            AS.actor: this(),
                        },
                    )
                },
            )
        with with_transient_graph() as graph:
            add(graph, {PROV.revisedEntity: this()})
            return context.buffer.get()


class ChatSession(DispatchingActor):
    def __init__(self):
        super().__init__()
        self.timeline = new(NT.Timeline)

    async def setup(self, actor_uri: URIRef):
        new(
            NT.Discussion,
            {
                NT.affordance: [
                    new(
                        NT.Prompt,
                        {
                            NT.placeholder: Literal("Type a name...", "en"),
                            NT.message: NT.AddParticipant,
                            NT.target: actor_uri,
                            NT.label: Literal("Add Participant", "en"),
                        },
                    ),
                    self.timeline,
                ]
            },
            actor_uri,
        )

    @handler(NT.AddParticipant)
    async def handle_add_participant(self, ctx: DispatchContext):
        name = get_single_object(ctx.request_id, NT.prompt, ctx.buffer)
        actor_uri = await spawn_actor(
            ctx.nursery, DiscussionParticipant, name, self.timeline
        )
        # await add_affordance_to_sheet(this(), actor_uri)
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: actor_uri})
            return context.buffer.get()


class ChatCreator(DispatchingActor):
    async def setup(self, actor_uri: URIRef):
        """Initialize by creating a ChatCreator with a 'New Chat' button."""
        new(
            NT.SheetCreator,
            {
                NT.affordance: create_button(
                    "New Chat",
                    icon="💬",
                    message_type=NT.CreateChat,
                    target=actor_uri,
                )
            },
            actor_uri,
        )

    @handler(NT.CreateChat)
    async def handle_create_chat(self, ctx: DispatchContext):
        async with new_persistent_graph():
            editor_uri = await spawn_actor(
                ctx.nursery,
                ChatSession,
                name="chat session",
            )

        with with_transient_graph() as graph:
            add(graph, {PROV.generated: editor_uri})
            return context.buffer.get()
