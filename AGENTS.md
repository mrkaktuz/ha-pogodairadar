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
- Для релізу оновлювати версію в `manifest.json` і створювати git tag.

## HACS

- Має існувати `hacs.json` у корені.
- `content_in_root` має залишатися `false`.
- `README.md` має містити коротку інструкцію встановлення через HACS.

## Брендинг

- Іконка інтеграції: `custom_components/pogodairadar/icon.png`.
- Виробник у DeviceInfo: `kaktuz`.

## Перевірки перед публікацією

- `python -m compileall custom_components/pogodairadar`
- Перевірка відсутності зайвих файлів у коміті.
- Перевірка `manifest.json` (домен, версія, config_flow).
