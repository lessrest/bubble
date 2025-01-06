import re
import json
import hashlib
import contextlib
import urllib.parse

from typing import Dict, List, Tuple, Optional

import arrow
import structlog

from rdflib import (
    RDF,
    XSD,
    DCAT,
    RDFS,
    SKOS,
    BNode,
    Graph,
    URIRef,
    Dataset,
    Literal,
    Variable,
)
from fastapi import APIRouter, HTTPException
from rdflib.graph import QuotedGraph
from rdflib.collection import Collection

from swash import here
from swash.html import (
    HypermediaResponse,
    tag,
    attr,
    html,
    text,
    classes,
)
from swash.prfx import NT, Schema
from swash.util import P, S
from swash import feed


router = APIRouter(prefix="/rdf", default_response_class=HypermediaResponse)

logger = structlog.get_logger()

rendering_sensitive_data = here.Parameter(
    "rendering_sensitive_data", default=False
)

language_preferences = here.Parameter(
    "language_preferences", default=["en", "sv", "lv"]
)

expansion_depth = here.Parameter("expansion_depth", default=4)
visited_resources = here.Parameter("visited_resources", default=set())


@contextlib.contextmanager
def autoexpanding(depth: int):
    """Context manager for controlling resource expansion depth."""
    with expansion_depth.bind(depth):
        with visited_resources.bind(set()):
            yield


def get_label(dataset: Dataset, uri: URIRef) -> Optional[S]:
    # Get all labels with their languages
    labels = []

    # First try SKOS prefLabel
    for s, p, o, c in dataset.quads((uri, SKOS.prefLabel, None, None)):
        if isinstance(o, Literal):
            labels.append(
                (o, o.language or "", 1)
            )  # Priority 1 for prefLabel
        else:
            labels.append((o, "", 1))

    # Fall back to RDFS label if no prefLabel found
    if not labels:
        for s, p, o, c in dataset.quads((uri, RDFS.label, None, None)):
            if isinstance(o, Literal):
                labels.append(
                    (o, o.language or "", 2)
                )  # Priority 2 for label
            else:
                labels.append((o, "", 2))

    if not labels:
        return None

    # Sort labels by language preference
    prefs = language_preferences.get()

    def lang_key(label_tuple):
        label, lang, priority = label_tuple
        try:
            return (priority, prefs.index(lang))
        except ValueError:
            return (priority, len(prefs) if lang else len(prefs) + 1)

    sorted_labels = sorted(labels, key=lang_key)
    return sorted_labels[0][0] if sorted_labels else None


def get_subject_data(
    dataset: Optional[Dataset], subject: S, context: Optional[Graph] = None
) -> Dict[str, Optional[S]]:
    #    set_trace()

    data = {"type": None, "predicates": []}
    graph = context or dataset or here.graph.get()
    assert isinstance(graph, Graph)
    for predicate, obj in graph.predicate_objects(subject):
        if predicate == RDF.type:
            data["type"] = obj
        else:
            data["predicates"].append((predicate, obj))
    data["predicates"].sort(
        key=lambda x: (
            not isinstance(x[1], Literal),  # Literals first
            isinstance(x[1], BNode),  # Then URIRefs, then BNodes
            str(x[0]),  # Finally sort by predicate string
        )
    )
    return data


def resource_path(obj: S) -> str:
    obj_string = urllib.parse.quote(str(obj), safe="")
    if isinstance(obj, URIRef):
        return f"/rdf/resource/{obj_string}"
    elif isinstance(obj, BNode):
        return f"/rdf/resource/_:{obj_string}"
    else:
        raise ValueError(f"Unsupported node type: {obj}")


def has_doxxing_risk(predicate: Optional[P]) -> bool:
    if predicate is None:
        return False
    return any(
        here.dataset.get().triples((predicate, NT.hasRisk, NT.DoxxingRisk))
    )


def group_triples(
    dataset: Dataset, context: Optional[Graph] = None
) -> List[Tuple[S, Dict]]:
    grouped_triples: Dict[S, Dict] = {}
    for subject, predicate, obj in dataset.triples(
        (None, None, None), context=context
    ):
        if subject not in grouped_triples:
            grouped_triples[subject] = {
                "type": None,
                "predicates": [],
            }
        if predicate == RDF.type:
            grouped_triples[subject]["type"] = obj
        else:
            grouped_triples[subject]["predicates"].append((predicate, obj))

    for data in grouped_triples.values():
        data["predicates"].sort(
            key=lambda x: (isinstance(x[1], BNode), str(x[0]))
        )

    return sorted(grouped_triples.items())


