from datetime import UTC, datetime
import os
import platform
import pwd
import socket
import psutil
from rdflib import XSD, Literal
import uuid

from swash.prfx import NT
from bubble.stat.disk import DiskInfo, get_disk_info

from typing import TypedDict
from pwd import struct_passwd
from rdflib import URIRef


class SystemInfo(TypedDict):
    computer_serial: str
    machine_id: str
    now: Literal
    hostname: str
    architecture: URIRef
    system_type: URIRef
    system_version: str
    byte_size: int
    gigabyte_size: float
    user_info: struct_passwd
    person_name: str
    disk_info: DiskInfo
    disk_uuid: str


async def get_computer_serial() -> str:
    """Get computer serial number in a platform-independent way"""
    try:
        if platform.system() == "Darwin":
            from bubble.stat.macs import computer_serial_number

            return await computer_serial_number()
        else:
            # Try to get DMI info on Linux
            try:
                with open("/sys/class/dmi/id/product_serial") as f:
                    return f.read().strip()
            except (FileNotFoundError, PermissionError):
                return str(
                    uuid.getnode()
                )  # Fallback to MAC address-based ID
    except Exception:
        return str(uuid.getnode())  # Final fallback


async def get_machine_id() -> str:
    """Get a stable machine identifier in a platform-independent way"""
    # Try different methods in order of preference
    try:
        # Try reading machine-id on Linux/systemd systems
        if os.path.exists("/etc/machine-id"):
            with open("/etc/machine-id") as f:
                return f.read().strip()

        # Try reading Hardware UUID on macOS
        if platform.system() == "Darwin":
            from bubble.stat.macs import get_hardware_uuid

            try:
                return await get_hardware_uuid()
            except Exception:
                pass

        # Fallback: Use a combination of hostname and MAC address
        # This should be stable across reboots
        hostname = socket.gethostname()
        mac = uuid.getnode()
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{hostname}:{mac}"))

    except Exception:
        # Final fallback: random UUID
        # Note: This will change across reboots
        return str(uuid.uuid4())


async def gather_system_info() -> SystemInfo:
    computer_serial = await get_computer_serial()
    machine_id = await get_machine_id()

    now = get_timestamp()
    hostname, arch, system = get_system_info()
    architecture = resolve_architecture(arch)
    system_type, system_version = resolve_system(system)
    byte_size, gigabyte_size = get_memory_size()
    user_info, person_name = get_user_info()

    # Use platform-independent disk info gathering
    disk_info = await get_disk_info()
    disk_uuid = disk_info["DiskUUID"]

    return SystemInfo(
        computer_serial=computer_serial,
        machine_id=machine_id,
        now=now,
        hostname=hostname,
        architecture=architecture,
        system_type=system_type,
        system_version=system_version,
        byte_size=byte_size,
        gigabyte_size=gigabyte_size,
        user_info=user_info,
        person_name=person_name,
        disk_info=disk_info,
        disk_uuid=disk_uuid,
    )


def get_timestamp():
    return Literal(datetime.now(UTC), datatype=XSD.dateTime)


def get_system_info():
    hostname = socket.gethostname()
    arch = platform.machine()
    system = platform.system()
    return hostname, arch, system


def get_memory_size():
    memory_info = psutil.virtual_memory()
    byte_size = memory_info.total
    gigabyte_size = round(byte_size / 1024 / 1024 / 1024, 2)
    return byte_size, gigabyte_size


def get_user_info():
    user_info = pwd.getpwuid(os.getuid())
    person_name = user_info.pw_gecos
    return user_info, person_name


def resolve_system(system):
    """Resolve system type and version in a platform-independent way"""
    match system:
        case "Darwin":
            system_type = NT.macOSEnvironment
            system_version = platform.mac_ver()[0]
        case "Linux":
            system_type = NT.LinuxEnvironment
            system_version = platform.release()
        case "Windows":
            system_type = NT.WindowsEnvironment
            system_version = platform.release()
        case _:
            raise ValueError(f"Unknown operating system: {system}")
    return system_type, system_version


def resolve_architecture(arch):
    match arch:
        case "x86_64":
            architecture = NT.AMD64
        case "arm64" | "aarch64":
            architecture = NT.ARM64
        case _:
            raise ValueError(f"Unknown architecture: {arch}")
    return architecture
