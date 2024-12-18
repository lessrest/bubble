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

RepoPath = Option(str(home / "repo"), "--repo", help="Repository path")


def get_log_level() -> int:
    """Get logging level from environment variable."""
    debug = os.environ.get("BUBBLE_DEBUG", "").lower()
    if debug in ("1", "true", "yes"):
        return logging.DEBUG
    return logging.INFO


configure_logging(level=get_log_level())
