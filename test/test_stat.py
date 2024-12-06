import pytest

from bubble.stat.stat import gather_system_info
from swash.prfx import NT


@pytest.mark.darwin
async def test_gather_system_info_darwin():
    """Test system info gathering on macOS"""
    info = await gather_system_info()

    assert isinstance(info["computer_serial"], str)
    assert len(info["computer_serial"]) > 0
    assert isinstance(info["machine_id"], str)
    assert len(info["machine_id"]) > 0
    assert info["hostname"]
    assert info["architecture"] in (NT.AMD64, NT.ARM64)
    assert info["system_type"] == NT.macOSEnvironment
    assert isinstance(info["system_version"], str)
    assert len(info["system_version"].split(".")) >= 2
    assert info["byte_size"] > 0
    assert info["gigabyte_size"] > 0
    assert isinstance(info["gigabyte_size"], float)
    assert info["person_name"]
    assert info["user_info"].pw_name
    assert isinstance(info["disk_info"], dict)
    assert info["disk_uuid"] == info["disk_info"]["DiskUUID"]


@pytest.mark.linux
async def test_gather_system_info_linux():
    """Test system info gathering on Linux"""
    info = await gather_system_info()

    assert isinstance(info["computer_serial"], str)
    assert len(info["computer_serial"]) > 0
    assert isinstance(info["machine_id"], str)
    assert len(info["machine_id"]) > 0
    assert info["hostname"]
    assert info["architecture"] in (NT.AMD64, NT.ARM64)
    assert info["system_type"] == NT.LinuxEnvironment
    assert isinstance(info["system_version"], str)
    assert info["byte_size"] > 0
    assert info["gigabyte_size"] > 0
    assert isinstance(info["gigabyte_size"], float)
    assert info["person_name"]
    assert info["user_info"].pw_name
    assert isinstance(info["disk_info"], dict)
    assert info["disk_uuid"] == info["disk_info"]["DiskUUID"]
