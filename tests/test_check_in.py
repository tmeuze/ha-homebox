"""Tests for the homebox.check_in service handler (mocked API, no HA instance)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from homeassistant.config_entries import ConfigEntryState  # noqa: E402

from custom_components.homebox import services  # noqa: E402
from custom_components.homebox.const import DOMAIN, SERVICE_CHECK_IN  # noqa: E402


def _setup(entries: list[dict]):
    api = MagicMock()
    api.async_get_hb_item_maintenance = AsyncMock(return_value=entries)
    api.async_create_hb_item_maintenance = AsyncMock(return_value="new")
    api.async_update_hb_maintenance = AsyncMock()
    api.async_get_hb_item_id_by_asset_id = AsyncMock(return_value="item-1")
    entry = MagicMock(state=ConfigEntryState.LOADED)
    entry.runtime_data.api = api

    hass = MagicMock()
    hass.config_entries.async_entries.return_value = [entry]
    handlers = {}
    hass.services.has_service.return_value = False
    hass.services.async_register.side_effect = (
        lambda domain, name, handler, *a, **k: handlers.__setitem__(name, handler)
    )
    services.async_setup_services(hass)
    return hass, api, handlers[SERVICE_CHECK_IN]


def _call(data: dict):
    call = MagicMock()
    call.data = {"name": "Check-in", "description": "", **data}
    return call


def test_creates_completed_entry_when_nothing_pending():
    hass, api, handler = _setup([])
    result = asyncio.run(handler(_call({"asset_id": "000-042"})))
    assert result["action"] == "created"
    kwargs = api.async_create_hb_item_maintenance.await_args.kwargs
    assert kwargs["completed_date"] and kwargs["name"] == "Check-in"
    api.async_update_hb_maintenance.assert_not_awaited()


def test_completes_pending_entries_with_matching_name():
    pending = {"id": "m1", "name": "Check-in", "scheduledDate": "2026-11-01T00:00:00Z"}
    done = {"id": "m2", "name": "Check-in", "completedDate": "2026-10-01T00:00:00Z"}
    other = {"id": "m3", "name": "Other"}
    hass, api, handler = _setup([pending, done, other])
    result = asyncio.run(handler(_call({"hb_item_id": "item-1"})))
    assert result == {"action": "completed", "count": 1, "hb_item_id": "item-1"}
    kwargs = api.async_update_hb_maintenance.await_args.kwargs
    assert kwargs["scheduled_date"] == "2026-11-01" and kwargs["completed_date"]
    api.async_create_hb_item_maintenance.assert_not_awaited()


def test_unknown_asset_id_raises():
    hass, api, handler = _setup([])
    api.async_get_hb_item_id_by_asset_id.return_value = None
    with pytest.raises(Exception):
        asyncio.run(handler(_call({"asset_id": "999-999"})))
