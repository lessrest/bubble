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

from random import choice
from contextlib import contextmanager
from urllib.parse import quote

from rdflib import URIRef

from swash.html import tag, html, text
from bubble.mesh.base import vat as current_vat
from bubble.repo.repo import context

htmx_config = {
    "globalViewTransitions": True,
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
    with tag.html(lang="en"):
        with tag.head():
            with tag.title():
                text(title)

            tag.link(rel="stylesheet", href="/static/css/output.css")
            tag.link(rel="stylesheet", href="/static/audio-player.css")

            tag.script(type="module", src="/static/type-writer.js")
            tag.script(type="module", src="/static/voice-writer.js")
            tag.script(type="module", src="/static/audio-recorder.js")
            tag.script(type="module", src="/static/live.js")

        with tag.body(
            classes="bg-white dark:bg-slate-950 text-gray-900 dark:text-stone-50",
        ):
            yield

            tag.script(type="module", src="/static/audio-player.js")
            tag.script(
                type="module",
                src="/static/voice-recorder-writer.js",
            )
            tag.script(type="module", src="/static/jsonld-socket.js")

            tag.script(src="/static/htmx-2.0.4.js")
            tag.script(src="/static/hyperscript-0.9.13.js")

            json_assignment_script("htmx.config", htmx_config)


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
    with base_html(title):
        with tag.div(classes="min-h-screen flex flex-col"):
            render_status_bar()
            with tag.main(id="main", classes="flex-1 p-4 flex"):
                yield


@html.div(classes="flex flex-col")
def render_entry(label: str, value: str, href: str | URIRef):
    with tag.span(classes="text-gray-500 dark:text-gray-400 text-sm"):
        text(label)
    with tag.a(href=str(href), classes=link_styles):
        text(value)


@html.div(classes=status_bar_style)
def render_status_bar():
    advice_texts = [
        "Do not take notes on criminal conspiracies.",
        "Every system is broken but you can still try.",
        "Your file naming conventions are very interesting.",
        "Write it down—if it's bad, delete it later.",
        "The cloud is just someone else's computer.",
        "You have permission to start poorly. ❤️",
        "All good ideas look bad in the beginning. 😭",
        "This app has no opinions about your life choices.",
        "Make a backup right now. Trust me.",
        "Complexity is very, very seductive. Are you up for it, playboy?",
        "You are not legally obligated to finish everything you start.",
        "This app will remember for you. Do not stress today.",
        "Most thoughts do not deserve a post-it note.",
        "The best version of your idea is the one that exists right now.",
        "No one is grading your to-do list.",
        "Just because it's a draft doesn't mean it's bad in ANY way.",
        "Not every project needs a name. Call this one Freckles.",
        "Begin. The rest is easier.",
        "If you use this app to explain your feelings, use also a napkin.",
        "Your 17th idea today will likely be the good one!.",
        "Being busy is a thing. That happens. I think.",
        "This app is your therapist. Just kidding. Double jinx.",
        "Genius is forgetting bad ideas quickly.",
        "Despite the widespread enthusiasm, we have not yet implemented writer's block.",
        "Congratulations. You're overthinking it.",
        "Perfectionism is not always just a fancy word for procrastination.",
        "Spend more time naming than working.",
        "Write as though you realize that you will not even remember this tomorrow.",
        "Progress doesn't happen according to a plan. Unless you have a pretty good plan.",
        "Your creative process is what I call my existential crisis.",
        "This app contains a roadmap for your life.",
        "There are no rules. Especially syntax ones.",
    ]

    with tag.div(classes="flex items-center"):
        with tag.span(
            classes="text-sm text-gray-500 dark:text-gray-400 pl-4"
        ):
            text(choice(advice_texts))

    with tag.div(classes="flex items-center gap-6"):
        vat = current_vat.get()
        repo = context.repo.get()
        render_entry("Node ID", repo.repo_id, vat.identity_uri)
        render_entry("Site", vat.base_url, vat.site)
