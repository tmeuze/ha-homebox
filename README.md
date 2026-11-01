# HomeBox for Home Assistant (HACS)

A custom Home Assistant integration that connects to [HomeBox](https://github.com/sysadminsmedia/homebox), exposes inventory statistics, and supports linking Home Assistant devices to HomeBox items.

[![Open your Home Assistant instance and add this repository inside HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JeffreyDissmann&repository=ha-homebox&category=integration)
[![Open your Home Assistant instance and start setting up HomeBox](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=homebox)

## Features

- UI config flow (`host`, `username`, `password`, integration name, optional area)
- Polling-based HomeBox statistics sensors:
  - `homebox_total_items`
  - `homebox_total_locations`
  - `homebox_total_value`
  - `homebox_maintenance_due_today`
  - `homebox_maintenance_due_next_week`
- Device linking workflow (Home Assistant device <-> HomeBox item)
- HomeBox backlink field on linked items (links back to the HA device page)
- Home Assistant area -> HomeBox location synchronization
- Per-linked-device sensors:
  - Linked HomeBox item ID (diagnostic)
  - Estimated battery depletion date (diagnostic, requires a battery entity on the device)
- Automatic HomeBox maintenance entry sync from battery depletion forecasts
- Optional [Battery Notes](https://github.com/andrew-codechimp/HA-Battery-Notes) enrichment for maintenance entries
- Tag-driven discovery: HomeBox items tagged `HomeAssistant` are surfaced for linking in the HA UI
- Auto-unlink when the `HomeAssistant` tag is removed from a HomeBox item
- Automatic backlink restoration if a linked item's backlink field is cleared in HomeBox
- Service actions for triggering maintenance entries from automations (see below)
- Manual resync and stale backlink cleanup from integration options
- Bulk area import wizard to create and link multiple HomeBox items at once

## Requirements

- Home Assistant version `2024.1.0` or newer
- A reachable HomeBox instance
- HomeBox user credentials

Common HomeBox endpoints:

- default port: `7745`
- common Docker host mapping: `3100`

Examples:

- `http://192.168.1.20:7745`
- `http://homebox.local:3100`

## Installation (HACS)

Quick action:

- Click: `Add repository to HACS` button above.

1. Open HACS -> `Integrations`.
2. Open the menu -> `Custom repositories`.
3. Add `https://github.com/JeffreyDissmann/ha-homebox`.
4. Select category `Integration`.
5. Install `HomeBox`.
6. Restart Home Assistant.
7. Go to `Settings` -> `Devices & Services` -> `Add Integration` -> `HomeBox`.

## Configuration

During setup, provide:

- HomeBox host URL
- HomeBox username
- HomeBox password
- Integration display name (default: `HomeBox`)
- Optional Home Assistant area

## Entity Model

Primary HomeBox device:

- `homebox_total_items`
- `homebox_total_locations`
- `homebox_total_value`
- `homebox_maintenance_due_today`
- `homebox_maintenance_due_next_week`

Linked Home Assistant devices (one virtual device per link):

- Linked HomeBox item ID — diagnostic sensor exposing the HomeBox item ID
- Battery depletion date — diagnostic sensor with the estimated date the battery will run out (only present when a battery entity is detected on the HA device)

## Service Actions

Three actions are available under **Developer Tools → Actions** and in automations:

### `homebox.add_maintenance`

Creates a pending maintenance entry in HomeBox for the item linked to the given entity's device.

| Field | Required | Description |
| --- | --- | --- |
| `entity_id` | yes | Any entity whose device is linked to a HomeBox item |
| `name` | yes | Name of the maintenance entry |
| `description` | no | Optional details (default: empty) |
| `scheduled_date` | no | Due date (default: today) |

### `homebox.delete_maintenance`

Deletes all pending maintenance entries with the given name for the linked item.

| Field | Required | Description |
| --- | --- | --- |
| `entity_id` | yes | Any entity whose device is linked to a HomeBox item |
| `name` | yes | Name of the entries to delete |

### `homebox.clear_maintenance`

Deletes all pending maintenance entries for the linked item.

| Field | Required | Description |
| --- | --- | --- |
| `entity_id` | yes | Any entity whose device is linked to a HomeBox item |

### `homebox.check_in`

Records that an item has been checked, for example when an NFC tag on it is scanned. If the item has a pending maintenance entry with the given name, it is marked completed today; otherwise a new entry that is already completed today is created. Either way the item ends up with a completed entry dated today, so HomeBox's maintenance history shows when the item was last confirmed.

Identify the item with exactly one of `entity_id`, `asset_id` or `hb_item_id`. Items do not need to be linked to a HA device when you use `asset_id` or `hb_item_id`.

| Field | Required | Description |
| --- | --- | --- |
| `entity_id` | one of three | Any entity whose device is linked to a HomeBox item |
| `asset_id` | one of three | HomeBox asset ID as printed on the label, such as `000-042` |
| `hb_item_id` | one of three | HomeBox item (entity) UUID |
| `name` | no | Maintenance entry name to complete or create (default `Check-in`) |
| `description` | no | Note stored on a newly created entry |

The action returns a response (`action` of `created` or `completed`, `count`, `hb_item_id`) that automations can use.

**Example: tap an NFC tag to confirm an item is still there.** Register the tag in Home Assistant (Settings → Tags), then:

```yaml
automation:
  trigger:
    - trigger: tag
      tag_id: "<your-tag-id>"
  action:
    - action: homebox.check_in
      data:
        asset_id: "000-042"
```

**Example automation:** When a sensor reports a warning, log it as a maintenance task:

```yaml
automation:
  trigger:
    platform: state
    entity_id: binary_sensor.smoke_detector
    to: "on"
  action:
    service: homebox.add_maintenance
    data:
      entity_id: binary_sensor.smoke_detector
      name: "Smoke detector triggered — check device"
```

## Linking Workflow

From HomeBox integration options:

1. `Link HA device`: choose an unlinked tagged HomeBox item, then choose a HA device.
2. `Unlink HA device`: remove an existing mapping.
3. `Refresh HomeBox items`: re-scan tagged items and clean stale backlinks.

Tag-driven behavior:

- The integration manages/uses the HomeBox tag `HomeAssistant`.
- Tagged items that are not linked are surfaced for linking.

## Troubleshooting

- `Invalid authentication`:
  - verify username/password
  - verify URL and port
  - verify reverse proxy/auth setup if used
- `Cannot connect`:
  - verify network reachability from Home Assistant to HomeBox
  - verify protocol (`http` vs `https`)
- Link removed but still visible:
  - run `Refresh HomeBox items` in integration options
  - reload the integration

## Issues

Please report bugs and feature requests here:

- https://github.com/JeffreyDissmann/ha-homebox/issues

## Project Status

Active custom integration focused on HomeBox inventory stats + HA device linking.
