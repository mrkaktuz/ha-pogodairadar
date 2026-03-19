# PogodaiRadar для Home Assistant

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

## Структура

Інтеграція знаходиться в:

`custom_components/pogodairadar/`
