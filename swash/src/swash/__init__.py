"""Node.Town RDF/N3 utilities."""

from .here import Parameter
from .html import (
    Fragment,
    LiveMessage,
    XMLResponse,
    HypermediaResponse,
    tag,
    attr,
    text,
    classes,
    dataset,
    document,
    appending,
    live_node,
)
from .util import (
    new,
    is_a,
    turtle,
    print_n3,
    select_rows,
    get_subjects,
    select_one_row,
    get_single_subject,
)

__version__ = "0.1.0"

__all__ = [
    # RDF/N3 utilities
    "print_n3",
    "get_single_subject",
    "get_subjects",
    "select_one_row",
    "select_rows",
    "turtle",
    "new",
    "is_a",
    # HTML utilities
    "document",
    "tag",
    "text",
    "attr",
    "classes",
    "dataset",
    "Fragment",
    "HypermediaResponse",
    "XMLResponse",
    "appending",
    "live_node",
    "LiveMessage",
    "Parameter",
]
