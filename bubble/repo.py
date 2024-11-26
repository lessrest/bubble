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
import pathlib
import platform
import pwd
import socket
import trio

from trio import Path
from rdflib import OWL, RDF, XSD, Graph, Literal, URIRef

from bubble.id import Mint
from bubble.ns import AS, NT, SWA
from bubble.n3_utils import get_single_subject
from bubble.mac import computer_serial_number, get_disk_info
import psutil
import os
import logging

logger = logging.getLogger(__name__)


class Bubble:
    """A repository of RDF/N3 documents"""

    # The path to the bubble's root directory
    workdir: Path

    # The path to the bubble's root.n3 file
    rootpath: Path

    # The mint used to generate IRIs
    minter: Mint

    # The bubble's IRI
    bubble: URIRef

    # The graph of the bubble
    graph: Graph

    def __init__(self, path: Path, mint: Mint, base: URIRef):
        self.workdir = path
        self.rootpath = path / "root.n3"
        self.minter = mint
        self.bubble = base
        self.graph = Graph()

    async def load(self, path: Path) -> None:
        """Load the graph from a file"""
        logger.info(f"Loading graph from {path}")
        self.graph.parse(path)

    async def load_ontology(self) -> None:
        """Load the ontology into the graph"""
        vocab = Path(__file__).parent.parent / "vocab" / "nt.ttl"
        logger.info(f"Loading ontology from {vocab}")
        self.graph.parse(vocab, format="turtle")

    async def load_surfaces(self) -> None:
        """Load all surfaces from the bubble into the graph"""
        for path in await self.workdir.glob("*.n3"):
            logger.info(f"Loading surface from {path}")
            self.graph.parse(path, format="n3")

    async def load_rules(self) -> None:
        """Load all rules from the system rules directory"""
        rules = Path(__file__).parent / "rules"
        for path in await rules.glob("*.n3"):
            logger.info(f"Loading rules from {path}")
            self.graph.parse(path, format="n3")

    @staticmethod
    async def open(path: Path, mint: Mint) -> "Bubble":
        if not await path.exists():
            raise ValueError(f"Bubble not found at {path}")

        if not await (path / "root.n3").exists():
            bubble = mint.fresh_secure_iri(SWA)
            surface = URIRef(f"{bubble.toPython()}/root.n3")

            g = Graph(base=surface.toPython())
            g.bind("swa", SWA)
            g.bind("nt", NT)
            g.bind("as", AS)

            g.add((bubble, RDF.type, NT.Bubble))
            g.add((surface, RDF.type, NT.Surface))
            g.add((surface, NT.partOf, bubble))

            machine_id = mint.machine_id()
            machine = SWA[machine_id]
            computer_serial = await computer_serial_number()

            g.add((machine, RDF.type, NT.ComputerMachine))
            g.add((machine, NT.serialNumber, Literal(computer_serial)))

            posixenv = mint.fresh_secure_iri(SWA)
            g.add((posixenv, RDF.type, NT.PosixEnvironment))
            g.add((machine, NT.hosts, posixenv))

            user_info = pwd.getpwuid(os.getuid())
            person_name = user_info.pw_gecos

            person = mint.fresh_secure_iri(SWA)
            g.add((person, RDF.type, AS.Person))
            g.add((person, NT.name, Literal(person_name)))

            user = mint.fresh_secure_iri(SWA)
            g.add((user, RDF.type, NT.Account))
            g.add((user, NT.owner, person))
            g.add((user, NT.username, Literal(getpass.getuser())))
            g.add((user, NT.uid, Literal(user_info.pw_uid)))
            g.add((user, NT.gid, Literal(user_info.pw_gid)))
            g.add((posixenv, NT.account, user))

            hostname = socket.gethostname()
            g.add((posixenv, NT.hostname, Literal(hostname)))

            cpu_part = mint.fresh_secure_iri(SWA)
            g.add((machine, NT.part, cpu_part))
            g.add((cpu_part, RDF.type, NT.CentralProcessingUnit))

            arch = platform.machine()
            match arch:
                case "x86_64":
                    g.add((cpu_part, NT.architecture, NT.AMD64))
                case "arm64":
                    g.add((cpu_part, NT.architecture, NT.ARM64))
                case _:
                    raise ValueError(f"Unknown architecture: {arch}")

            system = platform.system()
            match system:
                case "Darwin":
                    system_part = mint.fresh_secure_iri(SWA)
                    g.add((system_part, RDF.type, NT.macOSEnvironment))
                    g.add(
                        (
                            system_part,
                            NT.version,
                            Literal(platform.mac_ver()[0]),
                        )
                    )
                    g.add((machine, NT.hosts, system_part))

                case _:
                    raise ValueError(f"Unknown operating system: {system}")

            # find amount of memory
            memory_info = psutil.virtual_memory()
            memory_part = mint.fresh_secure_iri(SWA)
            g.add((machine, NT.part, memory_part))
            g.add((memory_part, RDF.type, NT.RandomAccessMemory))
            g.add((memory_part, NT.byteSize, Literal(memory_info.total)))
            g.add(
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
            g.add((filesystem, OWL.sameAs, disk_urn))
            g.add((filesystem, RDF.type, NT.Filesystem))
            g.add((filesystem, NT.byteSize, Literal(disk_info["Size"])))
            g.add((posixenv, NT.filesystem, filesystem))

            home_dir = mint.fresh_secure_iri(SWA)
            g.add((user, NT.homeDirectory, home_dir))
            g.add((home_dir, RDF.type, NT.Directory))
            g.add((home_dir, NT.path, Literal(await Path.home())))
            g.add((home_dir, NT.filesystem, filesystem))

            worktree = mint.fresh_secure_iri(SWA)
            g.add((worktree, RDF.type, NT.Directory))
            g.add((worktree, NT.path, Literal(path)))
            g.add((worktree, NT.filesystem, filesystem))
            g.add((worktree, NT.parent, home_dir))

            repo = mint.fresh_secure_iri(SWA)
            g.add((repo, RDF.type, NT.Repository))
            g.add((repo, NT.tracks, bubble))
            g.add((repo, NT.worktree, worktree))

            head = mint.fresh_secure_iri(SWA)
            creation = mint.fresh_secure_iri(SWA)
            g.add((creation, RDF.type, AS.Create))
            g.add((creation, AS.actor, user))
            g.add((creation, AS.object, bubble))

            surface_addition = mint.fresh_secure_iri(SWA)
            g.add((surface_addition, RDF.type, AS.Add))
            g.add((surface_addition, AS.actor, user))
            g.add((surface_addition, AS.object, surface))
            g.add((surface_addition, AS.target, bubble))

            now = Literal(datetime.now(UTC), datatype=XSD.dateTime)
            g.add((creation, AS.published, now))

            g.add((bubble, NT.head, head))
            g.add((head, RDF.type, NT.Step))
            g.add((head, NT.rank, Literal(1)))

            g.serialize(destination=path / "root.n3", format="n3")
            bubble = Bubble(path, mint, bubble)
            await bubble.commit()
            return bubble

        else:
            g = Graph()
            g.parse(path / "root.n3", format="n3")

            bubble = get_single_subject(g, RDF.type, NT.Bubble)

            assert isinstance(bubble, URIRef)
            return Bubble(path, mint, URIRef(bubble))

    async def commit(self) -> None:
        """Commit the bubble"""
        await trio.run_process(["git", "-C", str(self.workdir), "add", "."])
        result = await trio.run_process(
            [
                "git",
                "-C",
                str(self.workdir),
                "commit",
                "-m",
                f"Initialize {self.bubble}",
            ],
            capture_stdout=True,
            capture_stderr=True,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError(f"Failed to commit: {result.stderr}")
