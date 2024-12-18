import os
import logging
import pathlib

import trio
import typer
import trio_asyncio

from typer import Option

from bubble.logs import configure_logging
from bubble.cli.info import bubble_info
from bubble.cli.join import bubble_join_simple
from bubble.cli.tool import run_generate_images
from bubble.cli.town import bubble_town
from bubble.cli.shell import bubble_shell

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


@app.command()
def shell(
    repo_path: str = RepoPath,
    namespace: str = Option(
        "https://example.com/", "--namespace", help="Namespace"
    ),
) -> None:
    """Create a new repository and start a shell session."""
    trio.run(bubble_shell, repo_path, namespace)


@app.command()
def town(
    bind: str = Option("127.0.0.1:2026", "--bind", help="Bind address"),
    base_url: str = Option(
        "https://localhost:2026/", "--base-url", help="Public base URL"
    ),
    repo_path: str = RepoPath,
    shell: bool = Option(False, "--shell", help="Start a bash subshell"),
) -> None:
    """Serve the Node.Town web interface."""
    trio_asyncio.run(bubble_town, bind, base_url, repo_path, shell)


@app.command()
def join_simple(
    town: str = Option(..., "--town", help="Town URL to join"),
    anonymous: bool = Option(
        False, "--anonymous", help="Join anonymously without an identity"
    ),
) -> None:
    """Join a remote town as a simple peer that prints incoming messages."""
    trio.run(bubble_join_simple, town, anonymous)


@app.command()
def info() -> None:
    """Display information about the current bubble environment and graphs."""
    trio_asyncio.run(bubble_info)


@app.command()
def tool(
    prompt: str,
    repo_path: str = RepoPath,
) -> None:
    """Run a tool, for now just generate images."""
    trio_asyncio.run(run_generate_images, prompt, repo_path)


if __name__ == "__main__":
    app()
