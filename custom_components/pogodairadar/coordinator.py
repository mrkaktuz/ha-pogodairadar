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


# WetterOnline / pogodairadar symbol → HA condition (aligned with main.js scene data + uk translations).
_WO_THUNDER = re.compile(r"^[bdmw][bdmw]g[123]")
_WO_SNOW_THUNDER = re.compile(r"^[bdmw][bdmw]sg")
_WO_SNOW_FLURRIES = re.compile(r"^[bdmw][bdmw]s[123]_")


def symbol_to_condition(symbol: str | None) -> str:
    """Map WetterOnline symbol code to Home Assistant weather condition.

    Logic follows WO bundles (regex → cloudy/rain/snow/…) and uk symbol labels in translations.
    HA only supports a fixed set of conditions; we pick the closest match.
    """
    if not symbol:
        return "cloudy"
    s = symbol.lower().strip()

    # Smog (am____, an____, ap____, as____) — no HA «smog»; fog is the closest UX.
    if s.startswith(("am", "an", "ap", "as")):
        return "fog"

    # Fog / mist (nb____, nn____); mixed sun/fog (nm____, ns____) → partlycloudy
    if s.startswith(("nb", "nn")):
        return "fog"
    if s.startswith(("nm", "ns")):
        return "partlycloudy"

    # Polar / extreme cold pictograms (ca____, …) — exceptional avoids wrong «snow» when no snowfall.
    if s.startswith(("ca", "cm", "cn", "cs")):
        return "exceptional"

    # Clear sky: so = sunny, ms = cloudless day, mo = clear night (translations.js).
    if s.startswith("so"):
        return "sunny"
    if s.startswith("ms"):
        return "sunny"
    if s.startswith("mo"):
        return "clear-night"

    # Thunder (гроза): *g[123]__ — usually with rain in WO data.
    if _WO_THUNDER.match(s):
        return "lightning-rainy"

    # Snow + lightning (sg__)
    if _WO_SNOW_THUNDER.match(s):
        return "snowy"

    # Sleet / rain–snow mix
    if "srs" in s or "dsrs" in s or "wsrs" in s or re.search(r"sr[123]", s):
        return "snowy-rainy"

    # Snow showers / flurries
    if _WO_SNOW_FLURRIES.match(s) or re.search(r"sn[123]", s) or "sns" in s:
        return "snowy"

    # Rain intensity (r3 = heavy → pouring)
    if "r3__" in s:
        return "pouring"
    if "r1__" in s or "r2__" in s:
        return "rainy"
    if "gr1_" in s or "gr2_" in s:
        return "rainy"

    if any(x in s for x in ("lr", "mr", "hr", "rr")):
        return "rainy"

    # Base cloud cover (exact 6-char icons from WO symbol set — not bds1__/bdr1__/…).
    if s == "mm____":
        return "partlycloudy"
    if s in ("wb____", "mb____"):
        return "partlycloudy"
    if s in ("bw____", "mw____"):
        return "cloudy"
    if s in ("bd____", "md____"):
        return "cloudy"

    if s.startswith("ww") and "r" not in s:
        return "partlycloudy"
    if s.startswith("w") and len(s) >= 2:
        if s[1] in "_w":
            return "sunny"
        if s[1] == "b":
            return "partlycloudy"

    if s.startswith(("b", "m", "d")):
        if "w" in s[2:4] or s[2:4] == "__":
            return "partlycloudy"
        return "cloudy"

    return "cloudy"


def observation_to_condition(obs: dict[str, Any] | None) -> str:
    """Map shortcast/blending observation (current, hour, or day) to HA condition.

    WetterOnline may set a snow-pictogram code (e.g. ``mds2__`` for night/mixed UI)
    while ``precipitation.type`` is ``rain``. The site then shows rain (e.g. ``bdr1__``)
    for hourly slots. Prefer explicit ``precipitation.type`` when it contradicts
    a snow-only mapping from ``symbol``.
    """
    if not obs:
        return "cloudy"
    sym = obs.get("symbol")
    prec = obs.get("precipitation") or {}
    ptype = (prec.get("type") or "").strip().lower()
    mapped = symbol_to_condition(sym)

    if ptype == "rain" and mapped in ("snowy", "snowy-rainy"):
        s = (sym or "").lower()
        if "r3__" in s:
            return "pouring"
        return "rainy"

    return mapped


def _visibility_meters_from_shortcast_hour(hour: dict[str, Any] | None) -> float | None:
    """Extract horizontal visibility in metres from one shortcast hour slot."""
    if not hour:
        return None
    vis = hour.get("visibility")
    if not isinstance(vis, dict):
        return None
    m = vis.get("meter")
    if m is not None:
        try:
            return float(m)
        except (TypeError, ValueError):
            pass
    ft = vis.get("feet")
    if ft is not None:
        try:
            return round(float(ft) * 0.3048, 1)
        except (TypeError, ValueError):
            pass
    return None


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

    # WO shortcast "current" often has no visibility; use first hourly slot (nearest hour).
    nearest_hour = hours[0] if hours else None

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
        "current_visibility_m": _visibility_meters_from_shortcast_hour(nearest_hour),
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
