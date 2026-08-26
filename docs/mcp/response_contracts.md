# Контракты ответов MCP

[Инструменты](../tools.md) · [Сценарии](../usage-flow.md) · [Safe Apply](../safe-apply.md)

Ответы инструментов — JSON-объекты. Точная схема зависит от инструмента, но общие поля и состояния остаются единообразными.

## Общий envelope

```json
{
  "ok": true,
  "status": "completed",
  "summary": "Краткий итог",
  "target": {
    "object_type": "chart",
    "object_id": "<CHART_ID>"
  },
  "artifacts": [],
  "warnings": [],
  "blockers": [],
  "next_actions": []
}
```

- `ok` сообщает, завершил ли инструмент заявленную операцию.
- `status` уточняет достигнутый этап или причину остановки.
- `summary` предназначен для краткого ответа пользователю.
- `target` фиксирует тип и ID цели, когда они известны.
- `artifacts` содержит пути к созданным файлам внутри project root.
- `warnings` описывает неблокирующие ограничения.
- `blockers` содержит проверяемые причины остановки.
- `next_actions` перечисляет допустимые следующие шаги.

Учётные данные, заголовки авторизации и приватные ключи удаляются из всех вложенных полей.

## Task-level ответы

Восемь инструментов `autonomous-v2` используют компактный restart-safe envelope:

```json
{
  "task_id": "<TASK_ID>",
  "state": "PLAN_VALIDATED",
  "task_revision": 6,
  "state_etag": "<SHA256>",
  "observed_facts": ["semantic scope bound to immutable task contract"],
  "route": "wizard_native",
  "performed": ["PLANNED -> VALIDATED"],
  "result": {"status": "plan_validated"},
  "not_performed": ["save", "publish"],
  "blocked_by": null,
  "risk": "No unresolved workflow risk is recorded.",
  "next_action": "dl_verify",
  "resource_uri": "datalens://tasks/<TASK_ID>"
}
```

Внешнее состояние `PLAN_VALIDATED` соответствует внутреннему checkpoint `VALIDATED`. `state_etag` вычисляется из восстановленного state и может быть передан в `dl_task_resume.expected_hash`. Terminal-ответ имеет пустой или отсутствующий `next_action`; blocker всегда содержит проверяемую причину.

Task journal хранится в `.datalens-mcp/tasks/<TASK_ID>/`: immutable contract, hash-chained events, checkpoint, plans и receipts. MCP resources публикуют status и разрешённые artifacts как `datalens://tasks/<TASK_ID>/...`. `dl_evidence` возвращает только один bounded excerpt:

```json
{
  "task_id": "<TASK_ID>",
  "resource_uri": "datalens://tasks/<TASK_ID>/plans/plan.json",
  "offset": 0,
  "returned_chars": 4000,
  "total_chars": 12400,
  "truncated": true,
  "text": "..."
}
```

Полный plan не дублируется в `dl_plan` или `dl_execute`: ответы содержат `plan_hash` и resource URI. Вызов `dl_execute` отклоняется до переходов при несовпадении task state, contract-bound plan hash или destructive token.

## Runtime и доступ

`dl_runtime_status` возвращает локальные сведения без сетевого запроса:

```json
{
  "ok": true,
  "project_root": "/absolute/path/to/project",
  "token_present": true,
  "org_id_set": true,
  "allow_writes": true,
  "allow_save": true,
  "allow_publish": true,
  "request_scheduler": {
    "scope": "process_per_api_base_url",
    "request_interval_sec": 1.05,
    "effective_request_starts_per_minute": 57.14,
    "max_read_concurrency": 3,
    "totals": {
      "requests": 12,
      "queue_wait_ms": 3400.0,
      "network_ms": 8200.0,
      "rate_limit_429": 0,
      "transient_retries": 1
    },
    "cache_hits": {
      "dashboard_snapshot": 2
    }
  }
}
```

Метрики агрегируются по процессу и методу. В них отсутствуют ID объектов, payload, заголовки и значения учётных данных.

