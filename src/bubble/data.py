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
from contextlib import contextmanager, asynccontextmanager
from collections.abc import AsyncIterator

import trio
import arrow
import structlog
import rdflib.store

from trio import Path
from rdflib import (
    RDF,
    XSD,
    RDFS,
    VOID,
    Graph,
    URIRef,
    Dataset,
    Literal,
    Namespace,
    IdentifiedNode,
)
from rich.text import Text
from rich.console import Console
from rich.padding import Padding
from rdflib.namespace import DCAT, PROV, DCTERMS

import swash

from swash import here
from swash.mint import fresh_uri
from swash.prfx import NT
from swash.util import O, P, S, add, new, get_single_object

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

    graph = here.graph
    activity = here.Parameter["URIRef"]("current_activity")
    agent = here.Parameter["URIRef"]("current_agent")
    clock = here.Parameter[Callable[[], O]]("current_clock")
    repo = here.Parameter["Repository"]("current_repo")

    @classmethod
    @contextmanager
    def bind_graph(
        cls, graph_id: URIRef, repo: Optional["Repository"] = None
    ) -> Generator[Graph, None, None]:
        """Bind both the context graph and the legacy vars graph parameter."""
        repo = repo or context.repo.get()
        graph = repo.graph(graph_id)
        with cls.graph.bind(graph), here.in_graph(graph):
            yield graph


context.clock.set(
    lambda: Literal(arrow.now().datetime, datatype=XSD.dateTime)
)


