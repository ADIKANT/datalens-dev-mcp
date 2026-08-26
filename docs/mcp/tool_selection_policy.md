# Выбор инструментов

`tools/list` по умолчанию содержит восемь task-level инструментов `autonomous-v2`. Выбор начинается с цели пользователя, а low-level lifecycle остаётся server-owned.

## Рекомендуемый порядок

1. `dl_task_start` — компиляция цели, режима доставки, evidence и browser policy; остановка на `PLAN_VALIDATED` по умолчанию.
2. `dl_task_status` и `dl_inspect` — состояние и bounded обзор при необходимости.
3. `dl_plan` — явное чтение task-bound plan hash.
4. `dl_execute` — исполнение только совпадающего плана для write-task.
5. `dl_task_resume` — restart-safe продолжение server-owned переходов.
6. `dl_verify` — проверка требуемой точки доказательства.
7. `dl_evidence` — один bounded artifact вместо тяжёлого inline-ответа.

В профиле `legacy-v1` низкоуровневые вызовы остаются доступными для совместимости. Новая автономная задача не выбирает их через prompt: сервер использует внутренний registry, object plan и Safe Apply.

Произвольное удаление целого объекта недоступно. Manifest action
`retire_legacy_objects` требует `confirm_delete=true` для совпадающего плана.
Удаление содержимого внутри объекта остаётся update.