@router.get("/resource/{subject:path}")
def get_rdf_resource(subject: str) -> None:
    subject = (
        BNode(subject.removeprefix("_:"))
        if subject.startswith("_")
        else URIRef(subject)
    )
    rdf_resource(subject)


frameless = here.Parameter("frameless", default=False)


@html.dd("flex flex-col")
def render_subresource(subject: S, predicate: Optional[P] = None) -> None:
    dataset = here.dataset.get()
    if isinstance(subject, BNode):
        if any(dataset.triples((subject, RDF.first, None))):
            render_list(dataset.collection(subject), predicate)
        else:
            render_expander(subject, predicate)
    elif isinstance(subject, URIRef):
        render_expander(subject, predicate)
    else:
        render_value(subject, predicate)


def render_expander(obj, predicate):
    current_depth = expansion_depth.get()
    visited = visited_resources.get()

    # If we have depth remaining and haven't seen this resource yet
    if current_depth > 0 and obj not in visited:
        with expansion_depth.bind(current_depth - 1):
            rdf_resource(obj)

        visited.add(obj)
    else:
        # Render as expandable button if we're at depth 0 or already visited
        with tag(
            "button", classes="text-gray-900 dark:text-white px-2 mt-1"
        ):
            classes("dark:bg-blue-700/20 dark:border-blue-700/20")
            attr("hx-get", resource_path(obj))
            attr("hx-swap", "outerHTML")
            render_value(obj, predicate)


def rdf_resource(subject: S, data: Optional[Dict] = None) -> None:
    if data is None:
        data = get_subject_data(here.dataset.get(), subject)

    # logger.info(
    #     "Rendering resource",
    #     subject=subject,
    #     data=data,
    #     graph=vars.dataset.get(),
    # )

    if (
        data["type"] == NT.Image
        or data["type"] == Schema.ImageObject
        or data["type"] == DCAT.Distribution
    ):
        render_image_resource(subject, data)
    elif data["type"] == NT.VideoFile:
        render_video_resource(subject, data)
    elif data["type"] == NT.VoiceRecording:
        render_voice_recording_resource(subject, data)
    elif data["type"] == NT.UploadEndpoint:
        render_upload_capability_resource(subject, data)
    elif data["type"] == NT.Button:
        render_button_resource(subject, data)
    elif data["type"] == NT.Prompt:
        render_prompt_resource(subject, data)
    elif data["type"] == NT.TextEditor:
        render_text_editor_resource(subject, data)
    elif data["type"] == NT.ImageUploadForm:
        render_image_uploader_resource(subject, data)
    elif data["type"] == NT.Timeline:
        feed.render_timeline_resource(subject, data)
    else:
        render_default_resource(subject, data)
    visited_resources.get().add(subject)


@html.div("flex flex-col items-start gap-1")
def render_upload_capability_resource(subject: S, data: Dict):
    attr("vocab", "http://www.w3.org/ns/rdfa#")
    attr("prefix", "rdf: http://www.w3.org/1999/02/22-rdf-syntax-ns#")
    render_resource_header(subject, data)
    url = next(
        (obj for pred, obj in data["predicates"] if pred == NT.url), None
    )
    with tag(
        "audio-recorder",
        classes=[
            "text-lg font-serif py-1",
        ],
        endpoint=url,
    ):
        pass
    render_properties(data)


