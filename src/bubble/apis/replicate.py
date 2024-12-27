import os
import functools

from typing import Protocol, runtime_checkable
from datetime import UTC, datetime

import trio
import replicate
import structlog
import trio_asyncio

from rdflib import PROV, Graph, URIRef, Literal, Namespace

from swash.prfx import NT
from swash.util import add, new, is_a, get_single_object
from bubble.mesh.otp import (
    ServerActor,
)
from bubble.mesh.base import this, txgraph
from bubble.repo.repo import Repository

logger = structlog.get_logger(__name__)

# Create Replicate namespace
Replicate = Namespace("https://replicate.com/ns#")


@runtime_checkable
class AsyncReadable(Protocol):
    async def aread(self) -> bytes: ...


async def make_image(prompt: str) -> list[AsyncReadable]:
    f = functools.partial(
        replicate.async_run,
        "recraft-ai/recraft-v3",
        # "black-forest-labs/flux-dev",
        input={
            "prompt": prompt,
            "size": "2048x1024",
            #    "style": "realistic_image",
            #   "num_outputs": 2,
            #            "disable_safety_checker": True,
        },
    )
    result = await trio_asyncio.aio_as_trio(f)()
    logger.info("replicate.make.image", result=result)

    if isinstance(result, list):
        return result
    else:
        return [result]


async def make_video(prompt: str) -> list[AsyncReadable]:
    f = functools.partial(
        replicate.async_run,
        "minimax/video-01",
        input={"prompt": prompt, "prompt_optimizer": True},
    )
    result = await trio_asyncio.aio_as_trio(f)()
    logger.info("replicate.make.video", result=result)

    if isinstance(result, list):
        return result
    else:
        return [result]


class ReplicateClientActor(ServerActor):
    """Actor that manages image generation requests"""

    store: Repository

    def __init__(self, store: Repository):
        super().__init__()
        self.state = os.environ["REPLICATE_API_TOKEN"]
        self.store = store

    async def init(self):
        await super().init()
        async with txgraph():
            create_prompt_affordance(this())

    async def handle(self, nursery: trio.Nursery, graph: Graph) -> Graph:
        logger.info("Replicate client actor handling message", graph=graph)

        async with txgraph(graph) as result:
            add(result.identifier, {NT.isResponseTo: graph.identifier})

            if is_a(graph.identifier, Replicate.Generate):
                prompt = get_single_object(graph.identifier, NT.prompt)
                logger.info("Starting image generation", prompt=prompt)

                # Generate the images directly
                readables = await make_image(prompt)

                # Store the generated images and add them to the response
                for readable in readables:
                    img = await readable.aread()
                    distribution = await self.store.save_blob(
                        img, "image/webp"
                    )
                    add(
                        distribution,
                        {
                            PROV.wasGeneratedBy: this(),
                            PROV.generatedAtTime: Literal(
                                datetime.now(UTC)
                            ),
                        },
                    )
                    add(result.identifier, {PROV.generated: distribution})

            return result


def create_prompt_affordance(replicate_client: URIRef):
    """Create the prompt affordance for the Replicate client"""
    return new(
        Replicate.Client,
        {
            NT.affordance: new(
                NT.Prompt,
                {
                    NT.label: Literal("Generate Image", "en"),
                    NT.message: Replicate.Generate,
                    NT.target: replicate_client,
                    NT.placeholder: Literal(
                        "Describe the image you want to generate...", "en"
                    ),
                },
            )
        },
        subject=replicate_client,
    )