`dl_auth_probe` выполняет минимальный live-read. Ошибки разделяются по действию пользователя:

| `status` | Значение |
| --- | --- |
| `missing_credentials` | Нет ID организации или токена и недоступно получение через `yc` |
| `expired_token` | Токен истёк, а обновление не завершилось успешно |
| `organization_access_denied` | Организация или целевой объект недоступны пользователю |
| `yc_reauthentication_required` | Yandex Cloud CLI требует интерактивного входа |
| `transport_failure` | Сетевая, DNS, TLS или proxy-ошибка до ответа API |
| `api_failure` | DataLens API вернул техническую ошибку, не относящуюся к авторизации |

Ошибочный ответ содержит очищенное сообщение и рекомендацию, но не значение или производные токена.

Транспортная ошибка DataLens API сохраняет `request_phase=transport`,
`response_received=false`, число выполненных read-retry и один из безопасных
подтипов: `tls_handshake_timeout`, `tls_unexpected_eof`,
`tls_connection_closed`, `transport_timeout`, `connection_reset` или
`remote_disconnected`. `tls_certificate_failure` и общий `tls_failure` не
повторяются как временные ошибки. Инструменты object lifecycle возвращают для
них `error.category=transport_failure`, а не `unknown_runtime_error`.

## Компактный и полный ответ чтения

Инструменты чтения поддерживают компактный ответ для чата и полный artifact для последующей работы:

```json
{
  "ok": true,
  "response_mode": "compact",
  "count": 12,
  "items": [],
  "artifact_path": "artifacts/readback/workbook.entries.json",
  "truncated": false
}
```

При превышении inline-бюджета полные данные сохраняются в `artifact_path`; `summary`, ID и поля, необходимые следующему инструменту, остаются в ответе.

Batch-вызов `dl_get_workbook_entries(workbook_ids=[...])` возвращает элементы в исходном порядке. Ошибка одного воркбука не удаляет artifacts успешных элементов и не превращает 404 в повторяемую ошибку.

## Снимок дашборда

`dl_snapshot_dashboard` не смешивает успешность вызова с полнотой резервной
копии:

```json
{
  "ok": true,
  "completion": {
    "status": "partial",
    "complete": false,
    "error_count": 0,
    "omission_count": 1,
    "missing_root_branches": [],
    "unsafe_reasons": []
  },
  "coverage": {
    "scope": "dashboard_dependency_graph",
    "org_wide": false,
    "requested_branches": ["saved"],
    "captured_branches": ["saved"]
  },
  "api_contract": {
    "header_name": "x-dl-api-version",
    "required_api_header_version": "2",
    "openapi_sha256": "<SHA256>"
  }
}
```

`complete` означает снимок запрошенного графа без ошибок и пропусков,
`partial` — доступный снимок с пропусками, `unsafe` — отсутствие корневой
ветки дашборда. Эти же блоки записываются в manifest.

## Тяжёлые планы и workflow

Safe-apply/publish plans, guarded RPC и manifest-backed workflow используют `response_mode="summary"` по умолчанию. Типичный inline-бюджет — 15 КБ:

```json
{
  "ok": true,
  "status": "planned",
  "response_mode": "summary",
  "summary": {
    "action_count": 1,
    "action_contracts": [
      {
        "method": "updateEditorChart",
        "safety_guard_mode": "save",
        "write_mode": "publish",
        "readback_branch": "published"
      }
    ],
    "write_modes": ["publish"],
    "readback_branches": ["published"],
    "top_level_mode_contract": "safety_guard_save; payload.mode controls the publish RPC"
  },
  "canonical_artifact": {
    "path": "artifacts/runtime/mcp_runs/<RUN>/create_safe_apply_plan.<SHA>.full.json",
    "sha256": "<SHA256>"
  },
  "full_response": {
    "serialized_chars": 120000,
    "sha256": "<SHA256>"
  }
}
```

