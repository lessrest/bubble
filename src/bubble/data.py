from contextlib import contextmanager
import subprocess
from typing import Optional, Iterator, Generator
from swash.mint import fresh_uri
from swash.util import new
import structlog
import trio
import os
from rdflib import Dataset, Graph, URIRef, RDF, VOID, Literal, Namespace
from rdflib.namespace import PROV
from swash import vars

FROTH = Namespace("https://node.town/ns/froth#")


logger = structlog.get_logger()


class context:
    """Manages the current graph, activity and agent context."""

    graph = vars.Parameter["Graph"]("current_graph")
    activity = vars.Parameter["URIRef"]("current_activity")
    agent = vars.Parameter["URIRef"]("current_agent")

    @classmethod
    @contextmanager
    def bind_graph(
        cls, graph_id: URIRef, repo: "GraphRepo"
    ) -> Generator[Graph, None, None]:
        """Bind both the context graph and the legacy vars graph parameter."""
        graph = repo.graph(graph_id)
        with cls.graph.bind(graph), vars.in_graph(graph):
            yield graph


class Git:
    def __init__(self, workdir: str):
        self.workdir = workdir

    async def init(self) -> None:
        if not await self.exists(".git"):
            logger.info("Initializing git repository", workdir=self.workdir)
            await trio.run_process(
                ["git", "-C", self.workdir, "init"],
            )

    async def add(self, pattern: str) -> None:
        await trio.run_process(
            ["git", "-C", self.workdir, "add", pattern],
        )

    async def commit(self, message: str) -> None:
        await trio.run_process(
            ["git", "-C", self.workdir, "commit", "-m", message]
        )

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
        import tempfile

        logger.debug("Writing file to git", path=path)
        # Write to temp file first
        fd, temp_path = tempfile.mkstemp()
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            # Copy to repository
            await trio.run_process(
                ["cp", temp_path, os.path.join(self.workdir, path)]
            )
            logger.debug("File written successfully", path=path)
        finally:
            os.unlink(temp_path)


class GraphRepo:
    def __init__(
        self,
        git: Git,
        namespace: Namespace,
        dataset: Optional[Dataset] = None,
        metadata_id: URIRef = URIRef("urn:x-meta:"),
    ):
        self.git = git
        self.namespace = namespace
        self.dataset = dataset or Dataset(default_union=True)
        self.metadata_id = metadata_id
        self.metadata = self.dataset.graph(metadata_id)

    @contextmanager
    def using_metadata(self) -> Generator[Graph, None, None]:
        """Bind the metadata graph as the current graph."""
        with context.bind_graph(self.metadata_id, self):
            yield self.metadata

    async def load_metadata(self) -> None:
        try:
            content = await self.git.read_file("void.ttl")
            logger.info("Loading metadata from void.ttl")
            self.metadata.parse(data=content, format="turtle")
        except FileNotFoundError:
            logger.info("No existing metadata found")

    def graph(self, identifier: URIRef) -> Graph:
        if identifier not in self.list_graphs():
            logger.info("Registering new graph", identifier=identifier)
            self.metadata.add((identifier, RDF.type, VOID.Dataset))
        return self.dataset.graph(identifier)

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

    def _graph_filename(self, identifier: URIRef) -> str:
        safe_name = str(identifier).replace("/", "_").replace(":", "_")
        return f"{safe_name}.trig"

    async def save_graph(self, identifier: URIRef) -> None:
        graph = self.graph(identifier)
        content = graph.serialize(format="trig")
        filename = self._graph_filename(identifier)
        logger.info(
            "Saving graph",
            identifier=identifier,
            filename=filename,
            triples=len(graph),
        )
        await self.git.write_file(filename, content)

    async def save_all(self) -> None:
        # Save metadata first
        logger.info("Saving all graphs")
        content = self.metadata.serialize(format="turtle")
        await self.git.write_file("void.ttl", content)

        # Then save all registered graphs
        graphs = self.list_graphs()
        logger.info("Saving graphs", count=len(graphs))
        for identifier in graphs:
            await self.save_graph(identifier)

    async def load_graph(self, identifier: URIRef) -> None:
        filename = self._graph_filename(identifier)
        try:
            content = await self.git.read_file(filename)
            logger.info(
                "Loading graph", identifier=identifier, filename=filename
            )
            self.graph(identifier).parse(data=content, format="trig")
        except FileNotFoundError:
            logger.info(
                "New graph, no content to load", identifier=identifier
            )

    async def load_all(self) -> None:
        logger.info("Loading all graphs")
        await self.load_metadata()
        graphs = self.list_graphs()
        logger.info("Loading graphs", count=len(graphs))
        for identifier in graphs:
            await self.load_graph(identifier)

    async def commit(self, message: str) -> None:
        logger.info("Committing changes", message=message)
        await self.git.init()
        await self.git.add("*.trig")
        await self.git.add("void.ttl")
        await self.git.commit(message)

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
        with context.bind_graph(graph_id, self):
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

        act = activity if activity is not None else context.activity.get()

        # Temporarily bind metadata graph for adding provenance
        with self.using_metadata():
            # Create qualified derivation using new()
            deriv = new(
                FROTH.GraphDerivation,
                {
                    PROV.entity: source,
                    PROV.hadActivity: act if act else None,
                },
                subject=fresh_uri(self.namespace),
            )

            # Link the derivation
            new(None, {PROV.qualifiedDerivation: deriv}, subject=graph_id)

            # Add agent association if present
            try:
                agent = context.agent.get(None) if act else None
            except LookupError:
                agent = None
            if act and agent:
                new(None, {PROV.wasAssociatedWith: agent}, subject=act)

        with context.bind_graph(graph_id, self):
            yield graph_id
