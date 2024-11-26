import pytest
from typing import TypedDict

from bubble.macs import (
    DiskInfo,
    DiskList,
    disk_list,
    get_disk_info,
    all_disk_infos,
    computer_serial_number,
)


@pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="macOS disk tests only run on Darwin"
)
@pytest.mark.trio
async def test_disk_list():
    """Test retrieving list of disks"""
    disks = await disk_list()
    
    assert isinstance(disks, DiskList)
    assert isinstance(disks["AllDisks"], list)
    assert len(disks["AllDisks"]) > 0
    assert all(isinstance(d, str) for d in disks["AllDisks"])


@pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="macOS disk tests only run on Darwin"
)
@pytest.mark.trio
async def test_get_disk_info():
    """Test retrieving info for a specific disk"""
    # Get first disk from list
    disks = await disk_list()
    disk_id = disks["AllDisks"][0]
    
    info = await get_disk_info(disk_id)
    
    assert isinstance(info, DiskInfo)
    assert isinstance(info["Size"], int)
    assert isinstance(info["DeviceIdentifier"], str)
    assert isinstance(info["DeviceNode"], str)
    assert isinstance(info["Content"], str)
    assert isinstance(info["Internal"], bool)


@pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="macOS disk tests only run on Darwin"
)
@pytest.mark.trio
async def test_all_disk_infos():
    """Test retrieving info for all disks"""
    all_info = await all_disk_infos()
    
    assert isinstance(all_info, dict)
    assert len(all_info) > 0
    
    # Check first disk info
    first_disk = next(iter(all_info.values()))
    assert isinstance(first_disk, DiskInfo)
    assert isinstance(first_disk["Size"], int)
    assert isinstance(first_disk["DeviceIdentifier"], str)


@pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="macOS disk tests only run on Darwin"
)
@pytest.mark.trio
async def test_computer_serial_number():
    """Test retrieving computer serial number"""
    serial = await computer_serial_number()
    
    assert isinstance(serial, str)
    assert len(serial) > 0
