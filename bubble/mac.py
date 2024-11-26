import plistlib

from typing import Optional, TypedDict

import rich
import trio

from rich import inspect
from trio import run_process
from rich.table import Table


class DiskInfo(TypedDict):
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
    "List of disks"

    AllDisks: list[str]


async def disk_list() -> DiskList:
    cmd = ["diskutil", "list", "-plist"]
    output = await run_process(cmd, capture_stdout=True)
    return plistlib.loads(output.stdout)


async def get_disk_info(disk: str) -> DiskInfo:
    cmd = ["diskutil", "info", "-plist", disk]
    rich.print(cmd)
    output = await run_process(cmd, capture_stdout=True)
    return plistlib.loads(output.stdout)


async def all_disk_infos() -> dict[str, DiskInfo]:
    disks = await disk_list()
    return {disk: await get_disk_info(disk) for disk in disks["AllDisks"]}


async def computer_serial_number():
    cmd = ["system_profiler", "SPHardwareDataType", "-json"]
    output = await run_process(cmd, capture_stdout=True)

    import json

    data = json.loads(output.stdout)
    return data["SPHardwareDataType"][0]["serial_number"]


async def main():
    info = await all_disk_infos()
    rich.print(info)

    table = Table(title="Disk Information")
    table.add_column("UUID")
    table.add_column("Name")
    table.add_column("Mount")
    table.add_column("Parent")
    table.add_column("APFS ID")
    table.add_column("APFS Ref")

    for disk in info.values():
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
