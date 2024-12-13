"""Bubble initialization module.

This module handles the creation of new bubbles, which are versioned RDF graphs.
It sets up the initial graph structure with system information, user details,
and basic bubble metadata using the PROV ontology for provenance tracking.
"""

from datetime import datetime, timezone
import os
import pwd
import getpass

from trio import Path
from rdflib import OWL, RDFS, Graph, URIRef, Literal, RDF

from swash import vars
from swash.prfx import NT, SWA, PROV, UUID
from swash.util import new
from bubble.stat.stat import SystemInfo, gather_system_info


async def describe_new_bubble(path: Path, bubble: URIRef) -> Graph:
    """Create a new bubble with a unique IRI."""
    info = await gather_system_info()
    graph = await construct_bubble_graph(path, info, bubble)
    return graph


async def construct_bubble_graph(
    path, info: SystemInfo, bubble: URIRef
) -> Graph:
    with vars.graph.bind(
        Graph(identifier=bubble, base=URIRef(str(bubble)))
    ) as g:
        vars.bind_prefixes(g)

        machine = SWA[info["machine_id"]]

        # Describe filesystem
        filesystem = new(
            NT.Filesystem,
            {
                NT.byteSize: Literal(info["disk_info"]["Size"]),
                OWL.sameAs: UUID[info["disk_uuid"]],
                RDFS.label: info["disk_info"]["VolumeName"],
            },
        )

        # Describe home directory
        home_dir = new(
            NT.Directory,
            {
                NT.filesystem: filesystem,
                NT.path: await Path.home(),
            },
        )

        # Describe user account
        user = new(
            NT.Account,
            {
                NT.gid: info["user_info"].pw_gid,
                NT.homeDirectory: home_dir,
                NT.uid: info["user_info"].pw_uid,
                NT.username: getpass.getuser(),
            },
        )

        # Describe repository
        repo = new(
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
                PROV.generatedAtTime: datetime.now(timezone.utc),
            },
        )

        # Describe machine and its components
        new(
            NT.ComputerMachine,
            {
                NT.hosts: [
                    # PosixEnvironment
                    new(
                        NT.PosixEnvironment,
                        {
                            NT.account: user,
                            NT.filesystem: filesystem,
                            NT.hostname: info["hostname"],
                        },
                    ),
                    # # OperatingSystem
                    # new(
                    #     NT.OperatingSystem,
                    #     {
                    #         NT.type: info["system_type"],
                    #         NT.version: info["system_version"],
                    #     },
                    # ),
                ],
                NT.part: [
                    # CPU
                    new(
                        NT.CentralProcessingUnit,
                        {
                            NT.architecture: info["architecture"],
                        },
                    ),
                    # RAM
                    new(
                        NT.RandomAccessMemory,
                        {
                            NT.byteSize: Literal(info["byte_size"]),
                            NT.gigabyteSize: info["gigabyte_size"],
                        },
                    ),
                ],
                NT.serialNumber: info["computer_serial"],
            },
            subject=machine,
        )

        # Describe creation event
        new(
            NT.Create,
            {
                PROV.wasAssociatedWith: user,
                PROV.used: machine,
                PROV.generated: repo,
                PROV.startedAtTime: info["now"],
            },
        )

        return g


def get_user_info():
    """Get user info in a platform-independent way"""
    user_info = pwd.getpwuid(os.getuid())
    # Handle cases where GECOS field might be empty
    person_name = user_info.pw_gecos or user_info.pw_name
    return user_info, person_name
