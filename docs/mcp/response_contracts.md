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

## Runtime и доступ

`dl_runtime_status` возвращает локальные сведения без сетевого запроса:

```json
{
  "ok": true,
  "project_root": "/absolute/path/to/project",
  "credentials": {
    "organization_id_present": true,
    "token_present": true
  },
  "capabilities": {
    "allow_writes": true,
    "allow_save": true,
    "allow_publish": true,
    "refresh_available": true
  }
}
```

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

Первый запрос удаления целого объекта возвращает:

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

Второй вызов передаёт `confirm_delete=true` и должен ссылаться на тот же plan. Несовпадение цели, связей или hash возвращает новый `delete_confirmation_required`.

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

Execution response содержит очищенные stdout/stderr, exit code, timeout, путь к summary и достигнутый этап. `dl_read_project_live_summary` проверяет совпадение target IDs и непустое покрытие.

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
