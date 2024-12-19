"""Page generation: Where structure meets style in the digital realm.

In the beginning was the markup, and the markup was HTML. But raw HTML
was too verbose, too error-prone, too... 1995. So we build abstractions,
creating a dance of context managers and string builders that transform
our intentions into valid HTML.

Historical note: The first web browser was also an editor - Tim Berners-Lee's
WorldWideWeb (later renamed Nexus). We've been trying to recapture that
unified read-write vision of the web ever since.
"""

import json

from base64 import b64encode
from contextlib import contextmanager
from urllib.parse import quote

from rdflib import PROV

from swash import here
from swash.html import tag, text
from swash.prfx import NT
from swash.rdfa import rdf_resource
from bubble.mesh.base import vat
from bubble.repo.repo import context

# The scripts that power our interface - a carefully curated collection
# of modern web technologies that would make a 90s webmaster's head spin
cdn_scripts = [
    "https://unpkg.com/htmx.org@2",  # HTMX: Because sometimes JavaScript is too much
]

# Configuration for HTMX - teaching new tricks to old browsers
htmx_config = {
    "globalViewTransitions": True,  # Smooth transitions, like butter
}


def json_assignment_script(variable_name: str, value: dict):
    """Generate a script tag that assigns a JSON value to a variable.

    Because sometimes you need to pass data to JavaScript, and JSON is
    the least worst way to do it. Like passing notes in class, but with
    proper serialization.
    """
    with tag("script"):
        text(
            f"Object.assign({variable_name}, {json.dumps(value, indent=2)});"
        )


@contextmanager
def base_html(title: str):
    """Create the base HTML structure for our pages.

    Like a theater stage, we set up the basic structure where our
    content will perform. The head section is our backstage area,
    where we prepare all the scripts and styles that make the show
    possible.
    """
    with tag("html"):
        with tag("head"):
            with tag("title"):
                text(title)
            # Our costume department - where we dress up our content
            tag("link", rel="stylesheet", href="/static/css/output.css")
            tag("link", rel="stylesheet", href="/static/audio-player.css")
            # The stage machinery - scripts that make things move
            for script in cdn_scripts:
                tag("script", src=script)
            tag("script", type="module", src="/static/type-writer.js")
            tag("script", type="module", src="/static/voice-writer.js")
            tag("script", type="module", src="/static/audio-recorder.js")
            tag("script", type="module", src="/static/live.js")
            json_assignment_script("htmx.config", htmx_config)

        # The stage itself - where the content performs
        with tag(
            "body",
            classes="bg-white dark:bg-slate-950 text-gray-900 dark:text-stone-50",
        ):
            yield
            # The encore - scripts that run after the main content
            tag("script", type="module", src="/static/audio-player.js")
            tag(
                "script",
                type="module",
                src="/static/voice-recorder-writer.js",
            )
            tag("script", type="module", src="/static/jsonld-socket.js")


def urlquote(id: str):
    """URL-encode a string.

    Because spaces, slashes, and other special characters need to be
    properly dressed up before going out on the web. Like escaping
    characters in a string, but for URLs.
    """
    return quote(id, safe="")


@contextmanager
def base_shell(title: str):
    """Base shell layout with status bar showing town info like public key.

    This is our main stage layout - a responsive, modern interface that
    would make a Windows 95 user's jaw drop. The status bar is our
    digital equivalent of a theater's marquee, showing who we are and
    where we're located in the vast space of the web.
    """
    with base_html(title):
        with tag("div", classes="min-h-screen flex flex-col"):
            # Status bar - our digital marquee
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
                    # Find the editor actor - our stage director
                    editors = here.dataset.get().objects(
                        vat.get().get_identity_uri(), PROV.started
                    )
                    for editor in editors:
                        affordances = here.dataset.get().objects(
                            editor, NT.affordance
                        )
                        for affordance in affordances:
                            rdf_resource(affordance)

                # Right section - our digital business card
                with tag("div", classes="flex items-center gap-6"):
                    # Node ID - our unique identifier in the network
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
                            text(context.repo.get().get_repo_id())

                    # Site URL - our address in cyberspace
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

            # Main content area - where the magic happens
            with tag("main", id="main", classes="flex-1 p-4 flex"):
                yield
