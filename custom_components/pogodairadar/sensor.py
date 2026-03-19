"""Sensors: text forecast, warnings, last update."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PogodaIRadarCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PogodaIRadarCoordinator = hass.data[DOMAIN][entry.entry_id]
    safe = coordinator.slug.replace("/", "_").lower()
    uid = f"{entry.entry_id}_{safe}"
    dev = DeviceInfo(
        entry_type=DeviceEntryType.SERVICE,
        identifiers={(DOMAIN, entry.entry_id)},
        name=coordinator.data.get("location_name", "PogodaiRadar"),
        manufacturer="kaktuz",
        configuration_url=coordinator.url,
    )
    async_add_entities(
        [
            PogodaTextForecastSensor(coordinator, entry, uid, dev),
            PogodaWarningsSensor(coordinator, entry, uid, dev),
            PogodaLastUpdateSensor(coordinator, entry, uid, dev),
        ]
    )


class _PogodaSensor(CoordinatorEntity[PogodaIRadarCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PogodaIRadarCoordinator,
        entry: ConfigEntry,
        uid_base: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._uid_base = uid_base
        self._attr_device_info = device_info


class PogodaTextForecastSensor(_PogodaSensor):
    """Editorial text forecast."""

    _attr_icon = "mdi:calendar-text"

    @property
    def unique_id(self) -> str:
        return f"{self._uid_base}_text_forecast"

    @property
    def native_value(self) -> str | None:
        text = (self.coordinator.data.get("tomorrow_text") or "").strip()
        return text or None

    @property
    def name(self) -> str:
        return "Текстовий прогноз погоди"


class PogodaWarningsSensor(_PogodaSensor):
    """Weather warnings (v9 + warning map levels)."""

    _attr_icon = "mdi:alert"

    @property
    def unique_id(self) -> str:
        return f"{self._uid_base}_warnings"

    @property
    def native_value(self) -> str | None:
        full = self.coordinator.data.get("warnings_summary") or ""
        return full[:250] + ("…" if len(full) > 250 else "") or None

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        full = self.coordinator.data.get("warnings_summary") or ""
        return {"full_text": full} if len(full) > 250 else {}

    @property
    def name(self) -> str:
        return "Метеопопередження"


class PogodaLastUpdateSensor(_PogodaSensor):
    """Date and time of last successful update."""

    _attr_icon = "mdi:update"

    @property
    def unique_id(self) -> str:
        return f"{self._uid_base}_last_update"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("last_update_local")

    @property
    def name(self) -> str:
        return "Останнє оновлення"
