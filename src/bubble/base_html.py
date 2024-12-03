from bubble.html import tag, text

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
