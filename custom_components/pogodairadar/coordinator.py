"""Data update coordinator: fetch HTML and parse weather JSON."""

from __future__ import annotations

import json
import logging
import re
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import BASE_URL, DOMAIN, USER_AGENT

_LOGGER = logging.getLogger(__name__)

SERVER_APP_STATE_RE = re.compile(
    r'<script id="serverApp-state" type="application/json">([\s\S]*?)</script>',
    re.IGNORECASE,
)
GENERIC_JSON_SCRIPT_RE = re.compile(
    r'<script[^>]*type="application/json"[^>]*>([\s\S]*?)</script>',
    re.IGNORECASE,
)
WINDOW_STATE_RE = re.compile(
    r"window\.__[A-Za-z0-9_]+__\s*=\s*({[\s\S]*?})\s*;",
    re.IGNORECASE,
)

WARN_MAP_LABELS = {
    "storm": "Шторм / сильний вітер",
    "thunderstorm": "Гроза",
    "heavy_rain": "Сильні дощі",
    "slippery_conditions": "Ожеледь / слизькі дороги",
}

WARN_LEVEL_TEXT = {
    0: "немає ризику",
    1: "низький",
    2: "помірний",
    3: "високий",
    4: "дуже високий",
}


def _entry_by_url_substring(data: dict[str, Any], needle: str) -> Any | None:
    for key, val in data.items():
        if needle in key:
            if isinstance(val, list) and val:
                return val[0]
            return val
    return None


def _temp_c(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, dict):
        c = val.get("celsius")
        if c is not None:
            try:
                return float(c)
            except (TypeError, ValueError):
                pass
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _wind_ms(wind: dict | None) -> float | None:
    if not wind:
        return None
    try:
        mps = wind.get("speed", {}).get("meter_per_second", {}).get("value")
        if mps is None:
            return None
        return float(str(mps).split("-")[0])
    except (TypeError, ValueError, AttributeError):
        return None


def _wind_deg(wind: dict | None) -> int | None:
    if not wind:
        return None
    try:
        return int(wind.get("direction", 0))
    except (TypeError, ValueError):
        return None


def _probability_pct(value: Any) -> int | None:
    if value is None:
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if val <= 1:
        val *= 100
    return int(round(max(0, min(100, val))))


def symbol_to_condition(symbol: str | None) -> str:
    """Map WetterOnline symbol code to Home Assistant condition."""
    if not symbol:
        return "cloudy"
    s = symbol.lower().strip()
    if any(x in s for x in ("sr", "lr", "mr", "hr", "rr", "rs", "r1", "r2", "r3", "r4")):
        if "s" in s[:2] or s.startswith("sn") or "sf" in s:
            return "snowy"
        if "rs" in s or ("sr" in s and "sn" in s):
            return "snowy-rainy"
        return "rainy"
    if s.startswith("sn") or "sf" in s or s.startswith("s_") or "ds" in s:
        return "snowy"
    if "nb" in s or "nf" in s:
        return "fog"
    if s.startswith("ww") and "r" not in s:
        return "partlycloudy"
    if s.startswith("w") and len(s) >= 2 and s[1] in "_w":
        return "sunny"
    if s.startswith(("b", "m", "d")):
        if "w" in s[2:4] or s[2:4] == "__":
            return "partlycloudy"
        return "cloudy"
    return "cloudy"


def parse_server_state(raw_json: str) -> dict[str, Any]:
    """Extract structured weather data from serverApp-state."""
    data = json.loads(raw_json)
    geo = _entry_by_url_substring(data, "geokeycoding") or {}
    geo_obj = geo.get("geoObject") or {}
    name = geo_obj.get("locationName") or geo_obj.get("displayName", {}).get(
        "primaryName", "Погода"
    )

    shortcast = _entry_by_url_substring(data, "shortcast") or {}
    current = shortcast.get("current") or {}
    hours = shortcast.get("hours") or []

    forecast = _entry_by_url_substring(data, "blending/forecast") or {}
    days = forecast.get("days") or []

    editorial = _entry_by_url_substring(data, "editorial-pull-notification") or {}
    tomorrow_text = (editorial.get("body") or "").strip()

    warnings_v9 = _entry_by_url_substring(data, "warnings/v9") or {}
    warn_maps = _entry_by_url_substring(data, "warnings/maps") or {}

    astro = _entry_by_url_substring(data, "astro/days") or {}
    astro_days = astro.get("days") or []
    sunrise = None
    sunset = None
    if astro_days:
        target_date = (days[0].get("date") or "")[:10] if days else None
        for ad in astro_days:
            if target_date and (ad.get("date") or "")[:10] != target_date:
                continue
            sun = ad.get("sun") or {}
            sunrise = sun.get("rise")
            sunset = sun.get("set")
            if sunrise or sunset:
                break

    return {
        "location_name": name,
        "latitude": geo_obj.get("latitude"),
        "longitude": geo_obj.get("longitude"),
        "current": current,
        "hours": hours,
        "days": days,
        "tomorrow_text": tomorrow_text,
        "warnings_v9": warnings_v9,
        "warn_maps": warn_maps,
        "sunrise": sunrise,
        "sunset": sunset,
    }


