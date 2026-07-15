# Flow использования сервера

**Русский** · [English](usage-flow_en.md) · [Документация](README.md) · [Инструменты](tools.md) · [Codex setup](codex_setup.md)

Flow одинаков для Codex, Claude и любого другого MCP-клиента. Различается только регистрация stdio process; tool sequence, safety gates и response contracts задает сервер.

## 1. Подключение и preflight

1. Установите package и настройте external env file по [README](../README.md#установка).
2. Зарегистрируйте stdio server в клиенте. Для Codex используйте [пошаговую инструкцию](codex_setup.md).
3. Перезапустите клиент после изменения MCP-конфигурации.
4. Проверьте доступность server и стандартный tools surface.
5. Вызовите `dl_runtime_status`, затем `dl_auth_probe`.

В безопасном первом запуске ожидается:

- `allow_writes=false`;
- `allow_save=false`;
- `allow_publish=false`;
- `expert_rpc_enabled=false`;
- правильный `project_root`;
- auth presence без token values, prefixes или lengths.

Prompt для Codex:

> Используй только публичные инструменты DataLens MCP. Вызови `dl_runtime_status`, покажи project root, API version и mutation gates, затем выполни `dl_auth_probe`. Ничего не изменяй. Не выводи credentials или данные, производные от токена.

## 2. Read-only аудит

Цель — получить evidence о точном live target до любых решений.

```text
dl_runtime_status
  -> dl_auth_probe
  -> dl_list_workbooks
  -> dl_get_workbook_entries
  -> dl_snapshot_dashboard
  -> dl_read_object / dl_get_entries_relations
  -> dl_reference or dl_diagnose when needed
```

Рекомендуемый порядок:

1. Выберите workbook из `dl_list_workbooks`.
2. Получите compact inventory через `dl_get_workbook_entries`.
3. Для существующего dashboard всегда создайте fresh `dl_snapshot_dashboard`.
4. Прочитайте конкретные charts/datasets/connections через `dl_read_object`.
5. Получите relation graph через `dl_get_entries_relations` до изменения связанного object.
6. Используйте `dl_reference` для bounded official/local policy context и `dl_diagnose` для SQL, grain или performance evidence.

Prompt:

> Проведи read-only аудит dashboard `<DASHBOARD_ID>` в workbook `<WORKBOOK_ID>`. Сначала проверь runtime и auth, затем создай полный snapshot dashboard graph, прочитай связанные объекты и relation graph. Верни компактный список объектов, revision/branch evidence, риски и artifact paths. Ничего не сохраняй и не публикуй.

Если credentials отсутствуют, server возвращает `BLOCKED_LIVE_CREDENTIALS`. Исправьте external env file и перезапустите MCP process; не вставляйте токен в chat.

## 3. Plan-only

Plan-only превращает свежий readback и требования в проверенный no-write plan.

```text
fresh snapshot/readback
  -> dl_reference(mode="chart_selection" or "api_contract")
  -> dl_plan_object_create / dl_plan_object_update
  -> specialized planner when needed
  -> dl_validate_object
  -> dl_validate_editor_runtime_contract when Editor is involved
  -> dl_validate_project
  -> dl_build_payload_plan
  -> dl_create_safe_apply_plan (unapproved)
```

Правила выбора planner:

- стандартный create/update: `dl_plan_object_create` или `dl_plan_object_update`;
- изменение dataset model: `dl_plan_guarded_dataset_update`;
- одна dashboard tab: `dl_plan_dashboard_tab_update`;
- uncertain create retry: сначала `dl_reconcile_partial_creates`;
- exact RPC contract перед apply: `dl_compile_guarded_rpc_request`.

Создание стандартного нового chart идет через `wizard_native`. Advanced Editor выбирается только по прямому запросу или зарегистрированному capability gap. QL create/update требует прямого запроса QL и никогда не является fallback.

Prompt:

> На основе fresh saved readback спланируй изменение `<OBJECT_ID>`: `<ТРЕБОВАНИЕ>`. Покажи выбранный route, official API method, desired overlay, сохраняемые revision/unknown fields, validation findings и unapproved safe-apply plan. Работай строго plan-only: не включай gates и не выполняй write.

До live apply должны быть понятны target IDs, changed sections, blockers, readback mode и intended delivery state.

## 4. Guarded save и publish

Live write выполняется только после review plan и явного включения необходимых gates во внешнем env-файле. Изменение env требует restart MCP process.

### Save

```text
approved safe-apply plan
  -> dl_execute_safe_apply(mode=save)
  -> fresh read immediately before write
  -> revision-preserving save
  -> saved readback
  -> dl_readback_and_report(branch=saved)
```

Для save нужны `DATALENS_MCP_ENABLE_WRITES=1`, `DATALENS_MCP_LIVE_ALLOW_SAVE=1`, tool approval, fresh saved readback, validated payload и approved plan. `draft`, `review`, `plan-only`, `save-only` и `no-publish` не разрешают publish.

Prompt для save-only:

> Примени утвержденный plan к известному target в режиме save-only. Перед write сделай fresh saved read, сохрани revision и неизвестные поля, выполни saved readback и deployment report. Не создавай publish plan и не публикуй.

### Publish-from-saved

```text
verified saved readback
  -> saved runtime gate when the change is visible
  -> dl_create_publish_from_saved_plan
  -> dl_execute_safe_apply(publish action)
  -> published readback
  -> dl_readback_and_report(branch=published)
```

Publish возможен только из saved-branch artifact с expected `revId` и `savedId`, при delivery intent `save_then_publish`/`publish_from_saved` и `DATALENS_MCP_LIVE_ALLOW_PUBLISH=1`. Нельзя строить publish plan из published или unknown branch.

Prompt для полного guarded delivery:

> Реализуй согласованное изменение известного target. Используй approved safe-apply plan и включенные runtime gates. Выполни save, saved readback, runtime smoke измененного visible scope, затем publish только из проверенного saved artifact, после чего выполни published readback и deployment report. Если browser/runtime proof недоступен, верни `runtime_not_verified`, а не `done`.

## 5. Runtime и browser QA

API readback доказывает структуру, но не browser render. Для измененного visible chart/tab приемка идет в таком порядке:

1. browser/runtime smoke для changed scope;
2. sanitized details из DataLens error card, если она появилась;
3. targeted source evidence;
4. saved/published readback как structural proof;
5. `validateDataset` только как schema/compile hint для dataset changes.

Сам MCP tool `dl_run_live_maintenance_update` не открывает browser и не выполняет DataLens write. Он проверяет supplied guarded-execution и runtime evidence, рассчитывает delivery stage и создает final handoff artifact. Codex может получить browser evidence отдельным доступным browser/computer tool и затем передать его MCP planner.

Финальный visible change имеет статус:

- `done` — runtime gate passed или есть явное non-rendering exemption;
- `runtime_not_verified` — browser auth/tooling не позволили проверить;
- `blocked` — найден runtime marker или не пройден safety gate;
- `rolled_back` — выполнен подтвержденный rollback.

## 6. Project-live repositories

Если downstream project уже содержит собственные guarded scripts, не запускайте их напрямую. Используйте manifest-backed lane:

```text
dl_detect_project_live_workflows
  -> dl_plan_project_manifest when missing
  -> dl_plan_project_live_workflow
  -> dl_run_project_live_dry_run
  -> dl_read_project_live_summary
  -> dl_run_project_live_apply when approved
  -> dl_read_project_live_summary
```

Manifest фиксирует exact argv, object IDs, allowed env names, expected artifacts, evidence checks и safety constraints. Отсутствие manifest возвращает `adapter_required`. Именованное удаление объектов не добавляется в обычный publish: оно проходит отдельный `retire_legacy_objects` lifecycle.

## 7. Типовые остановки

| Состояние | Что означает | Следующее действие |
| --- | --- | --- |
| `BLOCKED_LIVE_CREDENTIALS` | Нет usable org ID/token | Исправить external env file и restart process |
| `adapter_required` | Project scripts не описаны manifest | Preview `dl_plan_project_manifest`, review, затем approved local write |
| Stale revision/readback | Target изменился после plan | Повторить fresh read, пересобрать overlay и plan |
| `conflict_no_write` | Lock или uniqueness conflict | Не retry blindly; дождаться lock или reconcile identity |
| `write_outcome_unknown` | После write attempt нет классифицированного результата | Остановиться и провести read-only reconciliation |
| `runtime_not_verified` | Структура подтверждена, render proof отсутствует | Провести browser smoke или передать статус без заявления `done` |

## 8. Клиенты кроме Codex

Claude Code, Claude Desktop и generic stdio clients используют тот же server command, env file и `--project-root`; примеры регистрации находятся в [README](../README.md#подключение-mcp-клиента). После подключения начните с того же `dl_runtime_status` → `dl_auth_probe` Flow и не просите модель выбирать hidden tool profile.
