"""Git integration: Where time becomes a DAG and every commit tells a story.

As Linus Torvalds once quipped, "Talk is cheap. Show me the code."
But here we are, talking about code that talks to Git, which talks
about code. It's turtles all the way down.

Historical note: Git was born out of necessity and spite when BitKeeper
withdrew free use from the Linux kernel project. Never underestimate
the power of spite in software development.
"""

import os
import subprocess

from typing import Optional

import trio
import structlog

from trio import Path
from rich.text import Text
from rich.console import Console
from rich.padding import Padding

console = Console(force_interactive=True, force_terminal=True)
logger = structlog.get_logger()


def print_box(text: str, style: str = "dim") -> None:
    """Print text in a padded box with consistent formatting.

    Because even in the age of GUIs and web interfaces, there's something
    deeply satisfying about ASCII art boxes in a terminal.
    """
    console.print(
        Padding(
            Text(text, style=style),
            (0, 2),
        ),
        highlight=False,
    )


def print_git_output(
    stdout: Optional[bytes] = None, stderr: Optional[bytes] = None
) -> None:
    """Print git command output with consistent formatting.

    Git's output is like a haiku - sometimes beautiful,
    sometimes cryptic, always meaningful.
    """
    if stdout:
        print_box(stdout.decode())
    if stderr:
        print_box(stderr.decode())


class Git:
    """A thin wrapper around git commands, like a bespoke suit for a version control system.

    As they say, "Git is not a versioning system, it's a content-addressable
    filesystem with a VCS user interface written on top of it." But try
    putting that on a resume.
    """

    def __init__(self, workdir: Path):
        """Initialize a new Git wrapper.

        Args:
            workdir: The working directory. Like a home, but for code.
        """
        self.workdir = workdir

    async def init(self) -> None:
        """Initialize a new git repository, or do nothing if one exists.

        Every git init is like a big bang event - creating a new universe
        of possibilities, complete with its own space (working directory)
        and time (commit history).
        """
        if not await trio.Path(self.workdir).exists():
            logger.debug("Creating workdir", workdir=self.workdir)
            await trio.Path(self.workdir).mkdir()

        if not await trio.Path(self.workdir / ".git").exists():
            logger.info("Initializing git repository", workdir=self.workdir)
            await trio.run_process(
                ["git", "-C", self.workdir, "init"],
            )

    async def add(self, pattern: str) -> None:
        """Stage files matching pattern for commit.

        The staging area: Git's purgatory, where files wait for judgment
        before ascending to commit heaven or being reset back to working
        directory hell.
        """
        await trio.run_process(
            ["git", "-C", self.workdir, "add", pattern],
        )

    async def commit(self, message: str) -> None:
        """Create a new commit with the staged changes.

        Every commit is a promise to your future self and others:
        "This code worked when I committed it. Honestly."
        """
        git = await trio.run_process(
            ["git", "-C", self.workdir, "commit", "-m", message],
            capture_stdout=True,
        )
        print_git_output(git.stdout, git.stderr)

    async def exists(self, path: str) -> bool:
        """Check if a file exists in the repository.

        To exist or not to exist - that is the question Git answers
        with remarkable complexity for such a simple query.
        """
        try:
            await trio.run_process(
                [
                    "git",
                    "-C",
                    self.workdir,
                    "ls-files",
                    "--error-unmatch",
                    path,
                ],
                capture_stdout=True,
                capture_stderr=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    async def read_file(self, path: str) -> str:
        """Read a file from the repository or working directory.

        Like Schrödinger's cat, a file in Git exists in multiple states
        until you observe it. This method collapses the wavefunction and
        gives you the content.
        """
        file_path = os.path.join(self.workdir, path)
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return f.read()

        if not await self.exists(path):
            raise FileNotFoundError(f"{path} not found in repository")

        result = await trio.run_process(
            ["git", "-C", self.workdir, "show", f"HEAD:{path}"],
            capture_stdout=True,
        )
        return result.stdout.decode()

    async def write_file(self, path: str, content: str) -> None:
        """Write content to a file, ensuring atomic operations.

        We write to a temporary file first because, like a good story,
        a good file write should be atomic. No one wants to read half
        a file any more than they want to hear half a joke.
        """
        import hashlib

        # Create temp directory if it doesn't exist
        temp_dir = os.path.join(self.workdir, ".tmp")
        os.makedirs(temp_dir, exist_ok=True)

        # Create hash of path for temp file name
        path_hash = hashlib.sha256(path.encode()).hexdigest()[:16]
        temp_path = os.path.join(temp_dir, path_hash)

        try:
            # Write content to temp file
            with open(temp_path, "x") as f:
                f.write(content)

            # Ensure target directory exists
            target_path = os.path.join(self.workdir, path)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            # Move to final location - the moment of truth
            await trio.run_process(["mv", temp_path, target_path])
            logger.debug("File written successfully", path=path)
        finally:
            # Clean up temp file - leave no evidence
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
