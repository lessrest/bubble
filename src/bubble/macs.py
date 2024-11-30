# This module provides utilities for querying disk information on macOS systems
# using the `diskutil` command line tool. It wraps the plist output in typed
# structures for better code safety and IDE support.

import plistlib

from typing import TypedDict

import rich
import trio

from trio import run_process
from rich.table import Table


class DiskInfo(TypedDict):
    """
    Represents detailed information about a disk volume.
    Maps to the plist output of `diskutil info -plist`.

    Note: APFS (Apple File System) volumes have additional fields for container
    references and UUIDs that traditional HFS+ volumes lack. An APFS container
    is a pool of storage that can contain multiple volumes sharing the same
    physical space. The container reference identifies which APFS container
    a volume belongs to.

    Fields:
        Size: Total size of the volume in bytes
        VolumeName: User-visible name of the volume
        VolumeUUID: Unique identifier for this volume
        DeviceIdentifier: System identifier like 'disk0s2'
        DeviceNode: Device path like '/dev/disk0s2'
        Content: Type of content (e.g. 'Apple_APFS', 'Apple_HFS')
        MountPoint: Path where volume is mounted, if mounted
        ParentWholeDisk: Identifier of the parent physical disk
        DiskUUID: Unique identifier for the physical disk
        Internal: Whether disk is internal to the computer
        Removable: Whether disk can be removed (e.g. USB drive)
        Encryption: Whether volume is encrypted
        MediaName: Name of the physical media
        SolidState: Whether disk is an SSD vs spinning disk
        WholeDisk: Whether this represents an entire physical disk
        APFSContainerReference: Reference to APFS container (APFS only)
        APFSContainerUUID: UUID of APFS container (APFS only)
    """

    Size: int
    VolumeName: str
    VolumeUUID: str
    DeviceIdentifier: str
    DeviceNode: str
    Content: str
    MountPoint: str
    ParentWholeDisk: str
    DiskUUID: str
    Internal: bool
    Removable: bool
    Encryption: bool
    MediaName: str
    SolidState: bool
    WholeDisk: bool
    APFSContainerReference: str
    APFSContainerUUID: str


class DiskList(TypedDict):
    "List of disks returned by diskutil list command"

    AllDisks: list[str]


async def disk_list() -> DiskList:
    """Get a list of all disks on the system"""
    cmd = ["diskutil", "list", "-plist"]
    output = await run_process(cmd, capture_stdout=True)
    return plistlib.loads(output.stdout)


async def get_disk_info(disk: str) -> DiskInfo:
    """Get detailed information about a specific disk using diskutil"""
    cmd = ["diskutil", "info", "-plist", disk]
    output = await run_process(cmd, capture_stdout=True)
    return plistlib.loads(output.stdout)


async def computer_serial_number():
    """
    Get the hardware serial number of this Mac using system_profiler.
    Useful for uniquely identifying the machine.
    """
    cmd = ["system_profiler", "SPHardwareDataType", "-json"]
    output = await run_process(cmd, capture_stdout=True)

    import json

    data = json.loads(output.stdout)
    return data["SPHardwareDataType"][0]["serial_number"]


async def get_hardware_uuid() -> str:
    """Get the hardware UUID of this Mac using system_profiler"""
    cmd = ["system_profiler", "SPHardwareDataType", "-json"]
    output = await run_process(cmd, capture_stdout=True)

    import json

    data = json.loads(output.stdout)
    return data["SPHardwareDataType"][0]["platform_UUID"]


async def main() -> None:
    """
    Display a rich table showing key information about all disks.
    Particularly useful for understanding APFS volume relationships.
    """
    info = []
    for disk in (await disk_list())["AllDisks"]:
        info.append(await get_disk_info(disk))

    rich.print(info)

    table = Table(title="Disk Information")
    table.add_column("UUID")
    table.add_column("Name")
    table.add_column("Mount")
    table.add_column("Parent")
    table.add_column("APFS ID")
    table.add_column("APFS Ref")

    for disk in info:
        table.add_row(
            str(disk.get("DiskUUID")),
            str(disk.get("VolumeName")),
            str(disk.get("MountPoint")),
            str(disk.get("ParentWholeDisk")),
            str(disk.get("APFSContainerUUID")),
            str(disk.get("APFSContainerReference")),
        )

    rich.print(table)


if __name__ == "__main__":
    trio.run(main)
