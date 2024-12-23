import logging
import traceback

from typing import Any, Optional
from datetime import datetime, timedelta

import trio
import outcome
import rich.box
import hypercorn
import starlette
import structlog
import rich.pretty
import hypercorn.trio
import rich.traceback

from rdflib import Graph
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme
from rich.console import Console, RenderableType
from rich.padding import Padding
from rich.containers import Renderables

from swash.util import graph_string

# Custom theme for our logs
THEME = Theme(
    {
        "info": "#7777ff on #2222ff",
        "warning": "yellow",
        "error": "red",
        "critical": "red reverse",
        "debug": "cyan",
        "timestamp": "#330022",
        "actor": "green",
        "event": "#33bb33",
        "dim": "dim white",
        "file": "#90a4ae ",
        "module": "#80cbc4 on #004d40",  # Medium teal on dark teal
        "field_key": "#f06292",
    }
)


class RichConsoleRenderer:
    """A custom structlog renderer that uses Rich for pretty console output"""

    def __init__(
        self,
        console: Optional[Console] = None,
        colors: bool = True,
        level_styles: Optional[dict[str, str]] = None,
        show_timestamp: bool = True,
    ):
        """Initialize the renderer."""
        self._console = console or Console(
            color_system="256", theme=THEME, force_terminal=colors
        )
        self._level_styles = level_styles or {
            "critical": "critical",
            "error": "error",
            "warn": "warning",
            "warning": "warning",
            "info": "info",
            "debug": "debug",
        }
        self._show_timestamp = show_timestamp

    def _create_header(
        self,
        timestamp: str,
        level_name: str,
        module: Optional[str],
        file_location: str,
        event: str,
    ) -> Table:
        """Create the main log header line using a table for consistent alignment."""
        table = Table(
            show_header=False,
            show_lines=False,
            pad_edge=False,
            box=None,
            padding=(0, 0),
            expand=True,
        )

        # Add columns with appropriate styles and sizing
        if self._show_timestamp:
            table.add_column("Timestamp", style="timestamp", width=9)
        table.add_column(
            "Module", style="module", min_width=6, justify="center"
        )
        table.add_column(
            "Level", style="white", min_width=8, justify="center"
        )
        table.add_column("Event", style="white")
        table.add_column(
            "Location", style="file", min_width=12, justify="right", ratio=1
        )

        # Create the row data
        row_data = []
        if self._show_timestamp and timestamp:
            row_data.append(Text(timestamp, style="timestamp"))

        level_style = self._level_styles.get(level_name, "info")
        row_data.extend(
            [
                Text(module or "", style="module"),
                Text(level_name, style=level_style),
                Text(f' "{event}"', style="event"),
                Text(file_location, style="file"),
            ]
        )

        table.add_row(*row_data)
        return table

    def _handle_hypercorn_error(self, timestamp: str, event: str) -> None:
        """Handle special case of hypercorn.error logs."""
        if timestamp and self._show_timestamp:
            self._console.print(Text(f"{timestamp} {event}", style="dim"))
        else:
            self._console.print(Text(event, style="dim"))

    def _format_log_entry(
        self, name: str, event_dict: dict[str, Any]
    ) -> tuple[str, str, Optional[str], str, str, dict[str, Any]]:
        """Extract and format the main components of a log entry."""
        timestamp = event_dict.pop("timestamp", "")
        event = event_dict.pop("event", "")

        # Extract location information
        filename = event_dict.pop("filename", "")
        lineno = event_dict.pop("lineno", "")
        module = event_dict.pop("module", None)

        file_location = (
            f"{filename}:{lineno}" if filename and lineno else ""
        )

        return timestamp, name, module, file_location, event, event_dict

    def _create_fields_table(self, event_dict: dict[str, Any]) -> Table:
        """Create a table for the additional fields."""
        table = Table(
            show_header=False,
            show_edge=False,
            show_lines=False,
            border_style=None,
            box=None,
            padding=(0, 1),
            expand=True,
            highlight=True,
        )

        table.add_column(
            "Key", style="field_key", justify="right", min_width=8
        )
        table.add_column("Value", style="white", ratio=1)

        for key, value in sorted(event_dict.items()):
            if key == "level":
                continue
            if key == "actor":
                table.add_row(key, Text(str(value), style="actor"))
            elif key == "graph":
                if isinstance(value, Graph):
                    table.add_row(
                        key, Text(graph_string(value), style="graph")
                    )
                else:
                    table.add_row(key, Text(str(value), style="graph"))
            elif key == "error":
                if isinstance(value, BaseExceptionGroup):
                    # Handle exception groups by showing each exception
                    tracebacks = []
                    for exc in value.exceptions:
                        tracebacks.append(
                            rich.traceback.Traceback.from_exception(
                                exc_type=type(exc),
                                exc_value=exc,
                                traceback=exc.__traceback__,
                                show_locals=True,
                                max_frames=10,
                                suppress=[
                                    structlog,
                                    trio,
                                    hypercorn,
                                    hypercorn.trio,
                                    outcome,
                                    starlette,
                                ],
                                locals_max_length=3,
                                locals_max_string=50,
                            )
                        )
                    table.add_row(key, Renderables(tracebacks))
                else:
                    # Handle single exception as before
                    table.add_row(
                        key,
                        rich.traceback.Traceback.from_exception(
                            exc_type=type(value),
                            exc_value=value,
                            traceback=value.__traceback__,
                            show_locals=True,
                            max_frames=10,
                            suppress=[
                                structlog,
                                trio,
                                hypercorn,
                                hypercorn.trio,
                                outcome,
                                starlette,
                            ],
                            locals_max_length=3,
                            locals_max_string=50,
                        ),
                    )
            else:
                if isinstance(value, datetime):
                    value = value.isoformat()
                elif isinstance(value, timedelta):
                    value = f"{value.total_seconds()}s"
                table.add_row(key, rich.pretty.Pretty(value))

        return table

    def __call__(
        self, logger: Any, name: str, event_dict: dict[str, Any]
    ) -> str:
        """Render the log entry using Rich."""
        # Special handling for hypercorn.error logs
        if event_dict.get("name") == "hypercorn.error":
            self._handle_hypercorn_error(
                event_dict.get("timestamp", ""), event_dict.get("event", "")
            )
            self._console.print(event_dict)
            return ""

        try:
            # Format the log entry components
            (
                timestamp,
                name,
                module,
                file_location,
                event,
                remaining_dict,
            ) = self._format_log_entry(name, event_dict)

            # Create header
            header = self._create_header(
                timestamp, name, module, file_location, event
            )

            # Build the complete renderable
            elements: list[RenderableType] = [header]

            # Add fields table if we have additional fields
            if remaining_dict:
                fields_table = self._create_fields_table(remaining_dict)
                elements.append(Padding(fields_table, (0, 0, 0, 0)))

            # Render the final output
            self._render_output(name, elements)
            return ""
        except Exception as e:
            traceback.print_exception(e)
            self._console.print(f"Error rendering log entry: {e}")
            return ""

    def _render_output(
        self, name: str, elements: list[RenderableType]
    ) -> None:
        """Render the final formatted output."""
        content = Renderables(elements)

        if name in ("error", "critical", "warning"):
            panel = Panel(
                content,
                border_style=self._level_styles[name],
                padding=(0, 1),
                title=name.upper(),
                title_align="left",
            )
            self._console.print(panel, end="")
        elif name == "debug":
            # Make debug logs appear dim by using a Panel with dim style
            self._console.print(content, style="dim", end="")
        else:
            self._console.print(content, end="\n")


def configure_logging(
    colors: bool = True, level: int = logging.DEBUG
) -> structlog.stdlib.BoundLogger:
    """Configure structlog to use our Rich renderer.

    Args:
        colors: Whether to use colors in output
        level: Logging level (default: logging.DEBUG)
    """
    processors = [
        structlog.processors.add_log_level,
        structlog.processors.CallsiteParameterAdder(
            [
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.LINENO,
                structlog.processors.CallsiteParameter.MODULE,
            ]
        ),
        structlog.processors.TimeStamper(fmt="%H:%M:%S"),
        RichConsoleRenderer(colors=colors),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    if level == logging.DEBUG:
        logging.basicConfig(level=level)

    return structlog.get_logger()
