"""Weather entity: current, hourly, and daily forecasts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.weather import Forecast, WeatherEntity, WeatherEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength, UnitOfPressure, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import (
    PogodaIRadarCoordinator,
    _probability_pct,
    _temp_c,
    _visibility_meters_from_shortcast_hour,
    _wind_deg,
    _wind_ms,
    observation_to_condition,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PogodaIRadarCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PogodaIRadarWeather(coordinator, entry)])


def _ms_to_kmh(ms: float | None) -> float | None:
    if ms is None:
        return None
    return round(ms * 3.6, 1)


class PogodaIRadarWeather(CoordinatorEntity[PogodaIRadarCoordinator], WeatherEntity):
    """Weather from pogodairadar (shortcast + blending forecast)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_visibility_unit = UnitOfLength.METERS
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(self, coordinator: PogodaIRadarCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        safe = coordinator.slug.replace("/", "_").lower()
        self._attr_unique_id = f"{entry.entry_id}_{safe}_weather"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.data.get("location_name", "PogodaiRadar"),
            manufacturer="kaktuz",
            configuration_url=coordinator.url,
        )

    @property
    def native_temperature(self) -> float | None:
        return _temp_c((self.coordinator.data.get("current") or {}).get("air_temperature"))

    @property
    def native_apparent_temperature(self) -> float | None:
        return _temp_c((self.coordinator.data.get("current") or {}).get("apparent_temperature"))

    @property
    def native_dew_point(self) -> float | None:
        return _temp_c((self.coordinator.data.get("current") or {}).get("dew_point"))

    @property
    def native_pressure(self) -> float | None:
        ap = (self.coordinator.data.get("current") or {}).get("air_pressure") or {}
        try:
            return float(ap.get("hpa", 0))
        except (TypeError, ValueError):
            return None

    @property
    def humidity(self) -> float | None:
        h = (self.coordinator.data.get("current") or {}).get("humidity")
        if h is None:
            return None
        try:
            return round(float(h) * 100, 0)
        except (TypeError, ValueError):
            return None

    @property
    def native_wind_speed(self) -> float | None:
        return _ms_to_kmh(_wind_ms((self.coordinator.data.get("current") or {}).get("wind")))

    @property
    def wind_bearing(self) -> int | None:
        return _wind_deg((self.coordinator.data.get("current") or {}).get("wind"))

    @property
    def native_visibility(self) -> float | None:
        v = self.coordinator.data.get("current_visibility_m")
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @property
    def condition(self) -> str | None:
        return observation_to_condition(self.coordinator.data.get("current"))

    @property
    def native_precipitation_unit(self) -> str:
        return "mm"

    @property
    def attribution(self) -> str:
        return "Дані з pogodairadar.com.ua (WetterOnline)"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        c = self.coordinator.data.get("current") or {}
        dp = _temp_c(c.get("dew_point"))
        if dp is not None:
            attrs["dew_point_c"] = dp
        app = _temp_c(c.get("apparent_temperature"))
        if app is not None:
            attrs["apparent_temperature_c"] = app
        prec = c.get("precipitation") or {}
        attrs["precipitation_type"] = prec.get("type")
        attrs["precipitation_probability_pct"] = _probability_pct(prec.get("probability"))
        attrs["air_pressure_tendency_category"] = c.get("air_pressure_tendency_category")
        attrs["smog_level"] = c.get("smog_level")
        attrs["solar_elevation"] = c.get("solar_elevation")
        days = self.coordinator.data.get("days") or []
        if days:
            today = days[0]
            uv = (today.get("uv_index") or {}).get("value")
            if uv is not None:
                attrs["uv_index"] = uv
            sunshine = (today.get("sunshine_duration") or {}).get("hours")
            if sunshine is not None:
                attrs["sunshine_hours"] = sunshine
        if self.coordinator.data.get("sunrise"):
            attrs["sunrise"] = self.coordinator.data["sunrise"]
        if self.coordinator.data.get("sunset"):
            attrs["sunset"] = self.coordinator.data["sunset"]
        attrs["last_update"] = self.coordinator.data.get("last_update_local")
        return attrs

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        return self._hourly(self.coordinator.data)

    async def async_forecast_daily(self) -> list[Forecast] | None:
        return self._daily_week(self.coordinator.data)

    async def async_get_forecasts(self, forecast_type: str) -> list[Forecast] | None:
        if forecast_type in ("hourly", getattr(WeatherEntity, "WEATHER_FORECAST_HOURLY", None)):
            return await self.async_forecast_hourly()
        if forecast_type in ("daily", getattr(WeatherEntity, "WEATHER_FORECAST_DAILY", None)):
            return await self.async_forecast_daily()
        return None

    def _hourly(self, data: dict[str, Any]) -> list[Forecast]:
        out: list[Forecast] = []
        for h in data.get("hours") or []:
            precip = h.get("precipitation") or {}
            vis_m = _visibility_meters_from_shortcast_hour(h)
            row: dict[str, Any] = {
                "datetime": h.get("date"),
                "condition": observation_to_condition(h),
                "native_temperature": _temp_c(h.get("air_temperature")),
                "precipitation_probability": _probability_pct(precip.get("probability")),
                "wind_bearing": _wind_deg(h.get("wind")),
                "native_wind_speed": _ms_to_kmh(_wind_ms(h.get("wind"))),
            }
            if vis_m is not None:
                row["native_visibility"] = vis_m
            out.append(Forecast(**row))
        return out

    def _daily_week(self, data: dict[str, Any]) -> list[Forecast]:
        out: list[Forecast] = []
        for d in (data.get("days") or [])[:7]:
            at = d.get("air_temperature") or {}
            precip = d.get("precipitation") or {}
            out.append(
                Forecast(
                    datetime=d.get("date"),
                    condition=observation_to_condition(d),
                    native_temperature=_temp_c(at.get("max")),
                    native_templow=_temp_c(at.get("min")),
                    precipitation_probability=_probability_pct(precip.get("probability")),
                    wind_bearing=_wind_deg(d.get("wind")),
                    native_wind_speed=_ms_to_kmh(_wind_ms(d.get("wind"))),
                )
            )
        return out
