# PogodaiRadar для Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![GitHub Release](https://img.shields.io/github/v/release/mrkaktuz/ha-pogodairadar)](https://github.com/mrkaktuz/ha-pogodairadar/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-41BDF5.svg)](https://www.home-assistant.io/)
[![GitHub Stars](https://img.shields.io/github/stars/mrkaktuz/ha-pogodairadar?style=social)](https://github.com/mrkaktuz/ha-pogodairadar/stargazers)

Кастомна інтеграція погоди для [pogodairadar.com.ua](https://www.pogodairadar.com.ua) з підтримкою:

- поточної погоди;
- погодинного прогнозу;
- денного прогнозу;
- метеопопереджень;
- текстового прогнозу;
- часу останнього оновлення.

## Встановлення через HACS

1. HACS -> Integrations -> Custom repositories.
2. Додайте URL цього репозиторію як тип `Integration`.
3. Встановіть `PogodaiRadar`.
4. Перезапустіть Home Assistant.
5. Додайте інтеграцію `PogodaiRadar` у Налаштуваннях.

## Налаштування

- `slug` з адреси сторінки, наприклад `buca/6702741`.
- Інтервал оновлення: 15 хв, 30 хв, 1 год, 2 год.

