from swash.html import tag, text

import json
from contextlib import contextmanager

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


def action_button(label: str, **attrs):
    """Create a styled action button with consistent Tailwind classes"""
    default_classes = [
        "relative inline-flex flex-row gap-2 justify-center items-center align-middle",
        "px-2 py-1",
        "border border-gray-300 text-center",
        "shadow-md shadow-slate-300 dark:shadow-slate-800/50",
        "hover:border-gray-400 hover:bg-gray-50",
        "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:border-indigo-500",
        "active:bg-gray-100 active:border-gray-500",
        "transition-colors duration-150 ease-in-out",
        "dark:border-slate-900 dark:bg-slate-900/50",
        "dark:hover:bg-slate-900 dark:hover:border-slate-800",
        "dark:focus:ring-indigo-600 dark:focus:border-indigo-600",
        "dark:active:bg-slate-800 dark:text-slate-200",
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
        with tag("span", classes="font-medium"):
            text(label)
