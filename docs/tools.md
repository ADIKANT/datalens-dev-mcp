# Инструменты MCP

**Русский** · [English](tools_en.md) · [Главная](../README.md)

[Быстрый старт](../README.md#быстрый-старт) · [Доступ к DataLens](access.md) · [Подключение](codex_setup.md) · **Инструменты** · [Сценарии](usage-flow.md) · [Источники](sources.md) · [Безопасность](local-only-safety-model.md)

Поверхность `autonomous-v2` используется по умолчанию. Она содержит восемь task-level инструментов и скрывает внутренние lifecycle-вызовы от модели. Сервер сам выбирает безопасный маршрут, ведёт restart-safe журнал, создаёт hash-bound план, применяет его через Safe Apply и возвращает компактные результаты с URI доказательств.

Точная JSON-схема всегда доступна через MCP `tools/list`. Технические контракты и совместимая поверхность `legacy-v1` описаны в [каталоге](mcp/tools.md), общие ответы — в [response contracts](mcp/response_contracts.md).

## Автономная поверхность

| Инструмент | Назначение | Когда использовать | Необходимые данные | Результат и класс | Источник |
| --- | --- | --- | --- | --- | --- |
| `dl_task_start` | Компилирует запрос в неизменяемый контракт и запускает workflow | В начале новой задачи | `request`, при необходимости `project_root`, `context`, `run_until` | Task ID, состояние, выполненные переходы и resource URI · `локальная` | [Task workflow](usage-flow.md#автономный-task-workflow) |
| `dl_task_resume` | Возобновляет сохранённый workflow с optimistic checks | После перезапуска или остановки на плане/блокировке | `task_id`, ожидаемые state/hash и граница выполнения | Новое состояние и компактный итог · `локальная`/`защищённая запись` | [Task workflow](usage-flow.md#автономный-task-workflow) |
| `dl_task_status` | Читает компактное состояние без выполнения переходов | Для проверки прогресса | `task_id` | State, revision, etag, blocker и следующий шаг · `локальная` | [Task state](mcp/response_contracts.md#task-level-ответы) |
| `dl_inspect` | Собирает ограниченный обзор проекта и доступных artifacts | Перед планированием или для диагностики | При необходимости `task_id`, `target_url`, `max_nodes` | Bounded graph и project-validation summary · `локальная` | [Task workflow](usage-flow.md#автономный-task-workflow) |
| `dl_plan` | Доводит задачу до проверенного hash-bound плана | Когда нужен явный план до исполнения | `task_id` | Plan hash, resource URI и readiness · `локальная` | [Safe Apply](safe-apply.md) |
| `dl_execute` | Исполняет только точный проверенный план | После проверки `plan_hash` | `task_id`, `plan_hash`, для destructive scope точный token | Результат переходов save/readback/publish/QA · `защищённая запись` | [Safe Apply](safe-apply.md) |
| `dl_verify` | Проверяет требуемую точку доказательства | После планирования или исполнения | `task_id`, при необходимости `proof_target` | Проверки журнала, readback и browser-policy · `локальная` | [Task state](mcp/response_contracts.md#task-level-ответы) |
| `dl_evidence` | Читает один ограниченный artifact задачи | Когда нужен фрагмент плана, receipt или доказательства | `task_id`, resource URI/section/offset/limit | Bounded excerpt без тяжёлого inline-ответа · `локальная` | [Ресурсы доказательств](mcp/response_contracts.md#task-level-ответы) |

## Профили поверхности

- `autonomous-v2` — профиль по умолчанию: восемь инструментов, не более 9 КБ в `tools/list` и не более 1.5 КБ initialization instructions.
- `legacy-v1` — совместимая поверхность из прежних 39 lifecycle-инструментов для существующих интеграций.
- `expert` — полный внутренний registry для управляемой оператором диагностики. Он включается только локальной настройкой процесса `DATALENS_MCP_TOOL_SURFACE=expert`; запрос или prompt не может изменить профиль работающего сервера.

Acceptance receipts фиксируют `declared_surface`, `effective_surface` и
`surface_consistent`. Профили autonomy, affected и full-sharded всегда
исполняются как `autonomous-v2`; совместимость `legacy-v1` проверяется только
явно изолированными тестами.

Перезапустите MCP-процесс после изменения `DATALENS_MCP_TOOL_SURFACE`. Не передавайте profile в `tools/list`: активная поверхность фиксируется при запуске процесса.

## Безопасность выполнения

- Task contract, state и event chain сохраняются в `.datalens-mcp/tasks/<TASK_ID>/` и проверяются при replay.
- `dl_execute` принимает только plan hash, связанный с неизменяемым task contract.
- Write-task использует обычный save-first Safe Apply, saved readback, publish из verified saved state и published readback.
- Review, audit, diagnose и plan-only не выполняют запись.
- Тяжёлые планы и доказательства возвращаются как `datalens://tasks/<TASK_ID>/...`; `dl_evidence` читает только один разрешённый artifact с ограничением размера.
- Отдельный destructive token нужен только для явно скомпилированного destructive scope. Произвольное удаление целого объекта не поддерживается.

Установленная поверхность подтверждается отдельным public stdio canary. Его
receipt фиксирует ровно 8 инструментов, установленный build, frozen source,
save/restart/publish/readback, typed dataset evidence, ноль browser-вызовов и
ноль stale-plan записей. См. [`public-autonomy-canary.md`](public-autonomy-canary.md).

## Совместимость

Внутренние lifecycle-инструменты не удалены: `legacy-v1` сохраняет точный прежний набор из 39 имён и схем. Новые клиенты должны использовать `autonomous-v2`; прямой вызов скрытого low-level инструмента в этом профиле отклоняется до исполнения.
