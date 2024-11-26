# This module implements a repository of RDF/N3 documents.
#
# It uses a local Git repository for storage.
#
# The default repository is $HOME/bubble.
#
# If the repository is empty, it will be initialized as a new bubble.
# Each bubble has a unique IRI minted on creation.

from datetime import UTC, datetime
import getpass
import platform
import socket
import trio

from trio import Path
from rdflib import OWL, RDF, XSD, Graph, Literal, URIRef

from bubble.id import Mint
from bubble.ns import AS, NT, SWA
from bubble.n3_utils import get_single_subject
from bubble.mac import computer_serial_number, get_disk_info
import psutil


class Bubble:
    """A repository of RDF/N3 documents"""

    path: Path
    root: Path
    mint: Mint
    base: URIRef
    graph: Graph

    def __init__(self, path: Path, mint: Mint, base: URIRef):
        self.path = path
        self.root = path / "root.n3"
        self.mint = mint
        self.base = base

        self.graph = Graph(base=base, identifier=base)
        self.graph.parse(self.root, format="n3")

    async def load_all_documents(self) -> None:
        """Load all documents from the repository into the graph"""
        for path in await self.path.glob("*.n3"):
            self.graph.parse(path, format="n3")

    @staticmethod
    async def open(path: Path, mint: Mint) -> "Bubble":
        if not await path.exists():
            raise ValueError(f"Bubble not found at {path}")

        if not await (path / "root.n3").exists():
            base = mint.fresh_secure_iri(SWA)
            graph = Graph(base=base, identifier=base)
            graph.bind("swa", SWA)
            graph.bind("nt", NT)
            graph.bind("as", AS)

            graph.add((base, RDF.type, NT.Bubble))

            machine_id = mint.machine_id()
            machine = SWA[machine_id]
            computer_serial = await computer_serial_number()
            graph.add((machine, RDF.type, NT.ComputerMachine))
            graph.add((machine, NT.serialNumber, Literal(computer_serial)))
            person = mint.fresh_secure_iri(SWA)
            graph.add((person, RDF.type, AS.Person))

            user = mint.fresh_secure_iri(SWA)
            graph.add((user, RDF.type, NT.Account))
            graph.add((user, NT.username, Literal(getpass.getuser())))
            graph.add((user, NT.owner, person))
            graph.add((user, NT.context, machine))

            # find hostname
            hostname = socket.gethostname()
            graph.add((machine, NT.hostname, Literal(hostname)))

            # find architecture
            cpu_part = mint.fresh_blank_node()
            graph.add((machine, NT.hasPart, cpu_part))
            graph.add((cpu_part, RDF.type, NT.CentralProcessingUnit))

            arch = platform.machine()
            match arch:
                case "x86_64":
                    graph.add((cpu_part, NT.architecture, NT.AMD64))
                case "arm64":
                    graph.add((cpu_part, NT.architecture, NT.ARM64))
                case _:
                    raise ValueError(f"Unknown architecture: {arch}")

            # find operating system
            os = platform.system()
            match os:
                case "Darwin":
                    os_part = mint.fresh_blank_node()
                    graph.add((machine, NT.hasPart, os_part))
                    graph.add((os_part, RDF.type, NT.MacOSInstallation))
                    graph.add(
                        (os_part, NT.version, Literal(platform.mac_ver()[0]))
                    )
                case _:
                    raise ValueError(f"Unknown operating system: {os}")

            # find amount of memory
            memory_info = psutil.virtual_memory()
            memory_part = mint.fresh_blank_node()
            graph.add((machine, NT.hasPart, memory_part))
            graph.add((memory_part, RDF.type, NT.RandomAccessMemory))
            graph.add((memory_part, NT.byteSize, Literal(memory_info.total)))
            graph.add(
                (
                    memory_part,
                    NT.gigabyteSize,
                    Literal(
                        round(memory_info.total / 1024 / 1024 / 1024, 2),
                        datatype=XSD.decimal,
                    ),
                )
            )

            disk_info = await get_disk_info("/System/Volumes/Data")
            disk_uuid = disk_info["DiskUUID"]
            disk_urn = URIRef(f"urn:uuid:{disk_uuid}")

            assert isinstance(disk_uuid, str)

            filesystem = SWA[disk_uuid]
            graph.add((filesystem, OWL.sameAs, disk_urn))
            graph.add((filesystem, RDF.type, NT.Filesystem))
            graph.add((filesystem, NT.byteSize, Literal(disk_info["Size"])))
            graph.add((machine, NT.hasPart, filesystem))

            home_dir = mint.fresh_secure_iri(SWA)
            graph.add((user, NT.homeDirectory, home_dir))
            graph.add((home_dir, RDF.type, NT.Directory))
            graph.add((home_dir, NT.path, Literal(await Path.home())))
            graph.add((home_dir, NT.filesystem, filesystem))

            repo_dir = mint.fresh_secure_iri(SWA)
            graph.add((repo_dir, RDF.type, NT.Directory))
            graph.add((repo_dir, NT.path, Literal(path)))
            graph.add((repo_dir, NT.filesystem, filesystem))
            graph.add((repo_dir, NT.parent, home_dir))

            repo = mint.fresh_secure_iri(SWA)
            graph.add((repo, RDF.type, NT.Repository))
            graph.add((repo, NT.tracks, base))
            graph.add((repo, NT.hasWorkingDirectory, repo_dir))

            head = mint.fresh_secure_iri(SWA)
            creation_activity = mint.fresh_secure_iri(SWA)
            graph.add((creation_activity, RDF.type, AS.Create))
            graph.add((creation_activity, AS.actor, user))
            graph.add((creation_activity, AS.object, base))

            now = Literal(datetime.now(UTC), datatype=XSD.dateTime)
            graph.add((creation_activity, AS.published, now))

            graph.add((base, NT.pointsTo, head))
            graph.add((head, RDF.type, NT.Step))
            graph.add((head, NT.ranks, Literal(1)))

            graph.serialize(destination=path / "root.n3", format="n3")
            bubble = Bubble(path, mint, base)
            await bubble.commit()
            return bubble

        else:
            graph = Graph()
            graph.parse(path / "root.n3", format="n3")

            base = get_single_subject(graph, RDF.type, NT.Bubble)

            assert isinstance(base, URIRef)
            return Bubble(path, mint, URIRef(base))

    async def commit(self) -> None:
        """Commit the bubble"""
        await trio.run_process(["git", "-C", str(self.path), "add", "."])
        result = await trio.run_process(
            [
                "git",
                "-C",
                str(self.path),
                "commit",
                "-m",
                f"Initialize {self.base}",
            ],
            capture_stdout=True,
            capture_stderr=True,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError(f"Failed to commit: {result.stderr}")
