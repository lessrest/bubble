import logging
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme

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
        "event": "white",
        "dim": "dim white",
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
        """Initialize the renderer.

        Args:
            console: Optional Rich console instance to use
            colors: Whether to use colors
            level_styles: Custom styles for different log levels
            show_timestamp: Whether to show timestamps
        """
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

    def __call__(
        self, logger: Any, name: str, event_dict: dict[str, Any]
    ) -> str:
        """Render the log entry using Rich.

        Args:
            logger: The logger instance
            name: The name of the log method (e.g. 'info', 'error')
            event_dict: The structured log entry

        Returns:
            The rendered string (though with Rich this is handled by the Console)
        """
        # Extract main components
        timestamp = event_dict.pop("timestamp", "")
        event = event_dict.pop("event", "")

        # Create the main line components
        components = []
        if self._show_timestamp and timestamp:
            components.append(f"[timestamp]{timestamp}[/timestamp]")

        # Add log level with appropriate style
        level_style = self._level_styles.get(name, "info")
        components.append(f" [{level_style}]{name}[/{level_style}]")

        # Add the event
        components.append(f": [event]{event}[/event]")

        # Create the main line
        main_line = "".join(components)

        # Format remaining fields
        field_lines = []
        for key, value in sorted(event_dict.items()):
            if key == "level":
                continue
            if key == "actor":
                field_lines.append(f"  {key:>12} = [actor]{value}[/actor]")
            else:
                # Indent other fields and style them
                field_lines.append(f"  {key:>12} = [white]{value}[/white]")

        # Combine all lines
        all_lines = (
            [main_line] + field_lines if field_lines else [main_line]
        )
        content = "\n".join(all_lines)

        # For errors and warnings, wrap in a panel
        if name in ("error", "critical", "warning"):
            panel = Panel(
                content,
                border_style=self._level_styles[name],
                padding=(0, 1),
            )
            self._console.print(panel)
        else:
            self._console.print(content)

        # Return empty string since we handled the printing
        return ""


def configure_logging(colors: bool = True) -> structlog.stdlib.BoundLogger:
    """Configure structlog to use our Rich renderer.

    Args:
        colors: Whether to use colors in output
    """
    processors = [
        structlog.processors.add_log_level,
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
