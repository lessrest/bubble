from typing import List, Tuple

from rdflib import PROV, URIRef

from swash.prfx import NT
from swash.util import add, new, get_single_object
from bubble.http.tool import (
    AsyncReadable,
    DispatchContext,
    DispatchingActor,
    handler,
    create_prompt,
    store_generated_assets,
)
from bubble.mesh.base import boss, with_transient_graph
from bubble.repo.repo import context
from bubble.apis.replicate import make_image


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
