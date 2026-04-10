# AGENTS.md

Цей файл містить постійні правила для агентів, які працюють з репозиторієм.

## Призначення репозиторію

- Репозиторій містить кастомну інтеграцію Home Assistant `PogodaiRadar`.
- Цільова структура для HACS: `custom_components/pogodairadar/`.

## Важливі правила

- Не змінювати домен інтеграції: `pogodairadar`.
- Не переносити файли інтеграції в корінь репозиторію.
- Не додавати тестові HTML/response-файли у релізні коміти.
- Не додавати debug-перемикач у UI config flow без явного запиту.
- Залишати логування факту кожного оновлення в Activity (logbook).

## Версіонування

- Версія в `custom_components/pogodairadar/manifest.json`.
- Для релізу оновлювати версію в `manifest.json`, додати рядок у `CHANGELOG.md` і створити git tag (`vX.Y.Z`).
- Мапінг умов погоди (`symbol_to_condition`, узгодження з `precipitation.type` — `observation_to_condition`) — у `coordinator.py`; зміни варто звіряти з актуальними символами WetterOnline у фронтенд-бандлі, не комітити локальні `debug_src_files/` чи збережені HTML.

## HACS

- Має існувати `hacs.json` у корені.
- `content_in_root` має залишатися `false`.
- `README.md` має містити коротку інструкцію встановлення через HACS.

## Брендинг

- Іконка в каталозі інтеграції: `custom_components/pogodairadar/icon.png` (зворотна сумісність).
- Для HA 2026.3+ — каталог `custom_components/pogodairadar/brand/` з `icon.png`, `logo.png`, `dark_*` (без `@2x` у назвах файлових шляхів — `@` у URL брендів може ламати віддачу в HA).
- У README — зображення логотипу з `raw.githubusercontent.com`, щоб HACS показував його на сторінці інтеграції (обмеження HACS щодо локального `brand/` у списку, див. [hacs/integration#5171](https://github.com/hacs/integration/issues/5171)).
- Виробник у DeviceInfo: `kaktuz`.

## Перевірки перед публікацією

- `python -m compileall custom_components/pogodairadar`
- Перевірка відсутності зайвих файлів у коміті.
- Перевірка `manifest.json` (домен, версія, config_flow).