@html.div("flex flex-col items-start gap-1")
def render_image_uploader_resource(subject: S, data: Dict):
    """Render an upload capability with file input."""
    attr("vocab", "http://www.w3.org/ns/rdfa#")
    attr("prefix", "rdf: http://www.w3.org/1999/02/22-rdf-syntax-ns#")

    # Get properties
    label = next(
        (obj for pred, obj in data["predicates"] if pred == NT.label),
        "Upload File",
    )
    target = next(
        (obj for pred, obj in data["predicates"] if pred == NT.target), None
    )
    message_type = next(
        (obj for pred, obj in data["predicates"] if pred == NT.message),
        None,
    )
    accept = next(
        (obj for pred, obj in data["predicates"] if pred == NT.accept),
        "*/*",
    )

    with tag.form(
        hx_post=f"{target}/message",
        hx_encoding="multipart/form-data",
        hx_swap="afterend",
    ):
        # Hidden field for message type
        with tag.input(type="hidden", name="type", value=str(message_type)):
            pass

        # File input group
        with tag.div(
            classes=[
                "flex flex-col gap-2 p-2 border rounded-sm",
                "bg-cyan-100/50 dark:bg-cyan-700/10",
                "border-cyan-300/50 dark:border-cyan-700/40",
            ]
        ):
            # File input
            with tag.input(
                type="file",
                name=str(NT.fileData),
                accept=str(accept),
                classes="text-sm text-gray-500 dark:text-gray-400",
            ):
                pass

            # Background removal option for images
            if "image/" in str(accept):
                with tag.div(classes="flex flex-col gap-2 text-sm"):
                    # Radio group for background options
                    with tag.div(classes="flex flex-col gap-1"):
                        text("Background options:")

                        with tag.label(classes="flex items-center gap-2"):
                            with tag.input(
                                type="radio",
                                name=str(NT.backgroundOption),
                                value="none",
                                checked="checked",
                                onchange="this.form.querySelector('.bg-prompt').classList.add('hidden')",
                            ):
                                pass
                            text("Keep original background")

                        with tag.label(classes="flex items-center gap-2"):
                            with tag.input(
                                type="radio",
                                name=str(NT.backgroundOption),
                                value="remove",
                                onchange="this.form.querySelector('.bg-prompt').classList.add('hidden')",
                            ):
                                pass
                            text("Remove background")

                        with tag.label(classes="flex items-center gap-2"):
                            with tag.input(
                                type="radio",
                                name=str(NT.backgroundOption),
                                value="modify",
                                onchange="this.form.querySelector('.bg-prompt').classList.remove('hidden')",
                            ):
                                pass
                            text("Modify background")

                    # Background prompt input (initially hidden)
                    with tag.div(classes="hidden bg-prompt"):
                        with tag(
                            "input",
                            type="text",
                            name=str(NT.backgroundPrompt),
                            placeholder="Describe the new background...",
                            classes="w-full p-1 text-sm border rounded-sm",
                        ):
                            pass

            # Submit button
            action_button(str(label), "📤")

    render_properties(data)


@html.div(
    # "border border-l-4",
    # "bg-gray-100/50 dark:bg-gray-800/30",
    # "border-slate-300 dark:border-slate-700",
    # "hover:bg-gray-200/50 dark:hover:bg-gray-800/50",
    # "hover:border-slate-400 dark:hover:border-slate-600",
    "mt-1",
)
@html.div("flex", "flex-col", "gap-1")
def render_default_resource(subject: S, data: Optional[Dict] = None):
    if isinstance(subject, BNode):
        attr("resource", "_:" + str(subject))
    else:
        attr("resource", str(subject))
    if data and data["type"]:
        attr("typeof", str(data["type"]))

    opened = (
        expansion_depth.get() > 0 and subject not in visited_resources.get()
    )

    with tag("details", open=opened):
        with tag("summary"):
            classes(
                "pl-2",
                "bg-blue-100/50 dark:bg-blue-700/20",
                "border border-gray-300 dark:border-blue-700/20",
                "w-fit",
                "text-slate-800 dark:text-slate-300",
            )
            render_resource_header(subject, data)
        render_properties(data)


@html.div("flex flex-col gap-2")
def render_affordance_resource(subject: S, data: Dict) -> None:
    """Render a resource focusing on its affordances."""
    render_resource_header(subject, data)

    # Get affordances from the graph
    dataset = here.dataset.get()
    affordances = list(dataset.objects(subject, NT.affordance))

    if affordances:
        with tag("div", classes="flex flex-col gap-2 pl-4"):
            for affordance in affordances:
                render_subresource(affordance)
    else:
        # If no affordances, fall back to default rendering
        render_properties(data)


@html.div("flex", "flex-row", "items-start", "gap-2")
def render_image_resource(subject: S, data: Dict) -> None:
    href = next(
        (
            obj
            for pred, obj in data["predicates"]
            if pred == NT.href or pred == DCAT.downloadURL
        ),
        None,
    )

    # Check for mediaType predicate
    media_type = next(
        (obj for pred, obj in data["predicates"] if pred == DCAT.mediaType),
        None,
    )

    if href:
        if media_type and media_type.startswith("video/"):
            render_video_element(href)
        else:
            render_image(subject, href)
    else:
        render_image(subject, subject)
    with tag("div", classes="flex flex-col items-start gap-2"):
        # render_resource_header(subject, data)
        render_properties(data)


