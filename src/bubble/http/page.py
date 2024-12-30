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

from contextlib import contextmanager
from urllib.parse import quote


from swash.html import tag, text, html
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


status_bar_style = [
    "bg-white dark:bg-cyan-900/30",
    "text-gray-900 dark:text-white",
    "px-4 py-2",
    "flex items-center justify-between",
    "border-b border-cyan-200 dark:border-cyan-800/40",
]

link_styles = [
    "font-mono text-sm",
    "text-emerald-600 dark:text-emerald-400",
    "hover:text-emerald-500 dark:hover:text-emerald-300",
    "transition-colors",
]


@contextmanager
def base_shell(title: str):
    """Base shell layout with status bar showing town info like public key."""
    with base_html(title):
        with tag("div", classes="min-h-screen flex flex-col"):
            render_status_bar()
            with tag("main", id="main", classes="flex-1 p-4 flex"):
                yield


@html.div(classes=status_bar_style)
def render_status_bar():
    with tag.div(classes="flex items-center"):
        pass  # todo: add some content here

    with tag.div(classes="flex items-center gap-6"):
        render_node_id()
        render_site_name()


@html.span(classes="text-gray-500 dark:text-gray-400 text-sm")
def render_label(label):
    text(label)


@html.div(classes="flex flex-col")
def render_site_name():
    render_label("Site")
    with tag.a(href=vat.get().site, classes=link_styles):
        text(vat.get().get_base_url())


def render_node_id():
    identity_uri = vat.get().get_identity_uri()
    repo_id = context.repo.get().get_repo_id()
    with tag.div(classes="flex flex-col"):
        render_label("Node ID")
        with tag.a(href=str(identity_uri), classes=link_styles):
            text(repo_id)
