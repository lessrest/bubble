import os
import tempfile

from typing import List, Tuple, cast

import httpx
import structlog

from rdflib import PROV, URIRef, Literal

from swash.prfx import NT
from swash.util import add, new, get_single_object
from bubble.http.tool import (
    AsyncReadable,
    BytesReadable,
    DispatchContext,
    DispatchingActor,
    handler,
    store_generated_assets,
)
from bubble.mesh.base import boss, this, with_transient_graph
from bubble.repo.repo import context, timestamp
from bubble.apis.recraft import RecraftAPI

logger = structlog.get_logger()


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
