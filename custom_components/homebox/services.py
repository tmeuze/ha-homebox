"""HomeBox HA service actions."""

from __future__ import annotations

import datetime
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .api import HomeBoxApiClient
from .const import (
    ATTR_ASSET_ID,
    ATTR_HB_ITEM_ID,
    ATTR_MAINTENANCE_DESCRIPTION,
    ATTR_MAINTENANCE_NAME,
    ATTR_MAINTENANCE_SCHEDULED_DATE,
    DEFAULT_CHECK_IN_NAME,
    DOMAIN,
    SERVICE_ADD_MAINTENANCE,
    SERVICE_CHECK_IN,
    SERVICE_CLEAR_MAINTENANCE,
    SERVICE_DELETE_MAINTENANCE,
)
from .linking import get_link_maps

ADD_MAINTENANCE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_MAINTENANCE_NAME): cv.string,
        vol.Optional(ATTR_MAINTENANCE_DESCRIPTION, default=""): cv.string,
        vol.Optional(ATTR_MAINTENANCE_SCHEDULED_DATE): cv.date,
    }
)

DELETE_MAINTENANCE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_MAINTENANCE_NAME): cv.string,
    }
)

CLEAR_MAINTENANCE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    }
)


CHECK_IN_SCHEMA = vol.All(
    cv.has_at_least_one_key(ATTR_ENTITY_ID, ATTR_HB_ITEM_ID, ATTR_ASSET_ID),
    vol.Schema(
        {
            vol.Exclusive(ATTR_ENTITY_ID, "target"): cv.entity_id,
            vol.Exclusive(ATTR_HB_ITEM_ID, "target"): cv.string,
            vol.Exclusive(ATTR_ASSET_ID, "target"): cv.string,
            vol.Optional(ATTR_MAINTENANCE_NAME, default=DEFAULT_CHECK_IN_NAME): cv.string,
            vol.Optional(ATTR_MAINTENANCE_DESCRIPTION, default=""): cv.string,
        }
    ),
)


def _is_entry_completed(entry: dict[str, Any]) -> bool:
    completed_date = entry.get("completedDate")
    return isinstance(completed_date, str) and bool(completed_date)


def _resolve_linked_item(
    hass: HomeAssistant, entity_id: str
) -> tuple[HomeBoxApiClient, str]:
    """Resolve entity_id to (api_client, hb_item_id) via the linking maps.

    Raises ServiceValidationError if the entity or its device is not linked.
    """
    entity_registry = er.async_get(hass)
    entity_entry = entity_registry.async_get(entity_id)
    if entity_entry is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entity_not_found",
            translation_placeholders={"entity_id": entity_id},
        )

    device_id = entity_entry.device_id
    if device_id is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entity_has_no_device",
            translation_placeholders={"entity_id": entity_id},
        )

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state != ConfigEntryState.LOADED:
            continue
        ha_device_to_hb_item, _ = get_link_maps(entry)
        hb_item_id = ha_device_to_hb_item.get(device_id)
        if hb_item_id:
            coordinator = entry.runtime_data
            return coordinator.api, hb_item_id

    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="device_not_linked",
        translation_placeholders={"entity_id": entity_id},
    )


def _first_loaded_api(hass: HomeAssistant) -> HomeBoxApiClient:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state == ConfigEntryState.LOADED:
            return entry.runtime_data.api
    raise ServiceValidationError(
        translation_domain=DOMAIN, translation_key="no_loaded_entry"
    )


async def _resolve_check_in_target(
    hass: HomeAssistant, data: dict[str, Any]
) -> tuple[HomeBoxApiClient, str]:
    """Resolve entity_id, hb_item_id or asset_id to (api_client, hb_item_id)."""
    if entity_id := data.get(ATTR_ENTITY_ID):
        return _resolve_linked_item(hass, entity_id)
    api = _first_loaded_api(hass)
    if hb_item_id := data.get(ATTR_HB_ITEM_ID):
        return api, hb_item_id.strip()
    asset_id = data[ATTR_ASSET_ID]
    hb_item_id = await api.async_get_hb_item_id_by_asset_id(asset_id)
    if hb_item_id is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="asset_not_found",
            translation_placeholders={"asset_id": asset_id},
        )
    return api, hb_item_id


