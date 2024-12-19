import os
import logging
import pathlib

import typer

from typer import Option

from bubble.logs import configure_logging

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
)

home = pathlib.Path.home()

app_dir = pathlib.Path(typer.get_app_dir("bubble"))

# Use environment variables if set, otherwise use defaults
RepoPath = Option(
    os.environ.get("BUBBLE", str(app_dir / "repo")),
    "--repo",
    help="Repository path",
)

BaseUrl = Option(
    os.environ.get("BUBBLE_BASE", "https://localhost:2026/"),
    "--base-url",
    help="Public base URL",
)


def get_log_level() -> int:
    """Get logging level from environment variable."""
    debug = os.environ.get("BUBBLE_DEBUG", "").lower()
    if debug in ("1", "true", "yes"):
        return logging.DEBUG
    return logging.INFO


configure_logging(level=get_log_level())