@html.img("max-h-[600px]")
def render_image(subject, href):
    attr("src", href)
    attr("alt", f"Image {subject}")


@html.div("flex flex-col items-start gap-2")
def render_video_resource(subject: S, data: Dict) -> None:
    render_resource_header(subject, data)
    href = next(
        (obj for pred, obj in data["predicates"] if pred == NT.href),
        None,
    )
    if href:
        render_video_element(href)


@html.video("max-h-96 rounded-lg shadow-lg", controls=True)
def render_video_element(href):
    attr("src", href)


@html.div("flex flex-col items-start gap-2")
def render_voice_recording_resource(subject: S, data: Dict) -> None:
    audio_url = next(
        (obj for pred, obj in data["predicates"] if pred == NT.audioUrl),
        None,
    )
    duration = next(
        (obj for pred, obj in data["predicates"] if pred == NT.duration),
        None,
    )
    render_audio_player_and_header(subject, data, audio_url, duration)
    render_properties(data)


@html.div("flex flex-row items-center gap-2")
def render_audio_player_and_header(subject, data, audio_url, duration):
    # if audio_url:
    #     render_audio_charm(audio_url, duration)
    render_resource_header(subject, data)


@html.form()
def render_button_resource(subject, data):
    label = next(
        (obj for pred, obj in data["predicates"] if pred == NT.label), None
    )
    if label is None:
        label = "Button"

    target = next(
        (obj for pred, obj in data["predicates"] if pred == NT.target), None
    )
    icon = next(
        (obj for pred, obj in data["predicates"] if pred == NT.icon), None
    )

    message_uri = next(
        (obj for pred, obj in data["predicates"] if pred == NT.message),
        None,
    )

    if message_uri is None:
        raise ValueError("Button resource has no message")

    attr("hx-post", str(target) + "/message")
    attr("hx-swap", "afterend")

    # Regular button rendering
    with tag("input", type="hidden", name="type", value=str(message_uri)):
        pass

    action_button(label, icon)


@html.form(
    classes="flex flex-col gap-2 p-2 border border-gray-300 dark:border-slate-700/40"
)
def render_prompt_resource(subject, data):
    classes("bg-cyan-100/50 dark:bg-cyan-700/10")
    label = next(
        (obj for pred, obj in data["predicates"] if pred == NT.label), None
    )
    if label is None:
        label = "Prompt"

    target = next(
        (obj for pred, obj in data["predicates"] if pred == NT.target), None
    )

    message_uri = next(
        (obj for pred, obj in data["predicates"] if pred == NT.message),
        None,
    )

    if message_uri is None:
        raise ValueError("Prompt resource has no message")

    placeholder = next(
        (obj for pred, obj in data["predicates"] if pred == NT.placeholder),
        "Enter text...",
    )

    attr("hx-post", str(target) + "/message")
    attr("hx-swap", "afterend")

    with tag(
        "input",
        type="text",
        name="https://node.town/2024/prompt",
        classes="border rounded-sm px-2 py-0 dark:bg-cyan-800/40 dark:text-white dark:border-cyan-600/40",
    ):
        attr("placeholder", str(placeholder))
    with tag("input", type="hidden", name="type", value=str(message_uri)):
        pass
    with tag(
        "button",
        classes="bg-cyan-900 rounded-sm border border-cyan-600 hover:bg-cyan-600 text-white font-bold px-4 mt-1",
    ):
        classes(
            "inline-flex flex-row gap-2",
            "dark:border-cyan-700/40 dark:bg-cyan-700/40",
        )
        with tag("span", classes="htmx-indicator"):
            text("💭")
        text(label)


@html.div("flex flex-col gap-2")
def render_text_editor_resource(subject: S, data: Dict) -> None:
    """Render a text editor affordance."""

    # Get properties from data
    placeholder = next(
        (obj for pred, obj in data["predicates"] if pred == NT.placeholder),
        "Type something...",
    )
    target = next(
        (obj for pred, obj in data["predicates"] if pred == NT.target),
        subject,
    )
    message_uri = next(
        (obj for pred, obj in data["predicates"] if pred == NT.message),
        None,
    )

    existing_text = next(
        (obj for pred, obj in data["predicates"] if pred == NT.text),
        None,
    )

    assert isinstance(existing_text, Literal)

    if not message_uri:
        logger.warning("Text editor missing target or message URI")
        return

    with tag("form", hx_post=str(target) + "/message", hx_swap="none"):
        with tag(
            "input", type="hidden", name="type", value=str(message_uri)
        ):
            pass

        with tag(
            "textarea",
            name=str(NT.text),
            placeholder=str(placeholder),
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
        ):
            text(str(existing_text))

        action_button("Save", "✍️")

    render_properties(data)


