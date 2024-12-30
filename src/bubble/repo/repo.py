"""The Repository: Where RDF triples go to achieve immortality.

In the beginning was the Graph, and the Graph was with Git,
and the Graph was versioned. Through commits all things were
preserved; without commits was not any triple preserved that
was preserved.

Historical note: RDF was conceived in the heady days of the semantic web,
when we thought machines would understand meaning as easily as they
process syntax. Two decades later, we're still explaining to ChatGPT
that a "hot dog" is not a dog with a fever.
"""

import os
import base64
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
from urllib.parse import urlparse
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
from rdflib.namespace import DCAT, PROV, DCTERMS
from cryptography.hazmat.primitives.asymmetric import ed25519

import swash

from swash import here
from swash.mint import fresh_uri
from swash.prfx import NT
from swash.util import O, P, S, add, new, get_single_object
from bubble.keys import generate_keypair, get_public_key_bytes
from bubble.repo.git import Git

FROTH = Namespace("https://node.town/ns/froth#")


logger = structlog.get_logger()


class context:
    """Manages the current graph, activity and agent context.

    Like Emacs with its dynamically scoped point, mark, and current buffer,
    we maintain a set of contextual locations that define "where" and "who"
    we are at any moment. Just as an Emacs user moves through buffers with
    save-excursion, we move through graphs with contextual bindings.

    The context system provides a rich notion of "current place":

    - buffer: The current graph we're editing (like current-buffer)
    - activity: What we're doing (like a keyboard macro recording)
    - agent: Who's doing it (like the current auth-source)
    - clock: When we're doing it (our version of current-time)
    - repo: Where we're doing it (like default-directory)

    Each of these can be temporarily rebound with context managers,
    creating a stack of bindings that automatically unwind, just like
    Emacs's save-excursion or save-restriction. This lets us safely
    nest operations while maintaining proper context.

    Dynamic scope is a beautiful thing - it gives us a clear sense of
    "where we are" at any moment, while ensuring we always return home
    when we're done. Like breadcrumbs in a fairy tale, our context
    managers ensure we can always find our way back.

    The genius of Emacs wasn't just in having a notion of "current place",
    but in making that place a dynamic binding that could be temporarily
    changed and automatically restored. We follow in those footsteps.
    """

    buffer = here.graph  # The current graph (like current-buffer)
    activity = here.Parameter["URIRef"](
        "current_activity"
    )  # What we're doing
    agent = here.Parameter["URIRef"]("current_agent")  # Who's doing it
    clock = here.Parameter[Callable[[], O]]("current_clock")  # When
    repo = here.Parameter["Repository"]("current_repo")  # Where

    @classmethod
    @contextmanager
    def bind_graph(
        cls, graph_id: URIRef, repo: Optional["Repository"] = None
    ) -> Generator[Graph, None, None]:
        """Bind both the context graph and the legacy vars graph parameter.

        Like save-excursion in Emacs, this creates a temporary binding of
        the current graph, ensuring we return to our previous location no
        matter what happens within the with block.

        The marriage metaphor still holds - it's a temporary union of
        context and graph, but now we understand it more as a dynamic
        scope than an eternal bond. Let no developer put asunder what
        context has joined together, at least until the with block ends.
        """
        repo = repo or context.repo.get()
        graph = repo.graph(graph_id)
        with cls.buffer.bind(graph), here.in_graph(graph):
            yield graph


context.clock.set(
    lambda: Literal(arrow.now().datetime, datatype=XSD.dateTime)
)


def timestamp() -> O:
    """Get the current time from our contextual clock.

    Time is an illusion. Lunchtime doubly so.
    Repository time triply so - it's whatever our clock says it is.
    """
    return context.clock.get()()


