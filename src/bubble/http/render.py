from collections import defaultdict

import structlog

from rdflib import RDF, Graph, Dataset
from rdflib.graph import QuotedGraph

from swash import here
from swash.html import tag, text
from swash.rdfa import (
    rdf_resource,
    autoexpanding,
    get_subject_data,
    visited_resources,
)
from swash.util import S
from bubble.http.node import get_node_classes
from bubble.http.sort import get_traversal_order

logger = structlog.get_logger(__name__)


def render_node(graph: Graph, node: S) -> None:
    """Render a single node with appropriate styling."""
    visited = visited_resources.get()
    if node in visited:
        return

    with here.in_graph(graph):
        with tag("div", classes=get_node_classes(graph, node)):
            dataset = here.dataset.get()
            dataset.add_graph(graph)
            data = get_subject_data(dataset, node, context=graph)
            rdf_resource(node, data)


def render_graph_view(graph: Graph) -> None:
    """Render a complete view of a graph with smart traversal ordering."""
    nodes = get_traversal_order(graph)
    typed_nodes = []

    for node in nodes:
        if list(graph.objects(node, RDF.type)):
            typed_nodes.append(node)

    logger.info("rendering graph", graph=graph, typed_nodes=typed_nodes)

    with autoexpanding(3):
        with tag("div", classes="flex flex-col gap-4"):
            for node in typed_nodes:
                render_node(graph, node)


def render_graphs_overview(dataset: Dataset) -> None:
    """Render an overview of all graphs in the dataset."""
    with tag("div", classes="p-4 flex flex-col gap-6"):
        with tag(
            "h2",
            classes="text-2xl font-bold text-gray-800 dark:text-gray-200",
        ):
            text("Available Graphs")

        with tag("div", classes="grid gap-4"):
            # Get all non-formula graphs and sort by triple count (largest first)
            graphs = [
                g
                for g in dataset.graphs()
                if not isinstance(g, QuotedGraph)
            ]

            for graph in sorted(graphs, key=len, reverse=True):
                render_graph_summary(graph)


def render_graph_summary(graph: Graph) -> None:
    """Render a summary card for a single graph."""
    subject_count = len(set(graph.subjects()))
    triple_count = len(graph)

    with tag(
        "div",
        classes="border rounded-lg p-4 bg-white dark:bg-gray-800 shadow-sm hover:shadow-md transition-shadow",
    ):
        # Header with graph ID and stats
        with tag("div", classes="flex justify-between items-start mb-4"):
            # Graph ID as link
            with tag(
                "a",
                href=f"/graph?graph={str(graph.identifier)}",
                classes="text-lg font-medium text-blue-600 dark:text-blue-400 hover:underline",
            ):
                text(str(graph.identifier))

            # Stats
            with tag(
                "div", classes="text-sm text-gray-500 dark:text-gray-400"
            ):
                text(f"{subject_count} subjects, {triple_count} triples")

        # Preview of typed resources
        typed_subjects = {s for s in graph.subjects(RDF.type, None)}
        if typed_subjects:
            with tag("div", classes="mt-2"):
                with tag(
                    "h4",
                    classes="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2",
                ):
                    text("Resource Types")

                type_counts = defaultdict(int)
                for s in typed_subjects:
                    for t in graph.objects(s, RDF.type):
                        type_counts[t] += 1

                with tag("div", classes="flex flex-wrap gap-2"):
                    for rdf_type, count in sorted(
                        type_counts.items(),
                        key=lambda x: (-x[1], str(x[0])),
                    ):
                        with tag(
                            "span",
                            classes="px-2 py-1 text-xs rounded-full bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200",
                        ):
                            text(
                                f"{str(rdf_type).split('#')[-1].split('/')[-1]} ({count})"
                            )
