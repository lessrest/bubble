from rdflib import PROV, URIRef

from swash.prfx import NT
from swash.util import add, new
from bubble.http.tool import (
    DispatchContext,
    DispatchingActor,
    handler,
    spawn_actor,
    create_button,
    add_affordance_to_sheet,
)
from bubble.mesh.base import this, with_transient_graph
from bubble.repo.repo import context


class SheetEditor(DispatchingActor):
    async def setup(self, actor_uri: URIRef):
        buttons = [
            ("Post Note", "✏️", NT.AddNote),
            ("Post Image", "📤", NT.UploadImage),
            ("Make Image", "🖼️", NT.MakeImage),
            ("Make Video", "🎥", NT.MakeVideo),
            ("Save Video", "⬇️", NT.FetchVideo),
            ("Hear Speech", "🎤", NT.HearSpeech),
        ]

        new(
            NT.SheetEditor,
            {
                NT.affordance: {
                    create_button(
                        label, icon=icon, message_type=msg, target=actor_uri
                    )
                    for label, icon, msg in buttons
                },
            },
            actor_uri,
        )

    async def make(self, ctx: DispatchContext, actor_class):
        actor_uri = await spawn_actor(ctx.nursery, actor_class)
        await add_affordance_to_sheet(this(), actor_uri)
        with with_transient_graph() as graph:
            add(graph, {PROV.generated: actor_uri})
            return context.buffer.get()

    @handler(NT.PostNote)
    async def post_note(self, ctx: DispatchContext):
        from bubble.tool.note import NoteEditor

        return await self.make(ctx, NoteEditor)

    @handler(NT.MakeImage)
    async def make_image(self, ctx: DispatchContext):
        from bubble.tool.genimg import ImageGenerator

        return await self.make(ctx, ImageGenerator)

    @handler(NT.MakeVideo)
    async def make_video(self, ctx: DispatchContext):
        from bubble.tool.genvid import VideoGenerator

        return await self.make(ctx, VideoGenerator)

    @handler(NT.HearSpeech)
    async def hear_speech(self, ctx: DispatchContext):
        from bubble.deepgram.talk import DeepgramClientActor

        return await self.make(ctx, DeepgramClientActor)

    @handler(NT.UploadImage)
    async def upload_image(self, ctx: DispatchContext):
        from bubble.tool.putimg import ImageUploader

        return await self.make(ctx, ImageUploader)

    @handler(NT.FetchVideo)
    async def fetch_video(self, ctx: DispatchContext):
        from bubble.tool.youtube import YouTubeDownloader

        return await self.make(ctx, YouTubeDownloader)
