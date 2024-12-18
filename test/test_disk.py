"""Tests for disk information functionality"""

import uuid

import pytest

from bubble.stat.disk import get_disk_info


async def test_get_disk_info_basic():
    """Test that get_disk_info returns valid data in the expected format"""
    info = await get_disk_info()

    # Check the returned type and structure
    assert isinstance(info, dict)
    assert all(key in info for key in ("Size", "VolumeName", "DiskUUID"))

    # Check value types
    assert isinstance(info["Size"], int)
    assert isinstance(info["VolumeName"], str)
    assert isinstance(info["DiskUUID"], str)

    # Basic sanity checks
    assert info["Size"] > 0
    assert len(info["DiskUUID"]) > 0


async def test_get_disk_info_stable_uuid():
    """Test that disk UUIDs are stable across multiple calls"""
    info1 = await get_disk_info()
    info2 = await get_disk_info()

    assert info1["DiskUUID"] == info2["DiskUUID"]

    # Verify it's a valid UUID
    uuid_obj = uuid.UUID(info1["DiskUUID"])
    assert isinstance(uuid_obj, uuid.UUID)


async def test_get_disk_info_custom_mount():
    """Test getting disk info for a custom mount point"""
    # Use /tmp as it should exist on all POSIX systems
    info = await get_disk_info("/tmp")

    assert isinstance(info, dict)
    assert info["Size"] > 0
    assert "tmp" in info["VolumeName"].lower()


@pytest.mark.darwin
async def test_get_disk_info_macos():
    """Test macOS-specific disk info features"""
    info = await get_disk_info()

    # On macOS, we should get the actual disk UUID from diskutil
    uuid_obj = uuid.UUID(info["DiskUUID"])
    assert isinstance(uuid_obj, uuid.UUID)

    # The volume name should be meaningful on macOS
    assert len(info["VolumeName"]) > 0
    assert info["VolumeName"] != "Root"
