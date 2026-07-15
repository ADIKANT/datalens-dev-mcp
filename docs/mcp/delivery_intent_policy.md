# Режим выполнения задачи

Один классификатор режима используется при планировании payload, Safe Apply, project-manifest flow и publish-from-saved.

## Состояния

- `read_only` — audit, review, diagnose, inspect, check;
- `plan_only` — plan-only и dry-run;
- `save_only` — save-only, no-publish и draft;
- `save_then_publish` — create, fix, update, enhance и redesign для известной цели;
- `publish_from_saved` — публикация из свежего saved readback;
- `delete` — удаление целого объекта после отдельного подтверждения;
- `blocked` — неизвестная цель, жёстко выключенная возможность, устаревшая ревизия, отсутствующий saved readback или неподдерживаемая операция.

План содержит `delivery_intent_decision` с состоянием, причиной, требуемыми проверками, следующим действием и путём подтверждения результата. Исходный пользовательский запрос сохраняется как нормализованный intent и SHA-256.

Команда пользователя создать, исправить, обновить, улучшить или переработать известный объект запускает save, saved readback, publish-from-saved и published readback. Дополнительная фраза подтверждения перед save или publish не требуется.

`save-only` и `no-publish` блокируют publish. Неизвестные ID блокируют write. Publish-plan всегда ссылается на saved readback и сохраняет ожидаемые `revId` и `savedId`.

Для удаления целого объекта первый вызов возвращает `delete_confirmation_required`, точные ID и hash плана. Выполнение требует `confirm_delete=true` для того же плана.
