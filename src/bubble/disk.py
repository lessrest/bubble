"""Platform-independent disk information module.

This module provides a unified interface for getting disk information across
different platforms, with specialized handling for macOS using diskutil.
"""

import os
import platform
import psutil
import uuid
from typing import TypedDict


class DiskInfo(TypedDict):
    """
    Represents disk information in a platform-independent way.

    On macOS, this maps to a subset of diskutil info.
    On other platforms, this is derived from psutil and device info.

    Fields:
        Size: Total size of the volume in bytes
        VolumeName: User-visible name of the volume
        DiskUUID: Unique identifier for the disk
    """

    Size: int
    VolumeName: str
    DiskUUID: str


async def get_disk_info(
    mount_point: str = "/",
) -> DiskInfo:
    """Get disk information in a platform-independent way"""
    disk = psutil.disk_usage(mount_point)

    try:
        if platform.system() == "Darwin":
            # Use macOS diskutil to get proper disk info
            from bubble.macs import get_disk_info as get_mac_disk_info

            # Find the device for this mount point
            partition = next(
                p
                for p in psutil.disk_partitions()
                if p.mountpoint == mount_point
            )

            disk_info = await get_mac_disk_info(partition.device)
            return DiskInfo(
                Size=disk_info["Size"],
                VolumeName=disk_info["VolumeName"],
                DiskUUID=disk_info["DiskUUID"],
            )

        # For other platforms, generate a stable UUID based on device name
        partition = next(
            p
            for p in psutil.disk_partitions()
            if p.mountpoint == mount_point
        )
        device_uuid = str(
            uuid.uuid5(uuid.NAMESPACE_DNS, partition.device)
        )

    except Exception:
        # Fallback to using mount point for UUID generation
        device_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, mount_point))

    return DiskInfo(
        Size=disk.total,
        VolumeName=os.path.basename(mount_point) or "Root",
        DiskUUID=device_uuid,
    )
