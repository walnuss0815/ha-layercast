"""One sensor per period: the recommended clothing."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LayercastConfigEntry
from .const import DOMAIN, SUBENTRY_PERIOD
from .coordinator import LayercastCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LayercastConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a sensor for every period subentry, and drop those of deleted periods."""
    periods = entry.get_subentries_of_type(SUBENTRY_PERIOD)
    registry = er.async_get(hass)
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registered.unique_id not in {sub.subentry_id for sub in periods}:
            registry.async_remove(registered.entity_id)
    # No config_subentry_id: all sensors share one device, and a device can belong to only
    # one subentry. That is why removed periods are cleaned up above.
    async_add_entities([LayercastSensor(entry, entry.runtime_data, sub) for sub in periods])


class LayercastSensor(CoordinatorEntity[LayercastCoordinator], SensorEntity):
    """The clothing recommended for one period."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:hanger"

    def __init__(
        self, entry: LayercastConfigEntry, coordinator: LayercastCoordinator, sub: ConfigSubentry
    ) -> None:
        super().__init__(coordinator)
        self._sub_id = sub.subentry_id
        self._attr_unique_id = sub.subentry_id
        self._attr_name = sub.title
        # One device per weather location, so area and name are set once.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _result(self) -> dict[str, Any]:
        return self.coordinator.data.get(self._sub_id, {})

    @property
    def native_value(self) -> str | None:
        return self._result.get("state")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._result.get("attributes", {})
