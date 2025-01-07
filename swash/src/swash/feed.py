import hashlib

from typing import Dict, Optional

import arrow

from rdflib import URIRef

from swash import here
from swash.html import tag, html, text
from swash.prfx import AS, NT
from swash.util import S, get_label


def get_avatar_emoji(actor: Optional[URIRef]) -> str:
    """Get a consistent avatar emoji for an actor based on their URI hash."""
    # List of distinct emoji avatars
    avatars = [
        "🌀",
        "🦊",
        "🐼",
        "🦉",
        "🦋",
        "🐙",
        "🦜",
        "🦝",
        "🐢",
        "🦡",
        "🦦",
        "🦥",
    ]

    if not actor:
        return "👤"  # Default for unknown actors

    # Get consistent index from hash
    hash_bytes = hashlib.sha256(str(actor).encode()).digest()
    index = int.from_bytes(hash_bytes[:4], byteorder="big") % len(avatars)
    return avatars[index]


@html.div("flow-root")
@html.ul("mb-4 mt-4", role="list")
def render_timeline_resource(subject: S, data: Dict):
    """Render a timeline of activity stream notes."""
    items = [obj for pred, obj in data["predicates"] if pred == NT.hasPart]
    for i, item in enumerate(items):
        render_timeline_item(item, is_last=(i == len(items) - 1))


@html.li()
def render_timeline_item(item: S, is_last: bool = False):
    """Render a single timeline item."""
    dataset = here.dataset.get()

    # Get actor info
    actor = next(
        (
            obj
            for pred, obj in dataset.predicate_objects(item)
            if pred == AS.actor and isinstance(obj, URIRef)
        ),
        None,
    )
    actor_name = str(get_label(dataset, actor) if actor else "Anonymous")

    with tag("div", classes=["relative", "" if is_last else "pb-8"]):
        # Vertical line connector (not on last item)
        if not is_last:
            with tag(
                "span",
                classes="absolute left-6 top-6 -ml-px h-full w-0.5 bg-gray-200 dark:bg-gray-700",
                aria_hidden="true",
            ):
                pass

        # Item content container
        with tag("div", classes="relative flex items-start space-x-4"):
            # Avatar section
            with tag("div", classes="relative"):
                with tag(
                    "div",
                    classes=[
                        "flex size-12 items-center justify-center",
                        "rounded-full",
                        "bg-slate-50 dark:bg-slate-800",
                        "ring-8 ring-white dark:ring-gray-900",
                        "text-2xl",
                    ],
                ):
                    text(get_avatar_emoji(actor))

            # Content section
            with tag("div", classes="min-w-0 flex-1"):
                # Header
                with tag("div"):
                    with tag("div", classes="text-sm"):
                        if actor:
                            with tag(
                                "a",
                                href=str(actor),
                                classes="font-medium text-gray-900 dark:text-gray-100",
                            ):
                                text(actor_name)
                        else:
                            with tag(
                                "span",
                                classes="font-medium text-gray-900 dark:text-gray-100",
                            ):
                                text(actor_name)

                    # Timestamp
                    published = next(
                        (
                            obj
                            for pred, obj in dataset.predicate_objects(item)
                            if pred == AS.published
                        ),
                        None,
                    )
                    if published:
                        with tag(
                            "p",
                            classes="mt-0.5 text-sm text-gray-500 dark:text-gray-400",
                        ):
                            text(
                                f"Posted {arrow.get(published).humanize()}"
                            )

                # Note content
                content = next(
                    (
                        obj
                        for pred, obj in dataset.predicate_objects(item)
                        if pred == AS.content
                    ),
                    None,
                )
                if content:
                    with tag(
                        "div",
                        classes="mt-2 text-sm text-gray-700 dark:text-gray-300",
                    ):
                        with tag("p"):
                            text(str(content))