# @html.dl("flex flex-row flex-wrap gap-x-6 gap-y-2 px-4 mb-1")
def render_properties(data):
    if not data["predicates"]:
        classes("contents")
        return

    # Group predicates by predicate URI
    grouped_predicates = {}
    for predicate, obj in data["predicates"]:
        if predicate not in grouped_predicates:
            grouped_predicates[predicate] = []
        grouped_predicates[predicate].append(obj)

    # Sort predicates by type of objects
    def sort_key(predicate_objects):
        predicate, objects = predicate_objects
        all_literals = all(isinstance(obj, Literal) for obj in objects)
        all_bnodes = all(isinstance(obj, BNode) for obj in objects)
        all_urirefs = all(isinstance(obj, URIRef) for obj in objects)

        return (
            # Single literal first
            not (all_literals and len(objects) == 1),
            # Multiple literals second
            not (all_literals and len(objects) > 1),
            # BNodes third
            not all_bnodes,
            # URIRefs last
            not all_urirefs,
            str(predicate),  # Break ties alphabetically
        )

    sorted_predicates = sorted(grouped_predicates.items(), key=sort_key)

    # Render each group
    with tag(
        "dl",
        classes="flex flex-row flex-wrap gap-x-6 gap-y-2 px-4 mb-1",
    ):
        if frameless.get() is False:
            classes(
                "border",
                "border-gray-300 dark:border-slate-700/20",
                "bg-blue-100/50 dark:bg-blue-700/10",
            )
        with frameless.bind(False):
            for predicate, objects in sorted_predicates:
                # Check if all objects are literals
                all_literals = all(
                    isinstance(obj, Literal) for obj in objects
                )

                if all_literals and len(objects) > 1:
                    # Render multiple literals together
                    render_property_with_multiple_literals(
                        predicate, objects
                    )
                else:
                    # Render each object separately
                    for obj in objects:
                        render_property(predicate, obj)


@html.div("flex flex-col")
def render_property_with_multiple_literals(predicate, literals):
    render_property_label(predicate)
    with tag("dd"):
        with tag("ul", classes="list-none"):
            # Sort literals by language preference
            prefs = language_preferences.get()
            sorted_literals = sorted(
                literals,
                key=lambda x: [
                    prefs.index(x.language) if x.language else 0,
                    x.language or "",
                    x.value,
                ],
            )
            for obj in sorted_literals:
                with tag("li", classes="ml-2"):
                    render_value(obj, predicate)


# @html.dd("flex flex-col")
@html.div("flex flex-col")
def render_property(predicate, obj):
    attr("property", str(predicate))
    if isinstance(obj, Literal):
        attr("content", str(obj))
        if obj.language:
            attr("lang", obj.language)
        if obj.datatype:
            attr("datatype", str(obj.datatype))
    elif isinstance(obj, URIRef):
        attr("resource", str(obj))
    elif isinstance(obj, BNode):
        attr("resource", "_:" + str(obj))
    render_property_label(predicate)
    render_subresource(obj, predicate)


inside_property_label = here.Parameter("inside_property_label", False)


@html.dt("flex flex-col")
def render_property_label(predicate):
    dataset = here.dataset.get()
    label = get_label(dataset, predicate)
    with inside_property_label.bind(True):
        render_value(label or predicate)


@html.div(
    "inline-flex flex-row gap-4 px-4 justify-between",
)
def render_resource_header(subject, data):
    render_value(subject)
    if data and data["type"]:
        with tag("span"):
            dataset = here.dataset.get()
            type_label = get_label(dataset, data["type"])
            with inside_property_label.bind(True):
                render_value(type_label or data["type"])
    # render a href link to the resource as a # icon

    with tag("a", href=here.site.get()[subject]):
        text("#")


@html.ul(
    "list-decimal flex flex-col gap-1 ml-4 text-cyan-600 dark:text-cyan-500"
)
def render_list(collection: List[S], predicate: Optional[P] = None) -> None:
    for item in collection:
        with tag("li"):
            render_subresource(item, predicate)


@contextlib.contextmanager
def sensitive_context():
    with rendering_sensitive_data.bind(True):
        yield


def render_value(obj: S, predicate: Optional[P] = None) -> None:
    if has_doxxing_risk(predicate):
        with sensitive_context():
            _render_value_inner(obj)
    else:
        _render_value_inner(obj)


