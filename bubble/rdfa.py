import json
import hashlib
import logging
import re
import urllib.parse

from typing import Dict, List, Tuple, Optional

import arrow

from fastapi import APIRouter, HTTPException
from rdflib import (
    RDF,
    XSD,
    RDFS,
    BNode,
    Graph,
    URIRef,
    Dataset,
    Literal,
)
import rich

from bubble.util import P, S
from bubble.repo import current_bubble

from bubble.prfx import NT
from bubble.html import (
    HypermediaResponse,
    html,
    tag,
    attr,
    text,
    classes,
)

router = APIRouter(
    prefix="/rdf", default_response_class=HypermediaResponse
)

logger = logging.getLogger(__name__)


def get_label(dataset: Dataset, uri: URIRef) -> Optional[S]:
    logger.info(f"Getting label for {uri} from {dataset}")
    for s, p, o, c in dataset.quads((None, RDFS.label, None, None)):
        logger.info(f"Label: {o} for {s} in context {c}")
    labels = list(dataset.objects(uri, RDFS.label))
    return labels[0] if labels else None


def get_subject_data(
    dataset: Dataset, subject: S, context: Optional[Graph] = None
) -> Dict[str, Optional[S]]:
    data = {"type": None, "predicates": []}
    graph = context or dataset
    logger.info(f"Getting subject data for {subject}")
    logger.info(f"Graph: {len(graph)} triples")
    for predicate, obj in graph.predicate_objects(subject):
        if predicate == RDF.type:
            data["type"] = obj
        else:
            data["predicates"].append((predicate, obj))
    data["predicates"].sort(
        key=lambda x: (isinstance(x[1], BNode), str(x[0]))
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
        current_bubble.get().dataset.triples(
            (predicate, NT.hasRisk, NT.DoxxingRisk)
        )
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
            grouped_triples[subject]["predicates"].append(
                (predicate, obj)
            )

    for data in grouped_triples.values():
        data["predicates"].sort(
            key=lambda x: (isinstance(x[1], BNode), str(x[0]))
        )

    return sorted(grouped_triples.items())


def render_subresource(
    subject: S, predicate: Optional[S] = None
) -> None:
    dataset = current_bubble.get().dataset
    if isinstance(subject, BNode):
        if RDF.List in dataset.objects(subject, RDF.type):
            render_list(dataset.collection(subject), predicate)
        else:
            render_expander(subject, predicate)
    else:
        render_value(subject, predicate)


@html.div(
    "bg-gray-800/30 dark:bg-gray-800/30 bg-gray-100/50 px-2 py-1",
    "border-l-4 border-gray-300 dark:border-gray-700",
    "hover:bg-gray-200/50 dark:hover:bg-gray-800/50",
    "hover:border-gray-400 dark:hover:border-gray-600",
)
@html.button("text-gray-900 dark:text-white")
def render_expander(obj, predicate):
    attr("hx-get", resource_path(obj))
    attr("hx-swap", "outerHTML")
    render_value(obj, predicate)


@router.get("/resource/{subject:path}")
def get_rdf_resource(subject: str) -> None:
    logger.info(f"Getting RDF resource for {subject}")
    subject = (
        BNode(subject.removeprefix("_:"))
        if subject.startswith("_")
        else URIRef(subject)
    )
    rdf_resource(subject)


@html.div(
    "border border-l-4",
    "bg-gray-100/50 dark:bg-gray-800/30",
    "border-slate-300 dark:border-slate-700",
    "hover:bg-gray-200/50 dark:hover:bg-gray-800/50",
    "hover:border-slate-400 dark:hover:border-slate-600",
    "px-2 py-1",
)
def rdf_resource(subject: S, data: Optional[Dict] = None) -> None:
    logger.info(f"Rendering RDF resource for {subject}")
    if data is None:
        data = get_subject_data(current_bubble.get().dataset, subject)
    logger.info(f"Data: {data}")

    if data["type"] == NT.Image:
        render_image_resource(subject, data)
    elif data["type"] == NT.VideoFile:
        render_video_resource(subject, data)
    elif data["type"] == NT.VoiceRecording:
        render_voice_recording_resource(subject, data)
    else:
        render_default_resource(subject, data)


@html.div("flex", "flex-col", "items-start", "gap-1")
def render_default_resource(subject: S, data: Optional[Dict] = None):
    render_resource_header(subject, data)
    render_properties(data)


@html.div("flex", "flex-col", "items-start", "gap-2")
def render_image_resource(subject: S, data: Dict) -> None:
    render_resource_header(subject, data)
    href = next(
        (obj for pred, obj in data["predicates"] if pred == NT.href),
        None,
    )
    if href:
        render_image(subject, href)
    render_properties(data)


@html.img("max-h-96 rounded-lg shadow-lg")
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
        (
            obj
            for pred, obj in data["predicates"]
            if pred == NT.audioUrl
        ),
        None,
    )
    duration = next(
        (
            obj
            for pred, obj in data["predicates"]
            if pred == NT.duration
        ),
        None,
    )
    render_audio_player_and_header(subject, data, audio_url, duration)
    render_properties(data)