Канонический очищенный результат записывается один раз; повторная выдача того же SHA не меняет файл. В publish-плане верхний `actions[].mode=save` означает защитный save-first guard, а фактический RPC-режим находится в `actions[].payload.mode=publish`; compact summary показывает оба значения явно. `response_mode="full"` сохраняет обратную совместимость и возвращает полные поля inline.

## Диагностика

`dl_diagnose`, `dl_validate_project`, `dl_validate_object` и проверки Editor возвращают findings:

```json
{
  "ok": false,
  "status": "blocked",
  "findings": [
    {
      "severity": "error",
      "rule": "example_rule",
      "path": "payload.data",
      "message": "Описание проблемы",
      "remediation": "Как исправить"
    }
  ],
  "coverage": {
    "checked_items": 4
  }
}
```

Пустая проверка не возвращается как успешная: `coverage.checked_items` должен отражать реально проверенные элементы.

Editor-валидация по умолчанию возвращает стабильный `corpus_reference_set` вместо повторяющегося списка ссылок. `include_references=true` добавляет полный список. Для одинакового payload и версии правил `validation_cache.hit=true`; JSON artifacts можно передать путями только внутри project root.

## Object plan

Create/update planners возвращают метод, нормализованный payload и target lock:

```json
{
  "ok": true,
  "operation": "update",
  "object_type": "chart",
  "method": "updateWizardChart",
  "target_lock": {
    "object_id": "<CHART_ID>",
    "branch": "saved",
    "base_revision": "<REV_ID>"
  },
  "desired_overlay": {},
  "validation": {
    "ok": true
  }
}
```

Update-plan хранит изменения отдельно от fresh readback. Executor накладывает overlay на актуальную saved-версию непосредственно перед записью.

## Safe Apply plan

`dl_create_safe_apply_plan` возвращает plan и путь к нему:

```json
{
  "ok": true,
  "status": "planned",
  "plan_path": "artifacts/plans/safe-apply.json",
  "delivery_intent_decision": {
    "state": "save_then_publish",
    "reason": "explicit_update_request"
  },
  "request_sha256": "<SHA256>",
  "target_lock": {},
  "actions": [],
  "blockers": []
}
```

Исходная команда пользователя авторизует обычный save-and-publish цикл. Отдельные поля подтверждения в этом контракте отсутствуют.

## Save, publish и readback

Save-ответ фиксирует выполненный метод и путь к saved readback:

```json
{
  "ok": true,
  "status": "saved",
  "action_results": [],
  "saved_readback_path": "artifacts/readback/object.saved.json",
  "next_action": "publish_from_saved"
}
```

Safe Apply не смешивает отправку записи и её последующую проверку. Каждый
`action_result` содержит:

```json
{
  "execution_stage": "verified",
  "write_outcome": "confirmed_write",
  "verification_outcome": "matched"
}
```

Полученный отказ API до записи возвращает
`write_outcome=remote_rejected_no_write`. Потеря ответа после отправки остаётся
`write_outcome=unknown` и требует reconciliation. Если запись подтверждена, но
readback не совпал, общий результат имеет `status=partial` и сохраняет список
`confirmed_write_action_indices`.

Если publish жёстко выключен, разрешённое сохранение возвращает:

```json
{
  "ok": true,
  "status": "saved_not_published",
  "saved_readback_path": "artifacts/readback/object.saved.json",
  "blockers": ["publish_disabled"]
}
```

Publish-plan должен ссылаться на saved artifact и ожидаемые идентификаторы:

```json
{
  "ok": true,
  "status": "publish_planned",
  "source_branch": "saved",
  "saved_readback_path": "artifacts/readback/object.saved.json",
  "expected_rev_id": "<REV_ID>",
  "expected_saved_id": "<SAVED_ID>",
  "plan_path": "artifacts/plans/publish-from-saved.json"
}
```

Published readback сохраняется отдельно:

```json
{
  "ok": true,
  "status": "published",
  "branch": "published",
  "published_readback_path": "artifacts/readback/object.published.json",
  "deployment_report_path": "artifacts/reports/deployment.json"
}
```