def _render_value_inner(obj: S, label: bool = False) -> None:
    if isinstance(obj, URIRef):
        _render_uri(obj)
    elif isinstance(obj, BNode):
        _render_bnode(obj)
    elif isinstance(obj, Literal):
        _render_literal(obj)
    elif isinstance(obj, Variable):
        _render_variable(obj)
    elif isinstance(obj, QuotedGraph):
        _render_quoted_graph(obj)
    else:
        raise ValueError(f"Unsupported node type: {obj}")


@html.div(
    "flex flex-col gap-4 p-4 border border-gray-300 dark:border-gray-700 bg-gray-100/50 dark:bg-gray-800/30 rounded-lg"
)
def _render_quoted_graph(obj: QuotedGraph) -> None:
    # TODO: render the quoted graph
    pass


@html.a(
    "text-blue-600 dark:text-slate-400 whitespace-nowrap",
    hx_swap="outerHTML",
)
def _render_uri(obj: URIRef) -> None:
    attr("hx-get", resource_path(obj))
    attr("resource", str(obj))

    # Try to get a label first
    dataset = here.dataset.get()
    label = get_label(dataset, obj)

    if label:
        # If we have a label, show it
        with tag("span", classes="font-serif font-bold"):
            text(label)
        # # Add the CURIE in a smaller, dimmer font
        # prefix, namespace, name = (
        #     dataset.namespace_manager.compute_qname(str(obj))
        # )
        # with tag("span", classes="text-sm opacity-60 pl-1"):
        #     text(f"({prefix}:{name})")
    else:
        # If no label, show the CURIE as before
        if obj in dataset.namespace_manager:
            prefix, namespace, name = (
                dataset.namespace_manager.compute_qname(str(obj))
            )

            with tag(
                "span",
                classes="max-w-[18ch] truncate align-bottom inline-block text-ellipsis",
            ):
                text(name)
            render_curie_prefix(prefix)
        elif str(obj).startswith("did:key:"):
            key = str(obj).removeprefix("did:key:")
            prefix = key[:4]
            suffix = key[-4:]
            with tag("span", classes="font-mono"):
                text(f"🔑 {prefix}...{suffix}")
        else:
            with tag(
                "span",
                classes="font-mono max-w-[20ch] truncate block",
            ):
                text(f"<{str(obj)}>")


@html.span(
    # "text-blue-600 dark:text-blue-500",
    "opacity-70 pl-1 text-sm small-caps",
)
def render_curie_prefix(prefix):
    text(f"{prefix}")


@html.a(
    "text-cyan-700 dark:text-cyan-600 font-mono",
    hx_swap="outerHTML",
)
def _render_bnode(obj: BNode) -> None:
    attr("href", resource_path(obj))
    attr("hx-get", resource_path(obj))
    text("♢")


def _render_literal(obj: Literal) -> None:
    datatype_handlers = {
        XSD.string: _render_string_literal,
        XSD.boolean: _render_boolean_literal,
        XSD.integer: _render_numeric_literal,
        XSD.decimal: _render_numeric_literal,
        XSD.double: _render_numeric_literal,
        XSD.date: _render_date_literal,
        XSD.dateTime: _render_date_literal,
        RDF.JSON: _render_json_literal,
        NT.SecretToken: _render_secret_token_literal,
        XSD.anyURI: _render_any_uri_literal,
    }

    if obj.datatype:
        handler = datatype_handlers.get(obj.datatype)
        if handler:
            handler(obj)
        elif obj.language:
            _render_language_literal(obj)
        else:
            _render_default_literal(obj)
    elif isinstance(obj, Collection):
        _render_collection(obj)
    else:
        _render_string_literal(obj)


@html.span("text-gray-600 dark:text-gray-400 italic")
def _render_variable(obj: Variable) -> None:
    text(str(obj))


@html.a("text-blue-400 cursor-pointer", hx_swap="outerHTML")
def _render_json_literal(obj: Literal) -> None:
    try:
        json_hash = hashlib.sha256(str(obj).encode()).hexdigest()
        attr("hx-get", f"/rdf/json/{json_hash}")
        text("JSON")
    except json.JSONDecodeError:
        _render_default_literal(obj)


