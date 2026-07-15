# Сверка качества данных

Используйте этот процесс, когда значение дашборда нужно сверить с контрольным baseline без сохранения исходного контрольного файла.

1. Подготовьте агрегированный summary baseline.
2. Опишите слои: source, history, current, mart и dashboard result.
3. Соберите точечные read-only проверки через доступный metadata/data provider.
4. Передайте очищенные результаты в `dl_diagnose`.
5. Для source availability соберите и проверьте matrix.
6. Сформируйте before/after evidence через `dl_build_validation_evidence_report`.

Разделяйте business key и стабильный технический ключ: изменяемый номер заказа не подходит как единственная связь при анализе перенумерации.

Исправление только на уровне дашборда выполняется после того, как evidence исключило проблему в source, history, current или mart. Raw контрольные строки, credentials, auth headers, cookies и token-like значения не записываются в artifacts.
