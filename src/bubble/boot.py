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

from bubble.mint import fresh_iri
from bubble import vars
from bubble.prfx import AS, NT, SWA, UUID
from bubble.util import new
from bubble.stat import gather_system_info


from rdflib import OWL, RDFS, Graph, Literal
from trio import Path


import getpass
import os
import pwd


async def describe_new_bubble(path: Path) -> Graph:
    info = await gather_system_info()
    return await construct_bubble_graph(path, info)


async def construct_bubble_graph(path, info):
    bubble = fresh_iri()
    with vars.graph.bind(Graph(identifier=bubble)) as g:
        surface = fresh_iri()
        step = fresh_iri()
        head = fresh_iri()

        vars.bind_prefixes()

        machine = SWA[info["machine_id"]]

        filesystem = describe_filesystem(info)

        home_dir = await describe_home_directory(info, filesystem)
        user = describe_user_account(info, home_dir)

        describe_bubble(bubble, step, info)
        describe_repository(path, filesystem, home_dir, bubble)
        describe_machine(info, machine, filesystem, user)
        describe_creation_event(user, bubble, path, info)
        describe_steps(bubble, step, head, path)
        describe_surface_addition(user, bubble, surface, path)

        return g


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
                },
            ),
        },
    )


def describe_bubble(bubble, step, info):
    local_part = str(bubble).split("/")[
        -1
    ]  # Get the last part after the slash
    return new(
        NT.Bubble,
        {
            NT.head: step,
            NT.emailAddress: f"{local_part}@swa.sh",
        },
        subject=bubble,
    )


async def describe_home_directory(info, filesystem):
    return new(
        NT.Directory,
        {
            NT.filesystem: filesystem,
            NT.path: await Path.home(),
        },
    )


def describe_filesystem(info):
    """Describe filesystem in a platform-independent way"""
    return new(
        NT.Filesystem,
        {
            NT.byteSize: Literal(info["disk_info"]["Size"]),
            OWL.sameAs: UUID[info["disk_uuid"]],
            RDFS.label: info["disk_info"]["VolumeName"],
        },
    )


def describe_machine(info, machine, filesystem, user):
    new(
        NT.ComputerMachine,
        {
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
        },
    )


def describe_cpu(info):
    return new(
        NT.CentralProcessingUnit,
        {
            NT.architecture: info["architecture"],
        },
    )


def describe_os(info):
    return new(
        NT.OperatingSystem,
        {
            NT.type: info["system_type"],
            NT.version: info["system_version"],
        },
    )


def describe_posixenv(info, filesystem, user):
    return new(
        NT.PosixEnvironment,
        {
            NT.account: user,
            NT.filesystem: filesystem,
            NT.hostname: info["hostname"],
        },
    )


def describe_creation_event(user, bubble, path, info):
    new(
        AS.Create,
        {
            AS.actor: user,
            AS.object: bubble,
            AS.published: info["now"],
        },
    )


def describe_steps(bubble, step, head, path):
    describe_initial_step(bubble, step, path)
    describe_next_step(bubble, step, head, path)


def describe_next_step(bubble, step, head, path):
    new(
        NT.Step,
        {
            NT.supposes: vars.quote([(bubble, NT.head, head)]),
            NT.succeeds: step,
        },
        subject=head,
    )


def describe_initial_step(bubble, step, path):
    new(
        NT.Step,
        {
            NT.supposes: vars.quote([(bubble, NT.head, step)]),
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
        },
    )


def describe_root_surface(bubble, surface, path):
    return new(
        NT.Surface,
        {
            NT.partOf: bubble,
        },
        subject=surface,
    )


def get_user_info():
    """Get user info in a platform-independent way"""
    user_info = pwd.getpwuid(os.getuid())
    # Handle cases where GECOS field might be empty
    person_name = user_info.pw_gecos or user_info.pw_name
    return user_info, person_name