def _extract_state_json(html: str) -> str | None:
    m = SERVER_APP_STATE_RE.search(html)
    if m:
        return m.group(1)

    for sm in GENERIC_JSON_SCRIPT_RE.finditer(html):
        candidate = sm.group(1).strip()
        if "shortcast" in candidate and "blending/forecast" in candidate:
            return candidate

    wm = WINDOW_STATE_RE.search(html)
    if wm:
        candidate = wm.group(1).strip()
        if "shortcast" in candidate and "blending/forecast" in candidate:
            return candidate

    return None


def build_warnings_summary(parsed: dict[str, Any]) -> str:
    parts: list[str] = []
    v9 = parsed.get("warnings_v9") or {}
    if isinstance(v9, dict) and v9:
        if "warnings" in v9 and v9["warnings"]:
            for w in v9["warnings"]:
                if isinstance(w, dict):
                    text = w.get("title") or w.get("headline") or w.get("text")
                    if text:
                        parts.append(str(text))
        for key in ("title", "headline", "text", "description"):
            if v9.get(key):
                parts.append(str(v9[key]))
        if not parts:
            parts.append(json.dumps(v9, ensure_ascii=False)[:500])

    wm = parsed.get("warn_maps") or {}
    for key, label in WARN_MAP_LABELS.items():
        block = wm.get(key)
        if not isinstance(block, dict):
            continue
        lvl = block.get("level_value")
        if lvl is not None and int(lvl) > 0:
            parts.append(f"{label}: рівень {lvl} ({WARN_LEVEL_TEXT.get(int(lvl), '')})")

    return " | ".join(parts) if parts else "Активних метеопопереджень немає"


class PogodaIRadarCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch pogodairadar page and parse embedded JSON."""

    def __init__(
        self,
        hass: HomeAssistant,
        slug: str,
        update_interval_seconds: int,
        entry_id: str,
    ) -> None:
        self.slug = slug.strip().strip("/")
        self._url = f"{BASE_URL}/{self.slug}"
        self._entry_id = entry_id
        self._slug_safe = self.slug.replace("/", "_").lower()
        self._last_update_entity_id: str | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=f"PogodaiRadar {self.slug}",
            update_interval=timedelta(seconds=update_interval_seconds),
        )

    @property
    def url(self) -> str:
        return self._url

    async def _log_activity(self, message: str) -> None:
        try:
            if self._last_update_entity_id is None:
                ent_reg = er.async_get(self.hass)
                unique_id = f"{self._entry_id}_{self._slug_safe}_last_update"
                entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
                self._last_update_entity_id = entity_id or ""

            data = {"name": f"PogodaiRadar {self.slug}", "message": message, "domain": DOMAIN}
            if self._last_update_entity_id:
                data["entity_id"] = self._last_update_entity_id

            await self.hass.services.async_call("logbook", "log", data, blocking=True)
        except Exception:
            _LOGGER.exception("Не вдалося записати повідомлення в Activity (logbook)")

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            headers = {"User-Agent": USER_AGENT, "Accept-Language": "uk-UA,uk;q=0.9"}
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self._url, headers=headers) as resp:
                    if resp.status != 200:
                        _LOGGER.error("PogodaiRadar HTTP помилка %s для %s", resp.status, self._url)
                        raise UpdateFailed(f"HTTP {resp.status}")
                    html = await resp.text(encoding="utf-8", errors="replace")
        except aiohttp.ClientError as err:
            _LOGGER.exception("PogodaiRadar мережева помилка для %s", self._url)
            raise UpdateFailed(f"Помилка мережі: {err}") from err

        raw_state = _extract_state_json(html)
        if not raw_state:
            _LOGGER.error("У відповіді %s немає вбудованих погодних даних", self._url)
            raise UpdateFailed("Не знайдено вбудований JSON з погодою у HTML")

        try:
            parsed = parse_server_state(raw_state)
        except json.JSONDecodeError as err:
            _LOGGER.exception("Некоректний JSON у відповіді %s", self._url)
            raise UpdateFailed(f"Некоректний JSON: {err}") from err

        parsed["warnings_summary"] = build_warnings_summary(parsed)
        now = dt_util.now()
        parsed["last_update_iso"] = now.isoformat()
        parsed["last_update_local"] = dt_util.as_local(now).isoformat()

        _LOGGER.info(
            "Оновлено погоду для %s: %s годин, %s днів, інтервал %s с",
            self.slug,
            len(parsed.get("hours") or []),
            len(parsed.get("days") or []),
            int(self.update_interval.total_seconds()),
        )
        await self._log_activity(
            f"Оновлено дані: {len(parsed.get('hours') or [])} годин, "
            f"{len(parsed.get('days') or [])} днів"
        )

        return parsed
