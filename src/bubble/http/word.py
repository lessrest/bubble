from typing import Optional

import structlog

from swash import here
from swash.html import (
    HypermediaResponse,
    tag,
    text,
)
from swash.word import describe_word
from bubble.http.page import base_shell
from bubble.mesh.base import create_graph
from bubble.http.render import render_graph_view

logger = structlog.get_logger(__name__)


async def word_lookup_form(
    word: Optional[str] = None, error: Optional[str] = None
):
    """Render the word lookup form and results if any."""
    with base_shell("Word Lookup"):
        with tag("div", classes="p-4"):
            with tag("h1", classes="text-2xl font-bold mb-4"):
                text("WordNet Lookup")

            # Form
            with tag(
                "form",
                hx_get="/word",
                hx_target="this",
                hx_params="*",
                classes="mb-6",
            ):
                with tag("div", classes="flex gap-2"):
                    with tag(
                        "input",
                        type="text",
                        name="word",
                        value=word or "",
                        placeholder="Enter a word...",
                        classes=[
                            "flex-grow p-2 border rounded",
                            "dark:bg-gray-800 dark:text-white",
                            "dark:border-gray-700 focus:border-blue-500",
                            "focus:ring-blue-500 focus:outline-none",
                        ],
                    ):
                        pass

                    with tag(
                        "button",
                        type="submit",
                        classes=[
                            "px-4 py-2 bg-blue-500 text-white rounded",
                            "hover:bg-blue-600",
                            "dark:bg-blue-600 dark:hover:bg-blue-700",
                            "focus:outline-none focus:ring-2",
                            "focus:ring-blue-500 focus:ring-offset-2",
                        ],
                    ):
                        text("Look up")

    return HypermediaResponse()


async def word_lookup(word: str, pos: Optional[str] = None):
    """Handle word lookup form submission."""
    if not word.strip():
        return await word_lookup_form(error="Please enter a word")

    pos = pos if pos and pos.strip() else None

    with here.graph.bind(create_graph()):
        for word_node in describe_word(word, pos):
            pass

        render_graph_view(here.graph.get())
        logger.info("word lookup", graph=here.graph.get())

        return HypermediaResponse()