def async_setup_services(hass: HomeAssistant) -> None:
    """Register HomeBox service actions (idempotent — safe to call per entry)."""

    if hass.services.has_service(DOMAIN, SERVICE_ADD_MAINTENANCE):
        return

    async def _handle_add_maintenance(call: ServiceCall) -> None:
        api, hb_item_id = _resolve_linked_item(hass, call.data[ATTR_ENTITY_ID])
        scheduled: datetime.date = call.data.get(
            ATTR_MAINTENANCE_SCHEDULED_DATE, dt_util.now().date()
        )
        await api.async_create_hb_item_maintenance(
            hb_item_id,
            name=call.data[ATTR_MAINTENANCE_NAME],
            description=call.data.get(ATTR_MAINTENANCE_DESCRIPTION, ""),
            scheduled_date=scheduled.isoformat(),
        )

    async def _handle_delete_maintenance(call: ServiceCall) -> None:
        api, hb_item_id = _resolve_linked_item(hass, call.data[ATTR_ENTITY_ID])
        target_name = call.data[ATTR_MAINTENANCE_NAME]
        entries = await api.async_get_hb_item_maintenance(hb_item_id, status="both")
        deleted = 0
        for entry in entries:
            if entry.get("name") == target_name and not _is_entry_completed(entry):
                await api.async_delete_hb_maintenance(entry["id"])
                deleted += 1
        if deleted == 0:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="maintenance_not_found",
                translation_placeholders={"name": target_name},
            )

    async def _handle_clear_maintenance(call: ServiceCall) -> None:
        api, hb_item_id = _resolve_linked_item(hass, call.data[ATTR_ENTITY_ID])
        entries = await api.async_get_hb_item_maintenance(hb_item_id, status="both")
        for entry in entries:
            if not _is_entry_completed(entry):
                await api.async_delete_hb_maintenance(entry["id"])

    async def _handle_check_in(call: ServiceCall) -> dict[str, Any]:
        """Record a check-in: complete matching pending entries, else log a done one."""
        api, hb_item_id = await _resolve_check_in_target(hass, call.data)
        name = call.data[ATTR_MAINTENANCE_NAME]
        description = call.data.get(ATTR_MAINTENANCE_DESCRIPTION, "")
        today = dt_util.now().date().isoformat()
        entries = await api.async_get_hb_item_maintenance(hb_item_id, status="both")
        pending = [
            entry
            for entry in entries
            if entry.get("name") == name and not _is_entry_completed(entry)
        ]
        if not pending:
            await api.async_create_hb_item_maintenance(
                hb_item_id,
                name=name,
                description=description,
                completed_date=today,
            )
            return {"action": "created", "count": 1, "hb_item_id": hb_item_id}
        for entry in pending:
            scheduled = str(entry.get("scheduledDate") or today)[:10]
            await api.async_update_hb_maintenance(
                entry["id"],
                name=name,
                description=entry.get("description") or description,
                scheduled_date=scheduled,
                completed_date=today,
                cost=str(entry.get("cost") or "0"),
            )
        return {"action": "completed", "count": len(pending), "hb_item_id": hb_item_id}

    hass.services.async_register(
        DOMAIN,
        SERVICE_CHECK_IN,
        _handle_check_in,
        CHECK_IN_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_MAINTENANCE,
        _handle_add_maintenance,
        ADD_MAINTENANCE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_MAINTENANCE,
        _handle_delete_maintenance,
        DELETE_MAINTENANCE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_MAINTENANCE,
        _handle_clear_maintenance,
        CLEAR_MAINTENANCE_SCHEMA,
    )


def async_unload_services(hass: HomeAssistant) -> None:
    """Unregister HomeBox services when no config entries remain."""
    if hass.config_entries.async_entries(DOMAIN):
        return
    hass.services.async_remove(DOMAIN, SERVICE_CHECK_IN)
    hass.services.async_remove(DOMAIN, SERVICE_ADD_MAINTENANCE)
    hass.services.async_remove(DOMAIN, SERVICE_DELETE_MAINTENANCE)
    hass.services.async_remove(DOMAIN, SERVICE_CLEAR_MAINTENANCE)
