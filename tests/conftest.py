"""Global fixtures for VBAN tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from aiovban.enums import VoicemeeterType

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in Home Assistant."""
    yield

@pytest.fixture
def mock_voicemeeter_remote():
    """Mock a VoicemeeterRemote."""
    with patch("custom_components.vban.VoicemeeterRemote", autospec=True) as mock:
        remote = mock.return_value
        remote.device = MagicMock()
        remote.device.address = "1.1.1.1"
        remote.device.default_port = 6980
        remote.device._streams = {}
        remote.type = VoicemeeterType.POTATO
        remote.version = "3.0.4.2"
        remote.online = True
        remote.strips = []
        remote.buses = []
        remote.start = AsyncMock()
        remote.stop = AsyncMock()
        remote.send_command = AsyncMock()
        yield remote

@pytest.fixture
def mock_vban_client():
    """Mock an AsyncVBANClient."""
    with patch("custom_components.vban.AsyncVBANClient", autospec=True) as mock:
        client = mock.return_value
        client.listen = AsyncMock()
        client.register_device = AsyncMock()
        yield client

@pytest.fixture
def mock_setup_entry():
    """Mock setting up a config entry."""
    with patch("custom_components.vban.async_setup_entry", return_value=True) as mock:
        yield mock
