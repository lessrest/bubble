"""Test configuration for bubble"""

import platform

import pytest


def pytest_configure(config):
    """Configure custom markers for different platforms"""
    config.addinivalue_line(
        "markers",
        "darwin: mark test to run only on macOS",
    )
    config.addinivalue_line(
        "markers",
        "linux: mark test to run only on Linux",
    )


def pytest_runtest_setup(item):
    """Skip tests based on platform markers"""
    for marker in item.iter_markers():
        if marker.name == "darwin" and platform.system() != "Darwin":
            pytest.skip("Test requires macOS")
        elif marker.name == "linux" and platform.system() != "Linux":
            pytest.skip("Test requires Linux")
