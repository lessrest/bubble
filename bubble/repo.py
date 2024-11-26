# This module implements a repository of RDF/N3 documents.
#
# It uses a local Git repository for storage.
#
# The default repository is $HOME/bubble.
#
# If the repository is empty, it will be initialized as a new bubble.
# Each bubble has a unique IRI minted on creation.

import os
import pwd
import socket
import getpass
import logging
import platform
import tempfile

from datetime import UTC, datetime

import trio
import psutil

from trio import Path
from rdflib import (
    OWL,
    RDF,
    XSD,
    RDFS,
    Graph,
    URIRef,
    Literal,
    Namespace,
)
from rdflib.graph import QuotedGraph, _TripleType, _SubjectType

from bubble.id import Mint
from bubble.ns import AS, NT, SWA, UUID
from bubble.mac import get_disk_info, computer_serial_number
from bubble.rdfutil import New, print_n3, get_single_subject

logger = logging.getLogger(__name__)


class Bubbler:
    """A repository of RDF/N3 documents"""

    # The path to the bubble's root directory
    workdir: Path

    # The path to the bubble's root.n3 file
    rootpath: Path

    # The mint used to generate IRIs
    minter: Mint

    # The bubble's IRI
    bubble: _SubjectType

    # The graph of the bubble
    graph: Graph

    def __init__(self, path: Path, mint: Mint, base: _SubjectType):
        self.workdir = path
        self.rootpath = path / "root.n3"
        self.minter = mint
        self.bubble = base
        self.graph = Graph()

    async def load_many(
        self,
        directory: Path,
        pattern: str,
        kind: str,
    ) -> None:
        """Load files into the graph

        Args:
            directory: Directory to glob from
            pattern: Glob pattern to match
            kind: Description of what's being loaded for logging
        """
        paths = list(await directory.glob(pattern))

        for path in paths:
            logger.info(f"Loading {kind} from {path}")
            self.graph.parse(path)

    async def load(self, path: Path) -> None:
        """Load the graph from a file"""
        await self.load_many(path.parent, path.name, "graph")

    async def load_ontology(self) -> None:
        """Load the ontology into the graph"""
        vocab_dir = Path(__file__).parent.parent / "vocab"
        await self.load_many(vocab_dir, "*.ttl", "ontology")

    async def load_surfaces(self) -> None:
        """Load all surfaces from the bubble into the graph"""
        await self.load_many(self.workdir, "*.n3", "surface")

    async def load_rules(self) -> None:
        """Load all rules from the system rules directory"""
        rules_dir = Path(__file__).parent / "rules"
        await self.load_many(rules_dir, "*.n3", "rules")

    async def reason(self) -> Graph:
        """Reason over the graph"""
        from bubble.rdfutil import reason

        tmpfile = Path(tempfile.gettempdir()) / "bubble.n3"
        self.graph.serialize(destination=tmpfile, format="n3")
        logger.info(f"Reasoning over {tmpfile}")
        conclusion = await reason([str(tmpfile)])
        logger.info(f"Conclusion has {len(conclusion)} triples")
        return conclusion

    @staticmethod
    async def open(path: Path, mint: Mint) -> "Bubbler":
        def fresh_iri() -> URIRef:
            return mint.fresh_secure_iri(SWA)

        if not await path.exists():
            raise ValueError(f"Bubble not found at {path}")

        if not await (path / "root.n3").exists():
            BUBBLE = Namespace(fresh_iri().toPython() + "/")

            surface = BUBBLE["root.n3"]
            step = fresh_iri()
            head = fresh_iri()

            g = Graph(base=BUBBLE)
            Bubbler.bind_prefixes(g)

            new = New(g, mint)

            (
                computer_serial,
                machine_id,
                now,
                hostname,
                architecture,
                system_type,
                system_version,
                byte_size,
                gigabyte_size,
                user_info,
                person_name,
                disk_info,
                disk_uuid,
            ) = await Bubbler.get_a_bunch_of_info(mint)

            machine = SWA[machine_id]
            disk_urn = UUID[disk_uuid]

            filesystem = new(
                NT.Filesystem,
                {
                    NT.byteSize: Literal(disk_info["Size"]),
                    OWL.sameAs: disk_urn,
                    RDFS.label: Literal(
                        f"disk {disk_info['VolumeName']}", lang="en"
                    ),
                },
                subject=SWA[disk_uuid],
            )

            home_dir = new(
                NT.Directory,
                {
                    NT.filesystem: filesystem,
                    NT.path: Literal(await Path.home()),
                    RDFS.label: Literal(
                        f"home directory of {person_name}", lang="en"
                    ),
                },
            )

            bubble = new(
                NT.Bubble,
                {
                    RDFS.label: Literal(
                        f"a bubble for {person_name}", lang="en"
                    ),
                    NT.head: step,
                },
                subject=BUBBLE["#"],
            )

            new(
                NT.Repository,
                {
                    NT.tracks: bubble,
                    NT.worktree: new(
                        NT.Directory,
                        {
                            NT.filesystem: filesystem,
                            NT.parent: home_dir,
                            NT.path: Literal(path),
                            RDFS.label: Literal(
                                f"worktree directory at {path}",
                                lang="en",
                            ),
                        },
                    ),
                    RDFS.label: Literal(
                        f"bubble repository at {path}", lang="en"
                    ),
                },
            )

            user = new(
                NT.Account,
                {
                    NT.gid: Literal(user_info.pw_gid),
                    NT.homeDirectory: home_dir,
                    NT.owner: new(
                        AS.Person, {NT.name: Literal(person_name)}
                    ),
                    NT.uid: Literal(user_info.pw_uid),
                    NT.username: Literal(getpass.getuser()),
                    RDFS.label: Literal(
                        f"user account for {person_name}", lang="en"
                    ),
                },
            )

            new(
                NT.ComputerMachine,
                {
                    RDFS.label: Literal(
                        f"{person_name}'s {system_type} computer",
                        lang="en",
                    ),
                    NT.hosts: [
                        new(
                            NT.PosixEnvironment,
                            {
                                NT.account: user,
                                NT.filesystem: filesystem,
                                NT.hostname: Literal(hostname),
                                RDFS.label: Literal(
                                    f"POSIX environment on {hostname}",
                                    lang="en",
                                ),
                            },
                        ),
                        new(
                            NT.OperatingSystem,
                            {
                                NT.type: system_type,
                                NT.version: Literal(system_version),
                                RDFS.label: Literal(
                                    f"the {system_type} operating system installed on {hostname}",
                                    lang="en",
                                ),
                            },
                        ),
                    ],
                    NT.part: [
                        new(
                            NT.CentralProcessingUnit,
                            {
                                NT.architecture: architecture,
                                RDFS.label: Literal(
                                    f"the CPU of {person_name}'s {system_type} computer",
                                    lang="en",
                                ),
                            },
                        ),
                        new(
                            NT.RandomAccessMemory,
                            {
                                NT.byteSize: Literal(byte_size),
                                NT.gigabyteSize: Literal(gigabyte_size),
                                RDFS.label: Literal(
                                    f"the RAM of {person_name}'s {system_type} computer",
                                    lang="en",
                                ),
                            },
                        ),
                    ],
                    NT.serialNumber: Literal(computer_serial),
                },
                subject=machine,
            )

            new(
                AS.Create,
                {
                    AS.actor: user,
                    AS.object: bubble,
                    AS.published: now,
                    RDFS.label: Literal(
                        f"creation of the bubble at {path}", lang="en"
                    ),
                },
                subject=BUBBLE["#genesis"],
            )

            def quote(triples: list[_TripleType]) -> QuotedGraph:
                quoted = QuotedGraph(g.store, fresh_iri())
                for subject, predicate, object in triples:
                    quoted.add((subject, predicate, object))
                return quoted

            new(
                NT.Step,
                {
                    NT.supposes: quote([(bubble, NT.head, step)]),
                    RDFS.label: Literal(
                        f"the first step of the bubble at {path}",
                        lang="en",
                    ),
                },
                subject=step,
            )

            new(
                NT.Step,
                {
                    NT.supposes: quote([(bubble, NT.head, head)]),
                    NT.succeeds: step,
                    RDFS.label: Literal(
                        f"the second step of the bubble at {path}",
                        lang="en",
                    ),
                },
                subject=head,
            )

            new(
                AS.Add,
                {
                    AS.actor: user,
                    AS.object: new(
                        NT.Surface,
                        {
                            NT.partOf: bubble,
                            RDFS.label: Literal(
                                f"the root surface of the bubble at {path}",
                                lang="en",
                            ),
                        },
                        subject=surface,
                    ),
                    AS.target: bubble,
                    RDFS.label: Literal(
                        f"addition of the root surface to the bubble at {path}",
                        lang="en",
                    ),
                },
                subject=BUBBLE["#add"],
            )

            print_n3(g)

            g.serialize(destination=path / "root.n3", format="n3")

            bubbler = Bubbler(path, mint, bubble)
            await bubbler.commit()
            return bubbler

        else:
            g = Graph()
            g.parse(path / "root.n3", format="n3")

            bubble = get_single_subject(g, RDF.type, NT.Bubble)

            assert isinstance(bubble, URIRef)
            return Bubbler(path, mint, URIRef(bubble))

    @staticmethod
    async def get_a_bunch_of_info(mint):
        computer_serial = await computer_serial_number()
        machine_id = mint.machine_id()

        now = Bubbler.get_timestamp()
        hostname, arch, system = Bubbler.get_system_info()
        architecture = Bubbler.resolve_architecture(arch)
        system_type, system_version = Bubbler.resolve_system(system)
        byte_size, gigabyte_size = Bubbler.get_memory_size()
        user_info, person_name = Bubbler.get_user_info()

        disk_info = await get_disk_info("/System/Volumes/Data")
        disk_uuid = disk_info["DiskUUID"]
        return (
            computer_serial,
            machine_id,
            now,
            hostname,
            architecture,
            system_type,
            system_version,
            byte_size,
            gigabyte_size,
            user_info,
            person_name,
            disk_info,
            disk_uuid,
        )

    @staticmethod
    def get_timestamp():
        return Literal(datetime.now(UTC), datatype=XSD.dateTime)

    @staticmethod
    def get_system_info():
        hostname = socket.gethostname()
        arch = platform.machine()
        system = platform.system()
        return hostname, arch, system

    @staticmethod
    def get_memory_size():
        memory_info = psutil.virtual_memory()
        byte_size = memory_info.total
        gigabyte_size = round(byte_size / 1024 / 1024 / 1024, 2)
        return byte_size, gigabyte_size

    @staticmethod
    def get_user_info():
        user_info = pwd.getpwuid(os.getuid())
        person_name = user_info.pw_gecos
        return user_info, person_name

    @staticmethod
    def resolve_system(system):
        match system:
            case "Darwin":
                system_type = NT.macOSEnvironment
                system_version = platform.mac_ver()[0]

            case _:
                raise ValueError(f"Unknown operating system: {system}")
        return system_type, system_version

    @staticmethod
    def resolve_architecture(arch):
        match arch:
            case "x86_64":
                architecture = NT.AMD64
            case "arm64":
                architecture = NT.ARM64
            case _:
                raise ValueError(f"Unknown architecture: {arch}")
        return architecture

    @staticmethod
    def bind_prefixes(g):
        g.bind("swa", SWA)
        g.bind("nt", NT)
        g.bind("as", AS)

    async def commit(self) -> None:
        """Commit the bubble"""
        await trio.run_process(
            ["git", "-C", str(self.workdir), "add", "."]
        )
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
