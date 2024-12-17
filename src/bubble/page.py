from base64 import b64encode
from html import escape
from typing import Optional
from urllib.parse import quote
from swash.html import tag, text

import json
from contextlib import contextmanager

from bubble.mesh import vat
from swash.html import html
from swash import vars
from rdflib import URIRef

cdn_scripts = [
    "https://unpkg.com/htmx.org@2",
]
htmx_config = {
    "globalViewTransitions": True,
}


def json_assignment_script(variable_name: str, value: dict):
    with tag("script"):
        text(
            f"Object.assign({variable_name}, {json.dumps(value, indent=2)});"
        )


@contextmanager
def base_html(title: str):
    with tag("html"):
        with tag("head"):
            with tag("title"):
                text(title)
            tag("link", rel="stylesheet", href="/static/css/output.css")
            tag("link", rel="stylesheet", href="/static/audio-player.css")
            for script in cdn_scripts:
                tag("script", src=script)
            tag("script", type="module", src="/static/type-writer.js")
            tag("script", type="module", src="/static/voice-writer.js")
            tag("script", type="module", src="/static/audio-recorder.js")
            tag("script", type="module", src="/static/live.js")
            json_assignment_script("htmx.config", htmx_config)

        with tag(
            "body",
            classes="bg-white dark:bg-slate-950 text-gray-900 dark:text-stone-50",
        ):
            yield
            tag("script", type="module", src="/static/audio-player.js")
            tag(
                "script",
                type="module",
                src="/static/voice-recorder-writer.js",
            )
            tag("script", type="module", src="/static/jsonld-socket.js")


def action_button(
    label: Optional[str] = None, icon: Optional[str] = None, **attrs
):
    """Create a styled action button with consistent Tailwind classes"""
    default_classes = [
        "relative inline-flex flex-row gap-2 justify-center items-center align-middle",
        "px-4 py-1",
        "bg-cyan-900 rounded-sm border border-cyan-600",
        "hover:bg-cyan-600 dark:hover:bg-cyan-700/80",
        "text-white font-bold",
        "dark:border-cyan-700/60 dark:bg-cyan-700/40",
        "transition-colors duration-150 ease-in-out",
    ]

    # Merge provided classes with default classes if any
    if "classes" in attrs:
        if isinstance(attrs["classes"], list):
            attrs["classes"].extend(default_classes)
        else:
            attrs["classes"] = [attrs["classes"]] + default_classes
    else:
        attrs["classes"] = default_classes

    with tag("button", **attrs):
        if icon:
            with tag("span"):
                text(icon)
        if label:
            with tag("span", classes="font-medium"):
                text(label)


def urlquote(id: str):
    """URL-encode a string."""
    return quote(id, safe="")


@contextmanager
def base_shell(title: str):
    """Base shell layout with status bar showing town info like public key."""
    with base_html(title):
        with tag("div", classes="min-h-screen flex flex-col"):
            # Status bar
            with tag(
                "div",
                classes=[
                    "bg-white dark:bg-cyan-900/30",
                    "text-gray-900 dark:text-white",
                    "px-4 py-2",
                    "flex items-center justify-between",
                    "border-b border-cyan-200 dark:border-cyan-800/40",
                ],
            ):
                id = vars.graph.get().identifier
                # Left section with Create button only
                with tag("div", classes="flex items-center"):
                    action_button(
                        "New sheet",
                        icon="📝",
                        hx_post="/create",
                        hx_target="#main",
                        hx_swap="innerHTML",
                        classes="mr-4",
                    )

                # Right section with Node ID and Site info
                with tag("div", classes="flex items-center gap-6"):
                    # Node ID
                    with tag("div", classes="flex flex-col"):
                        with tag(
                            "span",
                            classes="text-gray-500 dark:text-gray-400 text-sm",
                        ):
                            text("Node ID")
                        identity_uri = vat.get().get_identity_uri()
                        with tag(
                            "a",
                            href=str(identity_uri),
                            classes=[
                                "font-mono text-sm",
                                "text-emerald-600 dark:text-emerald-400",
                                "hover:text-emerald-500 dark:hover:text-emerald-300",
                                "transition-colors",
                            ],
                        ):
                            pubkey = vat.get().get_public_key_bytes()
                            text(b64encode(pubkey).decode()[0:8])

                    # Site URL
                    with tag("div", classes="flex flex-col"):
                        with tag(
                            "span",
                            classes="text-gray-500 dark:text-gray-400 text-sm",
                        ):
                            text("Site")
                        with tag(
                            "a",
                            href=vat.get().site,
                            classes=[
                                "font-mono text-sm",
                                "text-emerald-600 dark:text-emerald-400",
                                "hover:text-emerald-500 dark:hover:text-emerald-300",
                                "transition-colors",
                            ],
                        ):
                            text(vat.get().get_base_url())

            # Main content area
            with tag("main", id="main", classes="flex-1 p-4 flex"):
                yield


@html.div("flex flex-col gap-2 p-4")
def render_note_textarea(note_id: URIRef):
    """Render a textarea for editing notes with auto-save functionality."""
    with tag(
        "textarea",
        name="text",
        placeholder="Write your note here...",
        classes=[
            "w-full min-h-[200px] p-4",
            "bg-white/50 dark:bg-slate-800/30",
            "border border-gray-300/30 dark:border-slate-600/30",
            "text-gray-900 dark:text-gray-100",
            "placeholder-gray-500 dark:placeholder-gray-400",
            "focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400",
            "focus:border-blue-500 dark:focus:border-blue-400",
            "prose prose-sm dark:prose-invert",
            "font-serif",
        ],
        hx_post=f"{note_id}/message",
        hx_trigger="keyup changed delay:500ms",
        hx_swap="none",
    ):
        pass
