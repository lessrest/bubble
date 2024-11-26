"""Bubble initialization module.

This module handles the creation of new bubbles, which are versioned RDF graphs.
It sets up the initial graph structure with system information, user details,
and basic bubble metadata. The created bubble includes:

- System information (OS, CPU, RAM, filesystem details)
- User account information
- Basic bubble structure with initial steps
- Root surface file

The module uses RDF and the Notation3 format to represent all data.
"""

from bubble.gensym import fresh_iri
from bubble.ns import AS, NT, SWA, UUID, bind_prefixes
from bubble.rdfutil import graphvar, new
from bubble.sysinfo import gather_system_info


from rdflib import OWL, RDFS, Graph, Literal, Namespace
from rdflib.graph import _TripleType, QuotedGraph, _SubjectType
from trio import Path


import getpass


async def create_new_bubble(path: Path) -> _SubjectType:
    BUBBLE = Namespace(fresh_iri().toPython() + "/")

    surface = BUBBLE["root.n3"]
    step = fresh_iri()
    head = fresh_iri()

    g = Graph(base=BUBBLE)
    graphvar.set(g)

    bind_prefixes(g)

    info = await gather_system_info()

    machine = SWA[info["machine_id"]]
    disk_urn = UUID[info["disk_uuid"]]

    filesystem = describe_filesystem(info, disk_urn)

    home_dir = await describe_home_directory(info, filesystem)
    bubble = construct_bubble_entity(BUBBLE, step, info)
    user = describe_user_account(info, home_dir)

    describe_repository(path, filesystem, home_dir, bubble)
    describe_machine(info, machine, filesystem, user)
    describe_creation_event(user, bubble, path, info)
    describe_steps(bubble, step, head, path)
    describe_root_surface(user, bubble, surface, path)

    g.serialize(destination=path / "root.n3", format="n3")

    return bubble


def describe_user_account(info, home_dir):
    return new(
        NT.Account,
        {
            NT.gid: Literal(info["user_info"].pw_gid),
            NT.homeDirectory: home_dir,
            NT.owner: new(
                AS.Person,
                {NT.name: Literal(info["person_name"])},
            ),
            NT.uid: Literal(info["user_info"].pw_uid),
            NT.username: Literal(getpass.getuser()),
            RDFS.label: Literal(
                f"user account for {info['person_name']}",
                lang="en",
            ),
        },
    )


def describe_repository(path, filesystem, home_dir, bubble):
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


def construct_bubble_entity(BUBBLE, step, info):
    return new(
        NT.Bubble,
        {
            RDFS.label: Literal(
                f"a bubble for {info['person_name']}", lang="en"
            ),
            NT.head: step,
        },
        subject=BUBBLE["#"],
    )


async def describe_home_directory(info, filesystem):
    return new(
        NT.Directory,
        {
            NT.filesystem: filesystem,
            NT.path: Literal(await Path.home()),
            RDFS.label: Literal(
                f"home directory of {info['person_name']}",
                lang="en",
            ),
        },
    )


def describe_filesystem(info, disk_urn):
    return new(
        NT.Filesystem,
        {
            NT.byteSize: Literal(info["disk_info"]["Size"]),
            OWL.sameAs: disk_urn,
            RDFS.label: Literal(
                f"disk {info['disk_info']['VolumeName']}",
                lang="en",
            ),
        },
        subject=SWA[info["disk_uuid"]],
    )


def describe_machine(info, machine, filesystem, user):
    new(
        NT.ComputerMachine,
        {
            RDFS.label: Literal(
                f"{info['person_name']}'s {info['system_type']} computer",
                lang="en",
            ),
            NT.hosts: [
                new(
                    NT.PosixEnvironment,
                    {
                        NT.account: user,
                        NT.filesystem: filesystem,
                        NT.hostname: Literal(info["hostname"]),
                        RDFS.label: Literal(
                            f"POSIX environment on {info['hostname']}",
                            lang="en",
                        ),
                    },
                ),
                new(
                    NT.OperatingSystem,
                    {
                        NT.type: info["system_type"],
                        NT.version: Literal(info["system_version"]),
                        RDFS.label: Literal(
                            f"the {info['system_type']} operating system installed on {info['hostname']}",
                            lang="en",
                        ),
                    },
                ),
            ],
            NT.part: [
                new(
                    NT.CentralProcessingUnit,
                    {
                        NT.architecture: info["architecture"],
                        RDFS.label: Literal(
                            f"the CPU of {info['person_name']}'s {info['system_type']} computer",
                            lang="en",
                        ),
                    },
                ),
                new(
                    NT.RandomAccessMemory,
                    {
                        NT.byteSize: Literal(info["byte_size"]),
                        NT.gigabyteSize: Literal(info["gigabyte_size"]),
                        RDFS.label: Literal(
                            f"the RAM of {info['person_name']}'s {info['system_type']} computer",
                            lang="en",
                        ),
                    },
                ),
            ],
            NT.serialNumber: Literal(info["computer_serial"]),
        },
        subject=machine,
    )


def describe_creation_event(user, bubble, path, info):
    new(
        AS.Create,
        {
            AS.actor: user,
            AS.object: bubble,
            AS.published: info["now"],
            RDFS.label: Literal(
                f"creation of the bubble at {path}", lang="en"
            ),
        },
    )


def describe_steps(bubble, step, head, path):
    def quote(triples: list[_TripleType]) -> QuotedGraph:
        quoted = QuotedGraph(graphvar.get().store, fresh_iri())
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


def describe_root_surface(user, bubble, surface, path):
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
    )
