import os
from typing import Any, Protocol, runtime_checkable
from datetime import UTC, datetime
from urllib.parse import urlencode

import trio
import trio_asyncio
import replicate
import structlog
from rdflib import PROV, URIRef, Literal, XSD, Graph, Namespace

from swash.prfx import NT, Schema
import swash.vars as vars
from swash.util import add, new, is_a, get_single_object
from bubble.blob import BlobStore
from bubble.mesh import (
    ServerActor,
    get_base,
    receive,
    send,
    spawn,
    this,
    txgraph,
    with_transient_graph,
)

logger = structlog.get_logger(__name__)

# Create Replicate namespace
Replicate = Namespace("https://replicate.com/ns#")


@runtime_checkable
class AsyncReadable(Protocol):
    async def aread(self) -> bytes: ...


async def make_image(prompt: str) -> list[AsyncReadable]:
    result = await trio_asyncio.aio_as_trio(
        replicate.async_run(
            "recraft-ai/recraft-v3",
            # "black-forest-labs/flux-dev",
            input={
                "prompt": prompt,
                "size": "2048x1024",
                "style": "realistic_image/hard_flash",
                # "num_outputs": 4,
                # "disable_safety_checker": True,
            },
        )
    )
    logger.info("replicate.make.image", result=result)

    if isinstance(result, list):
        return result
    else:
        return [result]


class ReplicateClientActor(ServerActor[str]):
    """Actor that manages image generation requests"""

    store: BlobStore

    def __init__(self, name: str, store: BlobStore):
        super().__init__(os.environ["REPLICATE_API_TOKEN"], name=name)
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
                    entity = new(
                        Schema.ImageObject,
                        {
                            PROV.wasGeneratedBy: this(),
                            PROV.generatedAtTime: Literal(
                                datetime.now(UTC)
                            ),
                        },
                    )
                    href = Literal(
                        vars.site.get()[f"files/{entity}"],
                        datatype=XSD.anyURI,
                    )
                    add(
                        entity,
                        {
                            NT.href: href,
                            Schema.contentUrl: Literal(
                                vars.site.get()[f"files/{entity}"],
                                datatype=XSD.anyURI,
                            ),
                        },
                    )
                    add(result.identifier, {PROV.generated: entity})
                    self.store.append_blob(str(entity), 0, img)

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
