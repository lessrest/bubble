import os
import hashlib
import subprocess

from typing import (
    Any,
    BinaryIO,
    Callable,
    Iterator,
    Optional,
    Generator,
    cast,
)
from swash.prfx import NT
from trio import Path
from contextlib import contextmanager

import trio
import arrow
import structlog

from rich.padding import Padding
from rich.text import Text
import rich
from rdflib import (
    RDF,
    RDFS,
    XSD,
    VOID,
    Graph,
    URIRef,
    Dataset,
    Literal,
    Namespace,
)
from rdflib.namespace import PROV, DCAT, DCTERMS

from swash import vars
from swash.mint import fresh_uri
from swash.util import O, P, add, new
from rich.console import Console

FROTH = Namespace("https://node.town/ns/froth#")


logger = structlog.get_logger()
console = Console(force_interactive=True, force_terminal=True)


def print_box(text: str, style: str = "dim") -> None:
    """Print text in a padded box with consistent formatting.

    Args:
        text: The text to print
        style: Rich style to apply (default: "dim")
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
    """Print git command output with consistent formatting."""
    if stdout:
        print_box(stdout.decode())
    if stderr:
        print_box(stderr.decode())


class context:
    """Manages the current graph, activity and agent context."""

    graph = vars.Parameter["Graph"]("current_graph")
    activity = vars.Parameter["URIRef"]("current_activity")
    agent = vars.Parameter["URIRef"]("current_agent")
    clock = vars.Parameter[Callable[[], O]]("current_clock")

    @classmethod
    @contextmanager
    def bind_graph(
        cls, graph_id: URIRef, repo: "Repository"
    ) -> Generator[Graph, None, None]:
        """Bind both the context graph and the legacy vars graph parameter."""
        graph = repo.graph(graph_id)
        with cls.graph.bind(graph), vars.in_graph(graph):
            yield graph


context.clock.set(
    lambda: Literal(arrow.now().datetime, datatype=XSD.dateTime)
)


class Git:
    def __init__(self, workdir: Path):
        self.workdir = workdir

    async def init(self) -> None:
        if not await trio.Path(self.workdir).exists():
            logger.debug("Creating workdir", workdir=self.workdir)
            await trio.Path(self.workdir).mkdir()

        if not await trio.Path(self.workdir / ".git").exists():
            logger.info("Initializing git repository", workdir=self.workdir)
            await trio.run_process(
                ["git", "-C", self.workdir, "init"],
            )

    async def add(self, pattern: str) -> None:
        await trio.run_process(
            ["git", "-C", self.workdir, "add", pattern],
        )

    async def commit(self, message: str) -> None:
        git = await trio.run_process(
            ["git", "-C", self.workdir, "commit", "-m", message],
            capture_stdout=True,
        )
        print_git_output(git.stdout, git.stderr)

    async def exists(self, path: str) -> bool:
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
        import hashlib

        logger.debug("Writing file to git", path=path)

        # Create temp directory if it doesn't exist
        temp_dir = os.path.join(self.workdir, ".tmp")
        os.makedirs(temp_dir, exist_ok=True)

        # Create hash of path for temp file name
        path_hash = hashlib.sha256(path.encode()).hexdigest()[:16]
        temp_path = os.path.join(temp_dir, path_hash)

        try:
            # Write content to temp file
            with open(temp_path, "w") as f:
                f.write(content)

            # Ensure target directory exists
            target_path = os.path.join(self.workdir, path)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            # Copy to final location
            await trio.run_process(["cp", temp_path, target_path])
            logger.debug("File written successfully", path=path)
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass


class FileBlob:
    """A blob stored as a file in the git repository"""

    def __init__(self, path: Path):
        self.path = path
        self._file: Optional[BinaryIO] = None

    async def open(self, mode: str = "rb") -> BinaryIO:
        """Open and return the file handle"""
        await self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = cast(BinaryIO, open(self.path, mode))
        assert self._file is not None
        return self._file

    def close(self) -> None:
        """Close the file if open"""
        if self._file:
            self._file.close()
            self._file = None

    async def __aenter__(self) -> BinaryIO:
        return await self.open()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class Repository:
    async def __init__(
        self,
        git: Git,
        namespace: Namespace,
        dataset: Optional[Dataset] = None,
        metadata_id: URIRef = URIRef("urn:x-meta:"),
    ):
        self.git = git
        self.namespace = namespace
        self.dataset = dataset or Dataset(default_union=True)

        self.dataset.bind("home", namespace)
        self.metadata_id = metadata_id
        self.metadata = self.dataset.graph(metadata_id)

        self.metadata.bind("home", namespace)
        # Base path for graphs
        self.graphs_path = Path(self.git.workdir) / "graphs"

        # Load existing metadata if available
        try:
            content = await self.git.read_file("void.ttl")
            self.metadata.parse(data=content, format="turtle")
            self.metadata.bind("home", namespace)
        except FileNotFoundError:
            # Initialize new metadata graph
            with self.using_metadata():
                add(
                    self.metadata_id,
                    {
                        RDF.type: VOID.Dataset,
                        PROV.generatedAtTime: context.clock.get()(),
                    },
                )

        # Create meta.trig symlink in repository root
        await self.create_meta_symlink()

    @classmethod
    async def create(
        cls,
        git: Git,
        namespace: Namespace,
        dataset: Optional[Dataset] = None,
        metadata_id: URIRef = URIRef("urn:x-meta:"),
    ) -> "Repository":
        """Factory method to create a new Repository instance."""
        self = cls.__new__(cls)
        await self.__init__(git, namespace, dataset, metadata_id)  # type: ignore
        return self

    async def create_meta_symlink(self) -> None:
        """Create a symlink to void.ttl in the repository root."""
        repo_root = Path(self.git.workdir)
        meta_symlink = repo_root / "meta.trig"
        void_ttl = repo_root / "void.ttl"

        # Remove existing symlink if it exists
        try:
            await meta_symlink.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove existing meta.trig symlink")

        # Create relative symlink
        try:
            await meta_symlink.symlink_to(
                os.path.relpath(str(void_ttl), str(repo_root))
            )
        except OSError:
            logger.warning("Could not create meta.trig symlink")

    def graph_dir(self, identifier: URIRef) -> Path:
        """Get the directory path for a graph"""
        # Use hash of URI as directory name to avoid path length/char issues
        hashed = hashlib.sha256(str(identifier).encode()).hexdigest()[:16]
        return self.graphs_path / hashed

    def rdf_dir(self, identifier: URIRef) -> Path:
        """Get the .rdf directory path for a graph"""
        return self.graph_dir(identifier) / ".rdf"

    def graph_file(self, identifier: URIRef) -> Path:
        """Get the path to the graph.trig file for a graph"""
        return self.rdf_dir(identifier) / "graph.trig"

    def get_file(
        self,
        identifier: URIRef,
        filename: str,
        media_type: str = "application/octet-stream",
    ) -> FileBlob:
        """Get a file blob from a graph's directory and record metadata in the graph itself

        Args:
            identifier: The graph identifier
            filename: Name of the file
            media_type: MIME type of the file content (default: application/octet-stream)
        """
        file_path = self.graph_dir(identifier) / filename
        # Create a URI for the file
        file_uri = URIRef(f"file://{file_path.absolute()}")

        # Record file metadata in the graph itself
        with self.using_graph(identifier):
            # Link the file distribution to the graph
            add(
                identifier,
                {
                    DCAT.distribution: file_uri,
                },
            )
            # Describe the file distribution
            add(
                file_uri,
                {
                    RDF.type: DCAT.Distribution,
                    DCTERMS.identifier: Literal(filename),
                    DCTERMS.created: context.clock.get()(),
                    DCAT.downloadURL: file_uri,
                    DCAT.mediaType: Literal(media_type),
                },
            )

        return FileBlob(file_path)

    async def save_graph(self, identifier: URIRef) -> None:
        """Save a graph to its graph.trig file"""
        graph = self.graph(identifier)
        content = graph.serialize(format="trig")
        graph_file = self.graph_file(identifier)
        await graph_file.parent.mkdir(parents=True, exist_ok=True)
        await self.git.write_file(
            str(graph_file.relative_to(self.git.workdir)), content
        )

    async def load_graph(self, identifier: URIRef) -> None:
        """Load a graph from its graph.trig file"""
        graph_file = self.graph_file(identifier)
        try:
            content = await self.git.read_file(
                str(graph_file.relative_to(self.git.workdir))
            )
            logger.debug(
                "Loading graph", identifier=identifier, file=graph_file
            )
            self.graph(identifier).parse(data=content, format="trig")
        except FileNotFoundError:
            logger.debug(
                "New graph, no content to load", identifier=identifier
            )

    async def save_all(self) -> None:
        """Save all graphs and the graph catalog"""
        logger.debug("Saving all graphs")
        # Save metadata directly since we maintain it in memory
        content = self.metadata.serialize(format="turtle")
        await self.git.write_file("void.ttl", content)

        # Save all graphs with their full metadata
        graphs = self.list_graphs()
        logger.debug("Saving graphs", count=len(graphs))
        for identifier in graphs:
            await self.save_graph(identifier)

    async def load_all(self) -> None:
        """Load all graphs"""
        logger.debug("Loading all graphs")
        graphs = self.list_graphs()
        logger.debug("Loading graphs", count=len(graphs))
        for identifier in graphs:
            await self.load_graph(identifier)

    async def commit(self, message: str) -> None:
        """Commit all changes including graphs and their files, but only if there are changes."""
        if await self.has_changes():
            logger.info("Committing changes", message=message)
            await self.git.add(".")
            await self.git.commit(message)
        else:
            logger.debug("No changes to commit", message=message)

    def absolute_graph_path(self, identifier: URIRef) -> str:
        """Get the absolute path to a graph's directory"""
        return str(self.graph_dir(identifier))

    @contextmanager
    def using_metadata(self) -> Generator[Graph, None, None]:
        """Bind the metadata graph as the current graph."""
        with context.bind_graph(self.metadata_id, self):
            yield self.metadata

    @contextmanager
    def using_graph(
        self, identifier: URIRef
    ) -> Generator[Graph, None, None]:
        """Bind the specified graph as the current graph."""
        with context.bind_graph(identifier, self) as graph:
            yield graph

    def graph(self, identifier: URIRef) -> Graph:
        if (
            identifier not in self.list_graphs()
            and identifier is not self.metadata_id
        ):
            logger.debug("Registering new graph", identifier=identifier)
            # Add to metadata directly since we maintain it in memory
            self.metadata.add((identifier, RDF.type, VOID.Dataset))
            self.metadata.add(
                (identifier, PROV.generatedAtTime, context.clock.get()())
            )
            self.metadata.add(
                (
                    identifier,
                    VOID.dataDump,
                    Literal(
                        f"file://{self.absolute_graph_path(identifier)}"
                    ),
                )
            )

        return self.dataset.graph(identifier, base=self.namespace)

    def graphs(self) -> Iterator[Graph]:
        for identifier in self.list_graphs():
            yield self.graph(identifier)

    def list_graphs(self) -> list[URIRef]:
        return [
            URIRef(str(s))
            for s, p, o in self.metadata.triples(
                (None, RDF.type, VOID.Dataset)
            )
        ]

    def add(self, triple: tuple[URIRef, URIRef, URIRef | Literal]) -> None:
        """Add a triple to the current graph."""
        graph = context.graph.get()
        if not graph:
            raise ValueError("No current graph set")
        graph.add(triple)

    @contextmanager
    def new_graph(self) -> Generator[URIRef, None, None]:
        """Create a new graph with a fresh URI and set it as the current graph."""
        graph_id = fresh_uri(self.namespace)
        with self.using_graph(graph_id):
            yield graph_id

    @contextmanager
    def new_derived_graph(
        self,
        source_graph: Optional[URIRef] = None,
        activity: Optional[URIRef] = None,
    ) -> Generator[URIRef, None, None]:
        """Create a new graph derived from an existing graph, recording the provenance relation.

        Args:
            source_graph: The graph this is derived from. Defaults to current_graph.
            activity: Optional activity that caused this derivation. Defaults to current_activity.
        """
        graph_id = fresh_uri(self.namespace)
        source = (
            source_graph
            if source_graph is not None
            else context.graph.get()
        )
        if source is None:
            raise ValueError(
                "No source graph specified and no current graph set"
            )

        act = activity or context.activity.get()

        with self.using_metadata():
            add(
                graph_id,
                {
                    PROV.qualifiedDerivation: new(
                        FROTH.GraphDerivation,
                        {PROV.entity: source, PROV.hadActivity: act},
                    ),
                    PROV.generatedAtTime: context.clock.get()(),
                },
            )

        with context.bind_graph(graph_id, self):
            yield graph_id

    @contextmanager
    def new_activity(
        self, activity_type: URIRef
    ) -> Generator[URIRef, None, None]:
        """Create a new activity and set it as the current activity.

        Args:
            activity_type: The RDF type of the activity
        """
        activity_id = new(
            activity_type,
            {
                PROV.startedAtTime: context.clock.get()(),
                PROV.wasStartedBy: context.agent.get(),
            },
        )

        try:
            with context.activity.bind(activity_id):
                yield activity_id
        except Exception as error:
            logger.exception(
                "Activity failed", activity=activity_id, error=error
            )
            add(
                activity_id,
                {
                    PROV.qualifiedEnd: new(
                        NT.Error,
                        {
                            RDFS.label: Literal(str(error), lang="en"),
                        },
                    )
                },
            )
        finally:
            add(
                activity_id,
                {PROV.endedAtTime: context.clock.get()()},
            )

    @contextmanager
    def new_agent(
        self,
        agent_type: URIRef,
        props: Optional[dict[P, Any]] = None,
    ) -> Generator[URIRef, None, None]:
        """Create a new agent and set it as the current agent.

        Args:
            agent_type: The RDF type of the agent
            props: Optional properties to add to the agent
        """
        agent_id = new(agent_type, props or {})

        with context.agent.bind(agent_id):
            yield agent_id

    async def has_changes(self) -> bool:
        """Check if there are any uncommitted changes in the repository."""
        try:
            result = await trio.run_process(
                ["git", "-C", self.git.workdir, "status", "--porcelain"],
                capture_stdout=True,
            )
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False
