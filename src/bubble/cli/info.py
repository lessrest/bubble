import os

from datetime import datetime

from rich import box
from rdflib import DCAT, PROV, URIRef, Literal
from rich.panel import Panel
from rich.table import Table
from rich.console import Console

from swash.html import document
from swash.lynx import render_html
from swash.rdfa import rdf_resource, autoexpanding
from bubble.repo.repo import from_env


async def bubble_info():
    console = Console(width=78)

    # Check if we're in a bubble environment
    if "BUBBLE" not in os.environ:
        console.print(
            Panel(
                "No bubble environment detected. Use [bold]bubble shell[/] to create one.",
                title="Bubble Status",
                border_style="yellow",
            )
        )
        return
    try:
        async with from_env() as repo:
            # Create environment info table
            env_table = Table(box=box.ROUNDED, title="Environment")
            env_table.add_column("Key", style="bold blue")
            env_table.add_column("Value")

            env_table.add_row("Bubble Path", os.environ["BUBBLE"])
            env_table.add_row("Current Graph", os.environ["BUBBLE_GRAPH"])
            env_table.add_row(
                "Graph Directory",
                os.environ.get("BUBBLE_GRAPH_DIR", "-"),
            )

            console.print(env_table)

            # Create graphs info table
            graphs_table = Table(box=box.ROUNDED, title="Graphs")
            graphs_table.add_column("Graph", style="bold")
            graphs_table.add_column("Type")
            graphs_table.add_column("Created")
            graphs_table.add_column("Files")

            for graph_id in repo.list_graphs():
                graph = repo.metadata

                # Get graph type
                graph_type = "Dataset"

                # Get creation time
                created = graph.value(graph_id, PROV.generatedAtTime)
                if created and isinstance(created, Literal):
                    try:
                        # Parse the datetime from the Literal value
                        dt = datetime.fromisoformat(str(created))
                        created_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError):
                        created_str = str(created)
                else:
                    created_str = "-"

                # Count distributions (files)
                file_count = len(
                    list(graph.objects(graph_id, DCAT.distribution))
                )

                graphs_table.add_row(
                    graph_id.n3(graph.namespace_manager),
                    graph_type,
                    created_str,
                    str(file_count),
                )

            console.print(graphs_table)

            # Show the current activity using the lynx renderer
            activity_uri = URIRef(os.environ["BUBBLE_ACTIVITY"])
            with document() as doc:
                with autoexpanding(3):
                    rdf_resource(activity_uri)
                    print(doc.to_html(compact=False))
                    render_html(doc.element, console)

    except ValueError as e:
        # Handle missing environment variables
        console.print(f"[red]Error:[/] {str(e)}")
        return
