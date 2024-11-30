import platform
import pytest

from bubble.macs import (
    disk_list,
    get_disk_info,
    computer_serial_number,
)


@pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="macOS disk tests only run on Darwin",
)
async def test_disk_list():
    """Test retrieving list of disks"""
    disks = await disk_list()

    assert isinstance(disks, dict)
    assert "AllDisks" in disks
    assert isinstance(disks["AllDisks"], list)
    assert len(disks["AllDisks"]) > 0
    assert all(isinstance(d, str) for d in disks["AllDisks"])


@pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="macOS disk tests only run on Darwin",
)
async def test_get_disk_info():
    """Test retrieving info for a specific disk"""
    # Get first disk from list
    disks = await disk_list()
    disk_id = disks["AllDisks"][0]

    info = await get_disk_info(disk_id)

    assert isinstance(info, dict)
    # Check required fields are present with correct types
    assert isinstance(info.get("Size"), int)
    assert isinstance(info["DeviceIdentifier"], str)
    assert isinstance(info["DeviceNode"], str)
    assert isinstance(info["Content"], str)
    assert isinstance(info["Internal"], bool)


@pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="macOS disk tests only run on Darwin",
)
@pytest.mark.trio
async def test_computer_serial_number():
    """Test retrieving computer serial number"""
    serial = await computer_serial_number()

    assert isinstance(serial, str)
    assert len(serial) > 0