@html.div("flex flex-row items-center gap-2")
def render_audio_player_and_header(subject, data, audio_url, duration):
    # if audio_url:
    #     render_audio_charm(audio_url, duration)
    render_resource_header(subject, data)


@html.dl("flex flex-row flex-wrap gap-x-6 gap-y-2")
def render_properties(data):
    if data["predicates"]:
        for predicate, obj in data["predicates"]:
            render_property(predicate, obj)
    else:
        classes("contents")


@html.div("flex flex-col")
def render_property(predicate, obj):
    render_property_label(predicate)
    render_subresource(obj, predicate)


@html.span("text-gray-600 dark:text-gray-400 opacity-80")
def render_property_label(predicate):
    dataset = current_bubble.get().dataset
    label = get_label(dataset, predicate)
    render_value(label or predicate)


@html.div("flex flex-row gap-2")
def render_resource_header(subject, data):
    render_value(subject)
    if data and data["type"]:
        dataset = current_bubble.get().dataset
        type_label = get_label(dataset, data["type"])
        render_value(type_label or data["type"])


@html.ul(
    "list-decimal flex flex-col gap-1 ml-4 text-cyan-600 dark:text-cyan-500"
)
def render_list(
    collection: List[S], predicate: Optional[S] = None
) -> None:
    for item in collection:
        with tag("li"):
            render_subresource(item, predicate)


def render_value(obj: S, predicate: Optional[P] = None) -> None:
    if has_doxxing_risk(predicate):
        classes("blur-sm hover:blur-none transition-all duration-300")

    if isinstance(obj, URIRef):
        _render_uri(obj)
    elif isinstance(obj, BNode):
        _render_bnode(obj)
    elif isinstance(obj, Literal):
        _render_literal(obj)
    else:
        raise ValueError(f"Unsupported node type: {obj}")


@html.a(
    "text-blue-600 dark:text-blue-400 whitespace-nowrap",
    hx_swap="outerHTML",
)
def _render_uri(obj: URIRef) -> None:
    attr("hx-get", resource_path(obj))

    prefix, namespace, name = (
        current_bubble.get().dataset.namespace_manager.compute_qname(str(obj))
    )
    text(name)
    render_curie_prefix(prefix)


@html.span(
    "text-blue-600 dark:text-blue-500",
    "opacity-70 pl-1 text-sm small-caps",
)
def render_curie_prefix(prefix):
    text(f"{prefix}")


@html.a(
    "text-cyan-700 dark:text-cyan-600 font-mono border-b",
    "border-cyan-300 dark:border-cyan-900",
    hx_swap="outerHTML",
)
def _render_bnode(obj: BNode) -> None:
    attr("href", resource_path(obj))
    attr("hx-get", resource_path(obj))
    text(f"⌗{obj}")


def _render_literal(obj: Literal) -> None:
    logger.info(f"Rendering literal: {obj}")
    rich.inspect(obj)
    datatype_handlers = {
        XSD.string: _render_string_literal,
        XSD.boolean: _render_boolean_literal,
        XSD.integer: _render_numeric_literal,
        XSD.decimal: _render_numeric_literal,
        XSD.double: _render_numeric_literal,
        XSD.date: _render_date_literal,
        XSD.dateTime: _render_date_literal,
        RDF.JSON: _render_json_literal,
    }

    if obj.datatype:
        handler = datatype_handlers.get(obj.datatype)
        if handler:
            handler(obj)
        elif obj.language:
            _render_language_literal(obj)
        else:
            _render_default_literal(obj)
    else:
        _render_string_literal(obj)


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
    dataset = current_bubble.get().dataset
    for s, p, o in dataset.triples((None, NT.payload, None)):
        literal = o
        dictionary = json.loads(literal)
        hash = hashlib.sha256(literal.encode()).hexdigest()
        logger.info(
            "Checking JSON literal",
        )
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
    "whitespace-nowrap",
    "before:content-['«'] after:content-['»']",
)
def render_other_string(obj):
    text(obj.value)


@html.a(
    "text-blue-600 dark:text-blue-400 font-mono max-w-60",
    "inline-block text-ellipsis overflow-hidden",
    "whitespace-nowrap",
    "before:content-['«'] after:content-['»']",
)
def render_linkish_string(obj):
    attr("href", obj.value)
    text(obj.value)


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
    else:
        text(obj.value)


@html.span("text-teal-600 dark:text-teal-400")
def _render_language_literal(obj: Literal) -> None:
    logger.info(f"Rendering language literal: {obj}")
    text(obj.value)


@html.span("text-orange-600 dark:text-orange-400")
def _render_default_literal(obj: Literal) -> None:
    logger.info(f"Rendering default literal: {obj}")
    text(f'"{obj.value}" ({obj.datatype})')


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


@html.dt(
    "text-gray-600 dark:text-gray-400 text-sm opacity-80 font-mono"
)
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
