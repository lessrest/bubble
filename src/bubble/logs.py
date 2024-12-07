import logging
from typing import Any, Optional

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme
from rich.padding import Padding
from rich.columns import Columns
from rich.text import Text
from rich.containers import Renderables

import structlog

# Custom theme for our logs
THEME = Theme(
    {
        "info": "blue",
        "warning": "yellow",
        "error": "red",
        "critical": "red reverse",
        "debug": "cyan",
        "timestamp": "dim magenta",
        "actor": "green",
        "event": "white bold",
        "dim": "dim white",
        "file": "cyan",
        "module": "cyan",
        "field_key": "dim blue",
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
            theme=THEME, force_terminal=colors
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
        self, timestamp: str, name: str, file_location: Text, event: str
    ) -> Columns:
        """Create the main log header line with consistent spacing."""
        parts: list[RenderableType] = []

        # Timestamp and level in fixed-width format
        if self._show_timestamp and timestamp:
            parts.append(Text(timestamp, style="timestamp", justify="left"))

        level_style = self._level_styles.get(name, "info")
        parts.append(Text(name, style=level_style, justify="left"))

        # Add file location if present
        if file_location:
            parts.append(file_location)

        # Add event
        parts.append(Text(f": {event}", style="event", justify="left"))

        return Columns(parts, equal=False, expand=False, padding=(0, 1))

    def _create_fields_table(self, event_dict: dict[str, Any]) -> Table:
        """Create a table for the additional fields."""
        table = Table(
            show_header=False,
            show_lines=False,
            pad_edge=False,
            box=None,
            padding=(0, 2, 0, 2),
        )

        table.add_column(
            "Key", style="field_key", justify="right", min_width=12
        )
        table.add_column("Value", style="white", ratio=1)

        for key, value in sorted(event_dict.items()):
            if key == "level":
                continue
            if key == "actor":
                table.add_row(key, Text(str(value), style="actor"))
            else:
                table.add_row(key, str(value))

        return table

    def __call__(
        self, logger: Any, name: str, event_dict: dict[str, Any]
    ) -> str:
        """Render the log entry using Rich."""
        # Extract main components
        timestamp = event_dict.pop("timestamp", "")
        event = event_dict.pop("event", "")

        # Extract and format filename/lineno/module
        filename = event_dict.pop("filename", None)
        lineno = event_dict.pop("lineno", None)
        module = event_dict.pop("module", None)

        # Create file location text
        file_location = Text("")
        if filename and lineno:
            file_location.append(f"{filename}:{lineno}", style="file")
        if module:
            if file_location:
                file_location.append(" ")
            file_location.append(f"{module}", style="module")

        # Create header
        header = self._create_header(timestamp, name, file_location, event)

        # Build the complete renderable
        elements: list[RenderableType] = [header]

        # Add fields table if we have additional fields
        if event_dict:
            fields_table = self._create_fields_table(event_dict)
            elements.append(Padding(fields_table, (0, 0, 0, 4)))

        # Combine all elements
        content = Renderables(elements)

        # For errors and warnings, wrap in a panel with appropriate styling
        if name in ("error", "critical", "warning"):
            panel = Panel(
                content,
                border_style=self._level_styles[name],
                padding=(0, 1),
                title=name.upper(),
                title_align="left",
            )
            self._console.print(panel)
        else:
            self._console.print(content)

        return ""


def configure_logging(colors: bool = True) -> structlog.stdlib.BoundLogger:
    """Configure structlog to use our Rich renderer.

    Args:
        colors: Whether to use colors in output
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
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()