@router.get("/json/{json_hash}")
def get_json(json_hash: str):
    dataset = here.dataset.get()
    for s, p, o in dataset.triples((None, NT.payload, None)):
        literal = o
        dictionary = json.loads(literal)
        hash = hashlib.sha256(literal.encode()).hexdigest()
        if hash == json_hash:
            render_json(dictionary)
            return
    raise HTTPException(status_code=404, detail="JSON not found")


def _render_string_literal(obj: Literal) -> None:
    if obj.value.startswith("http"):
        render_linkish_string(obj)
    elif obj.language:
        _render_language_literal(obj)
    else:
        render_other_string(obj)


@html.span(
    "text-emerald-600 dark:text-emerald-500 font-mono",
    "inline-block text-ellipsis overflow-hidden",
    "max-w-64",
    "before:content-['«'] after:content-['»']",
)
def render_other_string(obj):
    if rendering_sensitive_data.get():
        classes("blur-sm hover:blur-none transition-all duration-300")
    if obj.language:
        attr("xml:lang", obj.language)
    if obj.datatype:
        attr("datatype", str(obj.datatype))
    text(obj.value)


@html.a(
    "text-blue-600 dark:text-blue-400 font-mono max-w-60",
    "inline-block text-ellipsis overflow-hidden",
    "whitespace-nowrap",
    "before:content-['«'] after:content-['»']",
)
def render_linkish_string(obj: Literal) -> None:
    attr("href", str(obj.toPython()))
    text(str(obj.toPython()))


@html.span("text-yellow-600 dark:text-yellow-400 font-bold")
def _render_boolean_literal(obj: Literal) -> None:
    text(str(obj.value).lower())


@html.span("font-mono")
def _render_numeric_literal(obj: Literal) -> None:
    classes(color_for_literal(obj))
    text(str(obj.value))


def color_for_literal(obj):
    match obj.datatype:
        case XSD.integer:
            return "text-purple-600 dark:text-purple-400"
        case XSD.double:
            return "text-blue-600 dark:text-blue-400"
        case _:
            return "text-indigo-600 dark:text-indigo-400"


@html.span("text-pink-600 dark:text-pink-400")
def _render_date_literal(obj: Literal) -> None:
    if obj.datatype == XSD.dateTime:
        t = arrow.get(obj.value)
        text(f"{t.humanize()}")
        attr("datetime", t.isoformat())
    elif obj.datatype == XSD.date:
        t = arrow.get(obj.value)
        text(f"{t.humanize()}")
        attr("datetime", t.isoformat())
    else:
        text(obj.value)


@html.span("text-teal-600 dark:text-teal-400 inline items-baseline")
def _render_language_literal(obj: Literal) -> None:
    assert obj.language
    if not inside_property_label.get():
        with tag(
            "span",
            classes="font-mono opacity-60 pr-1 text-xs language-tag",
        ):
            text(obj.language)
        with tag(
            "span",
            classes="font-serif text-stone-600 dark:text-stone-400",
        ):
            text(f"{obj.value}")
    else:
        text(obj.value)


@html.a(
    "text-blue-600 dark:text-blue-400 font-mono max-w-60",
    hx_swap="outerHTML",
)
def _render_any_uri_literal(obj: Literal) -> None:
    render_linkish_string(obj)


# rendering Collections (lists)
@html.ul(
    "list-decimal flex flex-col gap-1 ml-4 text-cyan-600 dark:text-cyan-500"
)
def _render_collection(obj: Collection) -> None:
    for item in obj:
        render_subresource(item)


@html.span("text-orange-600 dark:text-orange-400")
def _render_default_literal(obj: Literal) -> None:
    text(f'"{obj.value}" ({obj.datatype})')


@html.span(
    "text-red-600 dark:text-red-400",
)
def _render_secret_token_literal(obj: Literal) -> None:
    with tag("button"):
        classes(
            "text-red-600 dark:text-red-400 bg-red-100/70 dark:bg-red-900/70 border border-red-300 dark:border-red-700 px-1"
        )
        text(str(obj.value))


Atom = str | int | float | bool | None
Object = dict[str, "Value"]
Array = list["Value"]
Value = Atom | Object | Array


@html.dl(
    "flex flex-row flex-wrap gap-x-6 gap-y-2 px-2 py-1 ml-2",
    "border-l-2 border-pink-300/40 dark:border-pink-700/40",
    "bg-pink-100/20 dark:bg-pink-900/20",
)
def render_json(data: Value) -> None:
    match data:
        case dict() as o:
            render_json_dict(o)
        case list() as a:
            render_json_list(a)
        case _:
            render_json_value(data)


