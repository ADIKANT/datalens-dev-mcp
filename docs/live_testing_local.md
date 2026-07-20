# Локальные проверки с DataLens

[Доступ](access.md) · [Safe Apply](safe-apply.md) · [Общие проверки](testing.md)

Live-проверки выполняются с локальными учётными данными и выбранными пользователем объектами. CI и offline acceptance к DataLens не обращаются.

## Чтение

1. Настройте `DATALENS_ENV_FILE`.
2. Вызовите `dl_runtime_status` и `dl_auth_probe`.
3. Проверьте `dl_list_workbooks` и чтение тестового объекта.
4. Убедитесь, что ответы и логи не содержат секретов.

## Save-only

Используйте специально выбранный объект и формулировку save-only. План должен содержать точный ID, свежую ревизию и ожидаемый saved readback. После save сравните изменённые поля и сохранённые неизвестные поля.

## Save and publish

Для полного цикла сформулируйте create/fix/update/enhance/redesign, выполните saved readback, создайте publish-from-saved и проверьте published readback. Видимое изменение дополнительно проверяется в DataLens.

## Удаление

Тест удаления выполняется только через manifest action `retire_legacy_objects`
на специально созданной цели. Первый вызов должен вернуть
`delete_confirmation_required`; второй — принять `confirm_delete=true` для
того же plan и ID. Отсутствие объекта проверяется отдельным чтением.

Не используйте production-объекты для проверки записи или удаления.