## Удаление

Произвольное whole-object delete не входит в стандартный lifecycle surface.
Ниже приведён контракт только для manifest-действия
`retire_legacy_objects`. Первый вызов `dl_run_project_live_apply` возвращает:

```json
{
  "ok": false,
  "status": "delete_confirmation_required",
  "target": {
    "object_type": "chart",
    "object_id": "<CHART_ID>"
  },
  "relations": [],
  "plan_hash": "<SHA256>",
  "next_action": "repeat_with_confirm_delete"
}
```

Второй вызов передаёт `confirm_delete=true` и должен ссылаться на тот же plan. Несовпадение цели, связей или hash возвращает новый `delete_confirmation_required`. Whole-object QL deletion не поддерживается.

Удаление элемента внутри объекта использует operation `update` и не возвращает этот статус.

## Project manifest

План project workflow возвращает только данные, объявленные manifest:

```json
{
  "ok": true,
  "workflow_name": "apply",
  "action": "save",
  "argv": [],
  "target_ids": [],
  "allowed_env_names": [],
  "expected_artifacts": [],
  "evidence_checks": []
}
```

Execution response содержит `execution_id`, `execution_key`, phase, heartbeat,
deadline, очищенные stdout/stderr, exit code, timeout, путь к summary и
достигнутый этап. Все команды выполняются durable worker-процессом; повторный
эквивалентный вызов присоединяется к текущему execution, а polling после
перезапуска MCP читает атомарный state/result без relaunch.
`dl_read_project_live_summary` проверяет совпадение target IDs и непустое
покрытие. Нулевой exit code не заменяет эту проверку: отсутствующий или
заблокированный apply/publish summary возвращает `summary_blocked`, а следующий
publish-этап не запускается.

## Ошибки аргументов инструмента

До вызова функции сервер проверяет набор аргументов. Неизвестное или
отсутствующее поле возвращает структурированную ошибку:

```json
{
  "ok": false,
  "error": {
    "category": "invalid_tool_arguments",
    "unknown_arguments": ["unexpected"],
    "missing_arguments": ["required_field"],
    "allowed_arguments": ["required_field"]
  }
}
```

Текст Python `TypeError` и traceback в MCP-ответ не попадают.

## Source availability

Матрица источников использует статусы:

- `OK` — источник доступен;
- `NO_DATA` — источник отвечает, но данных для условия нет;
- `NO_TABLE` — таблица отсутствует;
- `ERROR` — получена подтверждённая ошибка;
- `UNKNOWN` — данных проверки недостаточно.

Каждая строка содержит environment, source, consumers, evidence path и влияние на публикацию. Инструменты не делают вывод об отсутствии данных по усечённому или неоднозначному результату.

## Уровни подтверждения

Отчёты различают:

- `source_static` — проверка исходных файлов;
- `installed_static` — проверка установленного пакета;
- `live_read_only_api` — чтение DataLens API;
- `save_readback` — проверка saved-версии;
- `publish_readback` — проверка published-версии;
- `browser_rendered` — проверка интерфейса;
- `controlled_live_write` — подтверждённая запись на выбранную цель.

Итоговый ответ указывает максимально подтверждённый уровень. API-readback подтверждает структуру, а `browser_rendered` — фактическое отображение.

## Ошибки записи

| `status` | Поведение |
| --- | --- |
| `conflict_no_write` | Объект заблокирован или нарушена уникальность; автоматическая повторная запись не выполняется |
| `stale_revision` | Нужны новое чтение и новый plan |
| `write_outcome_unknown` | Результат отправленного write не подтверждён; сначала выполняется reconciliation |
| `saved_not_published` | Save завершён, publish выключен или запрещён режимом задачи |
| `runtime_not_verified` | API-этап завершён, проверка интерфейса недоступна |

Ответ об ошибке содержит `remote_code`, очищенное сообщение, target, выполненные этапы и безопасное следующее действие, когда эти данные доступны.
