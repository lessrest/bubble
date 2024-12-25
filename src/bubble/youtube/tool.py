"""YouTube Downloader: A Tool for Video Downloads

This module implements a YouTube downloader actor that uses yt-dlp to
download videos from various platforms.
"""

import os
import tempfile

from typing import Dict, List, Tuple, Optional
from pathlib import Path
from datetime import UTC, datetime

import trio
import structlog

from rdflib import PROV, Graph, URIRef, Literal

from swash.prfx import NT
from swash.util import add, new, is_a, get_single_object
from bubble.http.tool import (
    AsyncReadable,
    DispatchContext,
    DispatchingActor,
    handler,
    create_prompt,
    store_generated_assets,
)
from bubble.mesh.base import boss, this, txgraph, with_transient_graph
from bubble.repo.repo import context

logger = structlog.get_logger()


class AsyncReadableFile:
    def __init__(self, file_path: str):
        self.file_path = file_path

    async def aread(self) -> bytes:
        with open(self.file_path, "rb") as f:
            return f.read()


def get_mime_type(path: Path) -> str:
    """Get MIME type based on file extension."""
    suffix = path.suffix.lower()
    return {
        ".mp4": "video/mp4",
        ".json": "application/json",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")


async def download_video(
    url: str, output_dir: Path
) -> Dict[str, List[Path]]:
    """Run yt-dlp as a subprocess in the given directory."""
    cmd = [
        "yt-dlp",
        "-f",
        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--no-playlist",
        "--write-info-json",  # Write video metadata to JSON
        "--write-thumbnail",  # Download thumbnail
        "--print",
        "after_move:filepath",  # Print final filepath after download
        url,
    ]

    # Get initial directory contents
    before = set(output_dir.iterdir())

    # Run yt-dlp
    process = await trio.run_process(
        cmd,
        cwd=str(output_dir),
        capture_stdout=True,
        capture_stderr=True,
    )

    if process.returncode != 0:
        logger.error(
            "yt-dlp failed",
            stdout=process.stdout.decode(),
            stderr=process.stderr.decode(),
        )
        raise RuntimeError("Failed to download video")

    # Get final directory contents and find new files
    after = set(output_dir.iterdir())
    new_files = after - before

    # Categorize files by type
    files_by_type = {
        "video": [],
        "json": [],
        "thumbnail": [],
        "other": [],
    }

    for f in new_files:
        if f.suffix == ".mp4":
            files_by_type["video"].append(f)
        elif f.suffix == ".json":
            files_by_type["json"].append(f)
        elif f.suffix in {".jpg", ".png", ".webp"}:
            files_by_type["thumbnail"].append(f)
        else:
            files_by_type["other"].append(f)

    logger.info(
        "yt-dlp downloaded files",
        files_by_type={
            k: [f.name for f in v] for k, v in files_by_type.items()
        },
        stdout=process.stdout.decode(),
    )

    return files_by_type


class YouTubeDownloader(DispatchingActor):
    """Actor for downloading videos from YouTube and other platforms."""

    async def setup(self, actor_uri: URIRef):
        """Initialize by creating a URL input prompt."""
        new(
            NT.YouTubeDownloader,
            {
                NT.affordance: create_prompt(
                    "Video URL",
                    "Enter a video URL to download...",
                    NT.DownloadVideo,
                    actor_uri,
                )
            },
            actor_uri,
        )

    @handler(NT.DownloadVideo)
    async def handle_download_video(self, ctx: DispatchContext):
        """Handle video download request."""
        url = get_single_object(ctx.request_id, NT.prompt, ctx.buffer)

        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                # Run yt-dlp as a subprocess
                files_by_type = await download_video(
                    str(url), Path(tmp_dir)
                )

                # Collect all assets with their MIME types
                assets: List[Tuple[AsyncReadable, str]] = []

                # Add videos first (they're the main content)
                for f in files_by_type["video"]:
                    assets.append(
                        (AsyncReadableFile(str(f)), get_mime_type(f))
                    )

                # Add metadata JSON
                for f in files_by_type["json"]:
                    assets.append(
                        (AsyncReadableFile(str(f)), get_mime_type(f))
                    )

                # Add thumbnails
                for f in files_by_type["thumbnail"]:
                    assets.append(
                        (AsyncReadableFile(str(f)), get_mime_type(f))
                    )

                # Add any other files
                for f in files_by_type["other"]:
                    assets.append(
                        (AsyncReadableFile(str(f)), get_mime_type(f))
                    )

                # Store all assets in a single collection
                collection = await store_generated_assets(boss(), assets)

                with with_transient_graph() as graph:
                    # Add the collection as the main generated thing
                    add(graph, {PROV.generated: collection})

                    return context.buffer.get()

            finally:
                # TemporaryDirectory will clean up automatically
                pass