def render_json_dict(data: Object) -> None:
    def sort_key(item):
        key, value = item
        return (
            not bool(
                re.search(r"(^|_)id($|_)", key, re.IGNORECASE)
            ),  # 'id' keys first
            not (
                isinstance(value, str) and value.startswith("https://")
            ),  # 'https://' keys second
            isinstance(value, (dict, list)),
            isinstance(value, dict),
            value is None,
            isinstance(value, (int, float)),
            isinstance(value, str),
            key,
        )

    sorted_items = sorted(data.items(), key=sort_key)

    for key, value in sorted_items:
        render_json_dict_item(key, value)


@html.div("flex flex-col")
def render_json_dict_item(key: str, value: Value) -> None:
    render_dictionary_key(key)
    render_dictionary_value(value)


@html.dd()
def render_dictionary_value(value: Value) -> None:
    render_complex_value(value)


@html.dt("text-gray-600 dark:text-gray-400 text-sm opacity-80 font-mono")
def render_dictionary_key(key: str) -> None:
    text(key)


def render_json_list(data: Array) -> None:
    for index, item in enumerate(data):
        render_json_list_item(index, item)


@html.div("flex flex-row items-baseline gap-1")
def render_json_list_item(index: int, item: Value) -> None:
    render_json_list_index(index)
    render_json_list_value(item)


@html.dd()
def render_json_list_value(item: Value) -> None:
    render_complex_value(item)


@html.dt("text-gray-400 text-sm opacity-80 font-mono")
def render_json_list_index(index: int) -> None:
    text(f"⌗{index}")


def render_complex_value(value: Value) -> None:
    match value:
        case dict() | list() as v:
            if len(v) > 1:
                render_json_nested_value(v)
            else:
                render_json(value)
        case _:
            render_json_value(value)


@html.details()
def render_json_nested_value(value: Object | Array) -> None:
    render_summary(value)
    render_json(value)


@html.summary("cursor-pointer text-gray-600 dark:text-gray-500")
def render_summary(value: Object | Array) -> None:
    text(f"{len(value)} entries")


def render_json_value(value: Atom) -> None:
    match value:
        case str() as s:
            if s.startswith("https://"):
                render_json_link_string(s)
            elif " " not in s:
                render_json_symbol_string(s)
            else:
                render_json_prose_string(s)
        case int() | float() as n:
            render_json_number(n)
        case bool() as b:
            render_json_boolean(b)
        case None:
            render_json_null()


@html.span("text-amber-600 dark:text-amber-400")
def render_json_null() -> None:
    text("∅")


@html.span("text-yellow-600 dark:text-yellow-400 font-bold")
def render_json_boolean(value: bool) -> None:
    text(str(value).lower())


@html.span("text-indigo-600 dark:text-indigo-400 font-mono")
def render_json_number(value: int | float) -> None:
    text(str(value))


@html.span(
    "text-teal-600 dark:text-teal-500 before:content-['«'] after:content-['»']"
)
def render_json_prose_string(value: str) -> None:
    text(value)


@html.span("text-emerald-600 dark:text-emerald-500 font-mono")
def render_json_symbol_string(value: str) -> None:
    text(value)


@html.a(
    "text-blue-600 dark:text-blue-400 font-mono underline truncate max-w-64 inline-block",
    target="_blank",
    rel="noopener noreferrer",
)
def render_json_link_string(value: str) -> None:
    attr("href", value)
    text(value)


def action_button(
    label: Optional[str] = None, icon: Optional[str] = None, **attrs
):
    """Create a styled action button with consistent Tailwind classes"""
    default_classes = [
        # Layout & Sizing
        "relative",
        "flex flex-row gap-2",
        "justify-center items-center align-middle",
        "min-w-48",
        "px-4 py-1",
        # Light Mode
        "bg-stone-50",
        "text-stone-900",
        "border border-stone-400",
        "shadow-md shadow-stone-400/40",
        # Dark Mode
        "dark:bg-stone-700/40",
        "dark:text-stone-100",
        "dark:border-stone-600/40",
        "dark:shadow-stone-900/50",
        # Interactions & Animation
        "hover:bg-stone-100",
        "hover:translate-y-px",
        "hover:shadow-md",
        "active:bg-stone-200",
        "active:translate-y-0.5",
        "active:shadow-none",
        "transition-all duration-75",
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
            with tag(
                "span", classes="flex items-center justify-center w-4 h-4"
            ):
                text(icon)
        if label:
            with tag("span"):
                text(label)


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