def timestamp() -> O:
    return context.clock.get()()


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

            # Move to final location
            await trio.run_process(["mv", temp_path, target_path])
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

    async def write(self, data: bytes) -> None:
        """Write data to the file"""
        io = await self.open("wb")
        io.write(data)
        io.close()

    async def read(self) -> bytes:
        """Read data from the file"""
        io = await self.open("rb")
        return io.read()

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
    dirty_graphs: set[Graph] = set()

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

        # Register builtin graphs
        vocab_ext = URIRef("urn:x-bubble:vocab:ext")
        self.register_builtin_graph(vocab_ext, "vocab/ext.ttl")
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

        self.dataset.store.dispatcher.subscribe(
            rdflib.store.TripleAddedEvent, self.on_triple_added
        )
        self.dataset.store.dispatcher.subscribe(
            rdflib.store.TripleRemovedEvent, self.on_triple_removed
        )

    def on_triple_added(self, event: rdflib.store.TripleAddedEvent) -> None:
        graph = event.context  # type: ignore
        assert isinstance(graph, Graph)
        self.dirty_graphs.add(graph)

    def on_triple_removed(
        self, event: rdflib.store.TripleRemovedEvent
    ) -> None:
        graph = event.context  # type: ignore
        assert isinstance(graph, Graph)
        self.dirty_graphs.add(graph)

    @classmethod
    async def create(
        cls,
        git: Git,
        namespace: Namespace,
        dataset: Optional[Dataset] = None,
        metadata_id: URIRef = URIRef("urn:x-bubble:meta"),
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

    def open_existing_file(self, file_uri: URIRef) -> FileBlob:
        path = get_single_object(file_uri, NT.hasFilePath)
        return FileBlob(Path(path))

    async def get_file(
        self,
        identifier: IdentifiedNode,
        filename: str,
        media_type: str = "application/octet-stream",
    ) -> FileBlob:
        """Get a file blob from a graph's directory and record metadata in the graph itself

        Args:
            identifier: The graph identifier
            filename: Name of the file
            media_type: MIME type of the file content (default: application/octet-stream)
        """
        assert isinstance(identifier, URIRef)
        file_path = self.graph_dir(identifier) / filename
        # Create a URI for the file
        file_uri = URIRef(f"file://{await file_path.absolute()}")

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
                    NT.hasFilePath: Literal(str(file_path)),
                },
            )

        return FileBlob(file_path)

    # I want a method that takes a bytes object and media type,
    async def save_blob(
        self, data: bytes, media_type: str = "application/octet-stream"
    ) -> URIRef:
        """Save a blob with content addressing and return its URIRef.

        Args:
            data: The binary data to save
            media_type: MIME type of the content (default: application/octet-stream)

        Returns:
            URIRef: A content-addressed URI like urn:x-bubble:file:sha256:...
        """
        # Generate SHA-256 hash of content
        sha256 = hashlib.sha256(data).hexdigest()

        # Create content-addressed URI
        file_uri = URIRef(f"urn:x-bubble:file:sha256:{sha256}")

        # Save to content-addressed location
        file_path = self.graphs_path / "blobs" / sha256[:2] / sha256[2:]
        blob = FileBlob(file_path)
        await blob.write(data)

        # Record metadata
        with self.using_metadata():
            add(
                file_uri,
                {
                    RDF.type: DCAT.Distribution,
                    DCTERMS.created: context.clock.get()(),
                    DCAT.mediaType: Literal(media_type),
                    NT.hasFilePath: Literal(str(file_path)),
                    DCAT.downloadURL: self.namespace[f"blobs/{sha256}"],
                },
            )

        await self.save_all()

        return file_uri

    async def open_blob(self, sha256: str) -> FileBlob:
        """Open a blob from its SHA-256 hash"""
        file_path = self.graphs_path / "blobs" / sha256[:2] / sha256[2:]
        return FileBlob(file_path)

    def get_streams_with_blobs(
        self,
    ) -> Generator[FileBlob, None, None]:
        """Get all streams that have blobs"""
        for graph in self.graphs():
            for stream in graph.objects(None, NT.hasFilePath):
                yield FileBlob(Path(stream))

    async def save_graph(self, identifier: IdentifiedNode) -> None:
        """Save a graph to its graph.trig file"""
        assert isinstance(identifier, URIRef)

        # Check if this is a builtin graph
        is_builtin = (
            identifier,
            FROTH.isBuiltin,
            Literal(True),
        ) in self.metadata
        if is_builtin:
            raise ValueError(f"Cannot save builtin graph {identifier}")

        graph = self.graph(identifier)
        content = graph.serialize(format="trig")
        logger.debug("Saving graph", identifier=identifier, graph=graph)
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
        if self.dirty_graphs:
            dirty_graphs = self.dirty_graphs.copy()
            self.dirty_graphs.clear()
            logger.debug("Saving graphs", count=len(dirty_graphs))
            for graph in dirty_graphs:
                await self.save_graph(graph.identifier)

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
            await self.git.add(".")
            await self.git.commit(message)

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

    def register_builtin_graph(
        self, identifier: URIRef, path: str
    ) -> Graph:
        """Register a builtin graph that lives in the project source.

        Args:
            identifier: The graph identifier
            path: Path relative to project root

        Returns:
            The registered graph
        """
        logger.debug(
            "Registering builtin graph", identifier=identifier, path=path
        )
        self.metadata.add((identifier, RDF.type, VOID.Dataset))
        self.metadata.add((identifier, FROTH.isBuiltin, Literal(True)))
        self.metadata.add((identifier, NT.hasFilePath, Literal(path)))

        graph = self.dataset.graph(identifier, base=self.namespace)
        graph.parse(path, format="turtle")
        return graph

    def reload_builtin_graphs(self) -> None:
        """Reload all registered builtin graphs from their source files."""
        for s, p, o in self.metadata.triples(
            (None, FROTH.isBuiltin, Literal(True))
        ):
            identifier = URIRef(str(s))
            path = str(get_single_object(identifier, NT.hasFilePath))
            logger.debug(
                "Reloading builtin graph", identifier=identifier, path=path
            )

            # Clear existing graph
            graph = self.dataset.graph(identifier)
            graph.remove((None, None, None))

            # Reload from file
            graph.parse(path, format="turtle")

    def graph(self, identifier: S) -> Graph:
        assert isinstance(identifier, URIRef)
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
        self, activity_type: URIRef, props: dict[P, Any] = {}
    ) -> Generator[URIRef, None, None]:
        """Create a new activity and set it as the current activity.

        Args:
            activity_type: The RDF type of the activity
        """
        activity_id = new(
            activity_type,
            {
                PROV.startedAtTime: context.clock.get()(),
                PROV.wasAssociatedWith: context.agent.get(),
                **props,
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


@asynccontextmanager
async def from_env() -> AsyncIterator[Repository]:
    """Load repository and context from environment variables.

    Requires the following environment variables:
    - BUBBLE: Path to the repository
    - BUBBLE_GRAPH: Current graph URI
    - BUBBLE_ACTIVITY: Current activity URI
    - BUBBLE_AGENT: Current agent URI

    Yields:
        Repository: The loaded repository

    Raises:
        ValueError: If required environment variables are missing
    """
    bubble_path = os.environ.get("BUBBLE")
    bubble_graph = os.environ.get("BUBBLE_GRAPH")
    bubble_activity = os.environ.get("BUBBLE_ACTIVITY")
    bubble_agent = os.environ.get("BUBBLE_AGENT")

    if not bubble_path:
        raise ValueError("BUBBLE environment variable not set")
    if not bubble_graph:
        raise ValueError("BUBBLE_GRAPH environment variable not set")
    if not bubble_activity:
        raise ValueError("BUBBLE_ACTIVITY environment variable not set")
    if not bubble_agent:
        raise ValueError("BUBBLE_AGENT environment variable not set")

    async def init_repo() -> Repository:
        git = Git(trio.Path(bubble_path))
        repo = await Repository.create(
            git, namespace=Namespace("file://" + bubble_path + "/")
        )
        await repo.load_all()
        return repo

    # Run async init in sync context
    repo = await init_repo()

    graph_uri = URIRef(bubble_graph)
    activity_uri = URIRef(bubble_activity)
    agent_uri = URIRef(bubble_agent)

    # Bind all context parameters
    with (
        context.repo.bind(repo),
        context.graph.bind(repo.graph(graph_uri)),
        context.activity.bind(activity_uri),
        context.agent.bind(agent_uri),
        swash.here.dataset.bind(repo.dataset),
    ):
        yield repo
