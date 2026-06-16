# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Постійні правила репозиторію — у `AGENTS.md` (домен, версіонування, HACS, брендинг). Цей файл їх не дублює, а описує архітектуру й неочевидну механіку.

## Що це

Кастомна інтеграція Home Assistant `pogodairadar`, що дістає погоду з `pogodairadar.com.ua` (фронтенд WetterOnline). Офіційного API немає: координатор **завантажує HTML сторінки й парсить вбудований JSON** (`serverApp-state`), що його Angular віддає в SSR. Код інтеграції живе тільки в `custom_components/pogodairadar/` (для HACS, `content_in_root: false`).

## Архітектура (велика картина)

Потік даних: `__init__.py` створює один `PogodaIRadarCoordinator` на config entry → координатор фетчить+парсить → entity-класи у `weather.py` і `sensor.py` лише читають `coordinator.data` (вони `CoordinatorEntity`, без власного I/O).

- **`coordinator.py`** — серце. Тут уся мережа й увесь парсинг, причому як **чисті функції модульного рівня** (їх імпортує `weather.py`): `symbol_to_condition`, `observation_to_condition`, `_temp_c`, `_wind_ms/_wind_deg`, `_probability_pct`, `_visibility_meters_from_shortcast_hour`, `parse_server_state`, `build_warnings_summary`. Логіку парсингу правимо тут, а не в entity-класах.
- **`weather.py`** — `weather.*` сутність (поточна + погодинний/денний прогноз), мапить дані WO у поля/одиниці HA.
- **`sensor.py`** — текстовий прогноз, метеопопередження, час останнього оновлення.
- **`config_flow.py`** / **`const.py`** / **`strings.json`** — UI-налаштування: `slug` (напр. `buca/6702741`) і інтервал опитування (15хв/30хв/1год/2год).

### Ключова механіка `serverApp-state`

Це dict, де **ключ — це URL API-запиту**, а значення — тіло відповіді. Записи дістаються за підрядком URL:

- `_entry_by_url_substring(data, needle)` — повертає запис; якщо значення список, **схлопує до `[0]`** (зручно для одиничних об'єктів і гео-пошуку).
- `_full_entry_by_url_substring(data, needle)` — повертає значення **як є**, не схлопуючи список. Потрібно там, де відповідь — масив, який треба зберегти цілим (напр. `blending/texts/v1/one_day` — тексти на кожен день).

Відомі підрядки-ключі: `geokeycoding`, `shortcast`, `blending/forecast`, `blending/texts/v1/one_day`, `editorial-pull-notification`, `warnings/v9`, `warnings/maps`, `astro/days`.

### Мапінг погодних умов (тонке місце)

HA має фіксований набір `condition`. `symbol_to_condition` переводить символьні коди WO (напр. `bdr1__`, `mds2__`) у ці умови через регекси/префікси. **Важливо:** `observation_to_condition` додатково звіряється з `precipitation.type` — WO інколи ставить «сніговий» код символу, коли фактично дощ; явний тип опадів має пріоритет. Зміни в мапінгу звіряти з актуальними символами у фронтенд-бандлі WO (не комітити збережені HTML/`debug_src_files/`).

### Текст із WO-токенами

Тексти `blending/texts` містять інлайн-токени типу `<WOCurrentTemperature>19</WOCurrentTemperature>`. Очищати через `_clean_forecast_text` (лишає внутрішнє значення).

## Команди

Тестового набору немає. Перевірки перед комітом/релізом:

```bash
python -m compileall custom_components/pogodairadar
python -m json.tool custom_components/pogodairadar/manifest.json   # домен, version, config_flow
```

Залежності HA (`homeassistant`, `aiohttp`, `voluptuous`) у цьому середовищі можуть бути не встановлені — чисті функції парсингу тестуються ізольовано (без імпорту HA).

## Реліз

Процес — в `AGENTS.md`: підняти `version` у `manifest.json`, додати запис у `CHANGELOG.md`, створити git tag `vX.Y.Z` на релізному коміті (тег можна вішати прямо на feat-коміт, як у попередніх версіях). HACS показує версії як **GitHub Releases**, тож для встановлюваної версії потрібен опублікований Release, а не лише тег.

## Середовище

Доступ до хостів даних (`pogodairadar.com.ua`, `*.wo-cloud.com`) може бути заблокований мережевою політикою сесії — живий зразок JSON тоді не дістати з оточення; покладайся на надані фрагменти відповіді.
