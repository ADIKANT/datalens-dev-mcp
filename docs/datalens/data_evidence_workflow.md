# Проверка источников данных

Эта последовательность собирает read-only evidence перед изменением дашборда, SQL или датасета.

## Статусы

- `AVAILABLE` — точечная проверка подтвердила источник;
- `UNAVAILABLE_CONFIRMED` — точечный поиск подтвердил отсутствие;
- `NOT_PROBED` — проверка не выполнялась;
- `PROBE_BLOCKED` — проверка недоступна или небезопасна;
- `INCONCLUSIVE_TRUNCATED` — усечённый результат не позволяет сделать вывод.

## Процесс

1. Подготовьте ограниченные результаты table discovery, column list, row count, sample или stage count через выбранный read-only provider.
2. Передайте очищенные результаты в `dl_diagnose` с подходящим mode.
3. Для нескольких источников и consumers используйте `dl_build_dashboard_source_availability_matrix`.
4. Проверьте согласованность через `dl_validate_source_availability_consumers`.
5. Постройте точечное исправление через `dl_plan_source_availability_patch`.
6. Добавьте результат в `dl_build_validation_evidence_report`.

Производственные probes перечисляют столбцы явно и используют ограничение строк. Усечённый aggregate inventory не подтверждает отсутствие таблицы; для этого нужен точечный table discovery.

Сохраняйте только очищенные агрегаты и схемы внутри active project root. Токены, headers и raw private rows в отчёты не входят.