class FileBlob:
    """A blob stored as a file in the git repository.

    In Git's content-addressable filesystem, blobs are the atoms
    of our universe - indivisible units of content that combine
    to form the molecules of our codebase.

    Fun fact: 'blob' stands for 'binary large object', but we use
    it for text too because consistency is overrated.
    """

    def __init__(self, path: Path):
        """Initialize a new blob at the given path.

        Args:
            path: Where this blob will materialize in our filesystem.
                 Choose wisely - a good path is worth a thousand words.
        """
        self.path = path
        self._file: Optional[BinaryIO] = None

    async def open(self, mode: str = "rb") -> BinaryIO:
        """Open and return the file handle.

        Like opening Pandora's box, but with better error handling
        and hopefully fewer catastrophic consequences.
        """
        await self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = cast(BinaryIO, open(self.path, mode))
        assert self._file is not None
        return self._file

    async def write(self, data: bytes) -> None:
        """Write data to the file.

        In the grand tradition of persistence, we take ephemeral
        bytes and grant them a more permanent existence on disk.
        At least until the next rm -rf.
        """
        io = await self.open("wb")
        io.write(data)
        io.close()

    async def read(self) -> bytes:
        """Read data from the file.

        Resurrect the bytes that were once written, hopefully
        finding them exactly as we left them. The miracle of
        storage technology.
        """
        io = await self.open("rb")
        return io.read()

    def close(self) -> None:
        """Close the file if open.

        All good things must come to an end, including file handles.
        Especially file handles. Please close your files.
        """
        if self._file:
            self._file.close()
            self._file = None

    async def __aenter__(self) -> BinaryIO:
        return await self.open()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class Repository:
    """A versioned RDF dataset with Git-backed persistence.

    This is where the magic happens - where RDF meets Git, where
    semantic graphs gain version control, and where developers
    start questioning their life choices about using semantic
    technologies in 2023.

    The dirty_graphs set is our conscience - it keeps track of
    what needs to be saved, like a persistent mother asking if
    you've done your homework.
    """

    dirty_graphs: set[Graph] = set()

    async def __init__(
        self,
        git: Git,
        base_url_template: str,
        dataset: Optional[Dataset] = None,
        metadata_id: URIRef = URIRef("urn:x-meta:"),
    ):
        """Initialize a new repository or load an existing one.

        This is a complex dance of initialization steps that would
        make a Baroque court choreographer proud. We generate keys,
        set up namespaces, bind graphs, and generally try to make
        sense of the semantic web.
        """
        self.git = git

        # Generate or load keypair first since we need repo_id for base URL
        await self._init_keypair()

        # Parse base URL template
        parsed = urlparse(base_url_template)

        if "{repo}" in parsed.netloc:
            hostname = parsed.netloc.format(repo=self.repo_id)
            base_url = parsed._replace(netloc=hostname).geturl()
        else:
            base_url = base_url_template

        # Ensure URL ends with forward slash
        if not base_url.endswith("/"):
            base_url += "/"

        self.base_url = base_url
        logger.info(
            "Using base URL", base_url=self.base_url, repo_id=self.repo_id
        )

        self.namespace = Namespace(self.base_url)
        self.dataset = dataset or Dataset(default_union=True)

        self.dataset.bind("home", self.namespace)
        self.metadata_id = metadata_id
        self.metadata = self.dataset.graph(metadata_id)

        self.metadata.bind("home", self.namespace)

        # Register builtin graphs
        vocab_ext = URIRef("urn:x-bubble:vocab:ext")
        self.register_builtin_graph(vocab_ext, "vocab/ext.ttl")
        # Base path for graphs
        self.graphs_path = Path(self.git.workdir) / "graphs"

        # Load existing metadata if available
        try:
            content = await self.git.read_file("void.ttl")
            self.metadata.parse(data=content, format="turtle")
            self.metadata.bind("home", self.namespace)
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

    async def _init_keypair(self):
        """Initialize or load the repository's keypair."""
        try:
            # Try to load existing keypair from metadata
            key_data = await self.git.read_file(".bubble/key")
            private_key = ed25519.Ed25519PrivateKey.from_private_bytes(
                base64.b64decode(key_data)
            )
            self.private_key = private_key
            self.public_key = private_key.public_key()
        except FileNotFoundError:
            # Generate new keypair
            self.private_key, self.public_key = generate_keypair()
            # Save private key
            key_bytes = base64.b64encode(
                self.private_key.private_bytes_raw()
            ).decode()
            await self.git.write_file(".bubble/key", key_bytes)

        # Get repo ID from public key
        pub_bytes = get_public_key_bytes(self.public_key)
        self.repo_id = (
            base64.b32encode(pub_bytes[:5]).decode().rstrip("=").lower()
        )

    def get_repo_id(self) -> str:
        """Get the repository's unique ID derived from its public key."""
        return self.repo_id

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
        base_url_template: str,
        dataset: Optional[Dataset] = None,
        metadata_id: URIRef = URIRef("urn:x-bubble:meta"),
    ) -> "Repository":
        """Factory method to create a new Repository instance."""
        self = cls.__new__(cls)
        await self.__init__(git, base_url_template, dataset, metadata_id)  # type: ignore
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
        with self.using_buffer(identifier):
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
        """Bind the metadata graph as the current graph.

        Like (with-current-buffer *Messages*) in Emacs, this temporarily
        makes the metadata graph our current location. It's a special place
        where we keep our system's internal bookkeeping - a cozy corner
        of the semantic space where we track what we know about our graphs.
        """
        with context.bind_graph(self.metadata_id, self):
            yield self.metadata

    @contextmanager
    def using_buffer(
        self, identifier: URIRef
    ) -> Generator[Graph, None, None]:
        """Bind the specified graph as the current graph.

        The Emacs equivalent of (with-current-buffer (find-file "some.ttl")),
        this makes a specific graph our current location. Just as Emacs users
        naturally think in terms of "the current buffer", we think in terms
        of "the current graph" - a familiar home for our immediate work.
        """
        with context.bind_graph(identifier, self) as graph:
            yield graph

    @contextmanager
    def using_new_buffer(self) -> Generator[URIRef, None, None]:
        """Create a new graph with a fresh URI and set it as the current buffer.

        Like (with-temp-buffer) in Emacs, this creates a new space and makes
        it our current location. The URI is our address in the semantic web,
        automatically chosen to be unique in our namespace - a fresh page
        ready for new ideas.
        """
        graph_id = fresh_uri(self.namespace)
        with self.using_buffer(graph_id):
            yield graph_id

    @contextmanager
    def using_new_activity(
        self, activity_type: URIRef, props: dict[P, Any] = {}
    ) -> Generator[URIRef, None, None]:
        """Create a new activity and set it as the current activity.

        Just as Emacs users naturally think about what command they're
        currently executing, we track what activity we're currently
        performing. This creates a new activity and makes it our current
        focus, automatically tracking timing and nesting.

        Args:
            activity_type: The RDF type of the activity (like a major mode)
            props: Additional properties for the activity
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
    def using_new_agent(
        self,
        agent_type: URIRef,
        props: Optional[dict[P, Any]] = None,
    ) -> Generator[URIRef, None, None]:
        """Create a new agent and set it as the current agent.

        Like auth-source-with-cache in Emacs, this establishes who's
        performing the operations. In Emacs you might switch between
        different auth sources; here we switch between different agents,
        each with their own identity and capabilities.

        Args:
            agent_type: The RDF type of the agent (like an auth-source type)
            props: Optional properties to add to the agent
        """
        agent_id = new(agent_type, props or {})

        with context.agent.bind(agent_id):
            yield agent_id

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
        graph = context.buffer.get()
        if not graph:
            raise ValueError("No current graph set")
        graph.add(triple)

    def get_base_url(self) -> str:
        """Get the repository's base URL with repo ID if templated."""
        return self.base_url

    @contextmanager
    def using_derived_buffer(
        self,
        origin: Optional[URIRef] = None,
        activity: Optional[URIRef] = None,
    ) -> Generator[URIRef, None, None]:
        """Create a new graph derived from an existing graph.

        Like (clone-buffer) in Emacs, but with provenance tracking.
        We remember where the new graph came from and what activity
        created it, like Emacs remembering a buffer's file-name and
        major-mode.

        Args:
            origin: The graph this is derived from.
              Defaults to the current buffer.
            activity: Optional activity that caused this derivation.
              Defaults to the current activity.
        """
        graph_id = fresh_uri(self.namespace)
        source = origin if origin is not None else context.buffer.get()
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

    async def has_changes(self) -> bool:
        """Check if there are any uncommitted changes in the repository.

        Like buffer-modified-p in Emacs, but for the whole repository.
        This checks if we have any unsaved changes that need to be
        committed to our version control system.
        """
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
    - BUBBLE_REPO: Path to the repository
    - BUBBLE_BASE: Base URL for the repository
    - BUBBLE_GRAPH: Current graph URI
    - BUBBLE_ACTIVITY: Current activity URI
    - BUBBLE_AGENT: Current agent URI

    Yields:
        Repository: The loaded repository

    Raises:
        ValueError: If required environment variables are missing
    """
    bubble_path = os.environ.get("BUBBLE_REPO")
    bubble_base = os.environ.get("BUBBLE_BASE")
    bubble_graph = os.environ.get("BUBBLE_GRAPH")
    bubble_activity = os.environ.get("BUBBLE_ACTIVITY")
    bubble_agent = os.environ.get("BUBBLE_AGENT")

    if not bubble_path:
        raise ValueError("BUBBLE environment variable not set")
    if not bubble_base:
        raise ValueError("BUBBLE_BASE environment variable not set")
    if not bubble_graph:
        raise ValueError("BUBBLE_GRAPH environment variable not set")
    if not bubble_activity:
        raise ValueError("BUBBLE_ACTIVITY environment variable not set")
    if not bubble_agent:
        raise ValueError("BUBBLE_AGENT environment variable not set")

    async def init_repo() -> Repository:
        git = Git(trio.Path(bubble_path))
        repo = await Repository.create(git, base_url_template=bubble_base)
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
        context.buffer.bind(repo.graph(graph_uri)),
        context.activity.bind(activity_uri),
        context.agent.bind(agent_uri),
        swash.here.dataset.bind(repo.dataset),
    ):
        yield repo
