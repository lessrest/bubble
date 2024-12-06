from typing import Optional
from swash.html import attr, tag, html
from swash.html import classes as klasses


@html("audio-player", "w-5")
def render_audio_charm(
    src: Optional[str] = None,
    duration: Optional[float] = None,
):
    attr("src", src)
    attr("duration", str(duration))
    render_shadow_root()


@html.template(shadowrootmode="open")
def render_shadow_root():
    tag("link", rel="stylesheet", href="/static/audio-player.css")
    render_widget_template()


@html.div("container")
def render_widget_template():
    render_circular_progress()
    render_playback_icons()


@html.svg("circular-progress", "w-5", viewBox="0 0 100 100")
def render_circular_progress():
    tag("circle", classes="progress-bg", cx="50", cy="50", r="45")
    tag("circle", classes="progress-bar", cx="50", cy="50", r="45")


@html.div("play-pause")
def render_playback_icons():
    render_play_icon()
    render_pause_icon()
    render_record_icon()


@html.svg(viewBox="0 0 24 24", fill="#60a5fa")
def svg_icon(classes: str, path: str):
    klasses(classes)
    tag("path", d=path)


def render_pause_icon():
    svg_icon("pause-icon", "M6 6h12v12H6z")


def render_play_icon():
    svg_icon("play-icon", "M8 5v14l11-7z")


def render_record_icon():
    svg_icon(
        "record-icon",
        "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8z",
    )
