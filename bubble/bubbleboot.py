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
from bubble.graphvar import bind_prefixes, langstr, quote, using_graph
from bubble.ns import AS, NT, SWA, UUID
from bubble.rdfutil import new
from bubble.sysinfo import gather_system_info


from rdflib import OWL, RDFS, Graph, Literal
from rdflib.graph import _SubjectType
from trio import Path


import getpass


async def describe_new_bubble(path: Path) -> _SubjectType:
    info = await gather_system_info()
    return await construct_bubble_graph(path, info)


async def construct_bubble_graph(path, info):
    surface = fresh_iri()
    step = fresh_iri()
    head = fresh_iri()

    with using_graph(Graph()) as g:
        bind_prefixes()

        machine = SWA[info["machine_id"]]

        filesystem = describe_filesystem(info)

        home_dir = await describe_home_directory(info, filesystem)
        bubble = describe_bubble(step, info)
        user = describe_user_account(info, home_dir)

        describe_repository(path, filesystem, home_dir, bubble)
        describe_machine(info, machine, filesystem, user)
        describe_creation_event(user, bubble, path, info)
        describe_steps(bubble, step, head, path)
        describe_surface_addition(user, bubble, surface, path)

        g.serialize(destination=path / "root.n3", format="n3")

        return bubble


def describe_user_account(info, home_dir):
    return new(
        NT.Account,
        {
            NT.gid: info["user_info"].pw_gid,
            NT.homeDirectory: home_dir,
            NT.owner: new(
                AS.Person,
                {NT.name: info["person_name"]},
            ),
            NT.uid: info["user_info"].pw_uid,
            NT.username: getpass.getuser(),
            RDFS.label: langstr(
                f"user account for {info['person_name']}"
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
                    NT.path: path,
                    RDFS.label: langstr(
                        f"worktree directory at {path}",
                    ),
                },
            ),
            RDFS.label: langstr(
                f"bubble repository at {path}",
            ),
        },
    )


def describe_bubble(step, info):
    return new(
        NT.Bubble,
        {
            RDFS.label: langstr(
                f"a bubble for {info['person_name']}",
            ),
            NT.head: step,
        },
    )


async def describe_home_directory(info, filesystem):
    return new(
        NT.Directory,
        {
            NT.filesystem: filesystem,
            NT.path: await Path.home(),
            RDFS.label: langstr(
                f"home directory of {info['person_name']}",
            ),
        },
    )


def describe_filesystem(info):
    return new(
        NT.Filesystem,
        {
            NT.byteSize: Literal(info["disk_info"]["Size"]),
            OWL.sameAs: UUID[info["disk_uuid"]],
            RDFS.label: langstr(
                f"disk {info['disk_info']['VolumeName']}",
            ),
        },
    )


def describe_machine(info, machine, filesystem, user):
    new(
        NT.ComputerMachine,
        {
            RDFS.label: langstr(
                f"{info['person_name']}'s {info['system_type']} computer",
            ),
            NT.hosts: [
                describe_posixenv(info, filesystem, user),
                describe_os(info),
            ],
            NT.part: [
                describe_cpu(info),
                describe_ram(info),
            ],
            NT.serialNumber: info["computer_serial"],
        },
        subject=machine,
    )


def describe_ram(info):
    return new(
        NT.RandomAccessMemory,
        {
            NT.byteSize: Literal(info["byte_size"]),
            NT.gigabyteSize: info["gigabyte_size"],
            RDFS.label: langstr(
                f"the RAM of {info['person_name']}'s {info['system_type']} computer",
            ),
        },
    )


def describe_cpu(info):
    return new(
        NT.CentralProcessingUnit,
        {
            NT.architecture: info["architecture"],
            RDFS.label: langstr(
                f"the CPU of {info['person_name']}'s {info['system_type']} computer",
            ),
        },
    )


def describe_os(info):
    return new(
        NT.OperatingSystem,
        {
            NT.type: info["system_type"],
            NT.version: info["system_version"],
            RDFS.label: langstr(
                f"the {info['system_type']} operating system installed on {info['hostname']}",
            ),
        },
    )


def describe_posixenv(info, filesystem, user):
    return new(
        NT.PosixEnvironment,
        {
            NT.account: user,
            NT.filesystem: filesystem,
            NT.hostname: info["hostname"],
            RDFS.label: langstr(
                f"POSIX environment on {info['hostname']}",
            ),
        },
    )


def describe_creation_event(user, bubble, path, info):
    new(
        AS.Create,
        {
            AS.actor: user,
            AS.object: bubble,
            AS.published: info["now"],
            RDFS.label: langstr(
                f"creation of the bubble at {path}",
            ),
        },
    )


def describe_steps(bubble, step, head, path):
    describe_initial_step(bubble, step, path)
    describe_next_step(bubble, step, head, path)


def describe_next_step(bubble, step, head, path):
    new(
        NT.Step,
        {
            NT.supposes: quote([(bubble, NT.head, head)]),
            NT.succeeds: step,
            RDFS.label: langstr(
                f"the second step of the bubble at {path}",
            ),
        },
        subject=head,
    )


def describe_initial_step(bubble, step, path):
    new(
        NT.Step,
        {
            NT.supposes: quote([(bubble, NT.head, step)]),
            RDFS.label: langstr(
                f"the first step of the bubble at {path}",
            ),
        },
        subject=step,
    )


def describe_surface_addition(user, bubble, surface, path):
    new(
        AS.Add,
        {
            AS.actor: user,
            AS.object: describe_root_surface(bubble, surface, path),
            AS.target: bubble,
            RDFS.label: langstr(
                f"addition of the root surface to the bubble at {path}",
            ),
        },
    )


def describe_root_surface(bubble, surface, path):
    return new(
        NT.Surface,
        {
            NT.partOf: bubble,
            RDFS.label: langstr(
                f"the root surface of the bubble at {path}",
            ),
        },
        subject=surface,
    )
