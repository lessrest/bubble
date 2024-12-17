from base64 import b64encode
from urllib.parse import quote
from swash.html import tag, text

import json
from contextlib import contextmanager

from swash.prfx import NT
from swash.rdfa import rdf_resource

from bubble.mesh import vat
from swash import vars
from rdflib import PROV

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
                with tag("div", classes="flex items-center"):
                    # find the editor actor which is started by the town's identity
                    editors = vars.dataset.get().objects(
                        vat.get().get_identity_uri(), PROV.started
                    )
                    for editor in editors:
                        affordances = vars.dataset.get().objects(
                            editor, NT.affordance
                        )
                        for affordance in affordances:
                            rdf_resource(affordance)

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
