from datetime import UTC, datetime
import os
import platform
import pwd
import socket
import psutil
from rdflib import XSD, Literal

from bubble.macsysinfo import computer_serial_number, get_disk_info
from bubble.ns import NT
from bubble.gensym import mintvar

from typing import TypedDict
from pwd import struct_passwd
from rdflib import URIRef

from bubble.macsysinfo import DiskInfo


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


async def gather_system_info() -> SystemInfo:
    computer_serial = await computer_serial_number()
    machine_id = mintvar.get().machine_id()

    now = get_timestamp()
    hostname, arch, system = get_system_info()
    architecture = resolve_architecture(arch)
    system_type, system_version = resolve_system(system)
    byte_size, gigabyte_size = get_memory_size()
    user_info, person_name = get_user_info()

    disk_info = await get_disk_info("/System/Volumes/Data")
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
    match system:
        case "Darwin":
            system_type = NT.macOSEnvironment
            system_version = platform.mac_ver()[0]

        case _:
            raise ValueError(f"Unknown operating system: {system}")
    return system_type, system_version


def resolve_architecture(arch):
    match arch:
        case "x86_64":
            architecture = NT.AMD64
        case "arm64":
            architecture = NT.ARM64
        case _:
            raise ValueError(f"Unknown architecture: {arch}")
    return architecture
