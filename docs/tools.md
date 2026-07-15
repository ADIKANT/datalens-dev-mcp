# Публичные инструменты MCP

**Русский** · [English](tools_en.md) · [Документация](README.md) · [Flow](usage-flow.md) · [Источники](sources.md)

Обычный `tools/list` возвращает один стандартный набор из **38 инструментов**. Ниже каждый инструмент описан ровно один раз. Compatibility/test-only helpers намеренно не включены: они не являются пользовательским профилем и не должны появляться в нормальном Flow.

Классы операций:

- `local` — работает с config, supplied evidence или файлами внутри `--project-root`; DataLens не изменяет;
- `read-only API` — выполняет только чтение через DataLens Public API;
- `guarded write` — может привести к live mutation только при approval, включенных gates, fresh read и readback;
- `local command` — запускает только команду, заранее объявленную project-live manifest.

Точные JSON inputs и response contracts: [технический catalog](mcp/tools.md) и [response contracts](mcp/response_contracts.md).

## Подключение и runtime

| Инструмент | Назначение | Когда использовать | Основной input | Результат и класс | Основание |
| --- | --- | --- | --- | --- | --- |
| `dl_get_local_config` | Возвращает merged local config без secret values | Проверить project root, defaults и policy overrides | Optional config path/project root | Sanitized effective config · `local` | [Local configuration](configuration.md) |
| `dl_runtime_status` | Показывает API version, auth presence, route policy и mutation gates | Первым вызовом каждой сессии и при неожиданной блокировке | Нет обязательных inputs | Secret-safe runtime status · `local` | [Safety model](local-only-safety-model.md) |
| `dl_auth_probe` | Делает минимальный `getWorkbooksList` probe | Перед любым live read | Credentials из external env file | Auth success или sanitized blocker · `read-only API` | [Public API/auth](sources.md#public-api-contracts) |

## Чтение и discovery

| Инструмент | Назначение | Когда использовать | Основной input | Результат и класс | Основание |
| --- | --- | --- | --- | --- | --- |
| `dl_list_workbooks` | Перечисляет доступные workbooks | После успешного auth probe | Pagination/filter options | Compact workbook list · `read-only API` | `getWorkbooksList` в [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/getWorkbooksList) |
| `dl_get_workbook_entries` | Читает entries выбранного workbook | Для инвентаризации charts, datasets, connections и dashboards | `workbook_id`, response mode | Compact entries или artifact-backed full data · `read-only API` | `getWorkbookEntries` в [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/getWorkbookEntries) |
| `dl_get_entries_relations` | Возвращает relation graph для entries | Перед изменением связанных объектов и retire lifecycle | Entry IDs | Sanitized dependency graph · `read-only API` | `getEntriesRelations` в [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/getEntriesRelations) |
| `dl_read_object` | Унифицированно читает поддерживаемый object type | Когда известны type и ID конкретного объекта | `object_type`, `object_id`, branch/response mode | Compact object contract или artifact · `read-only API` | [API method map](sources.md#public-api-contracts) |
| `dl_snapshot_dashboard` | Сохраняет полный graph snapshot дашборда и связанных объектов | Перед audit, fix, redesign или backup | `dashboard_id`, branch/readback options | Sanitized snapshot artifacts и manifest · `read-only API + local` | Dashboard/object reads в [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) |

## Справка и диагностика

| Инструмент | Назначение | Когда использовать | Основной input | Результат и класс | Основание |
| --- | --- | --- | --- | --- | --- |
| `dl_validate_editor_runtime_contract` | Проверяет Advanced Editor HTML/JS и allowed `Editor.*` methods | Перед payload plan и save Editor object | Hydrated/generated Editor sections | Findings с rule/path/line · `local` | [Editor tabs и methods](sources.md#основные-официальные-страницы) |
| `dl_classify_source_error` | Разделяет auth, connection, SQL, renderer и sanitizer failures | Когда DataLens вернул sanitized error payload | `error_payload` | Stage/category/remediation · `local` | [DataLens docs + local classifier](sources.md#три-слоя-истины) |
| `dl_diagnose` | Анализирует SQL, grain, semantic graph, performance и optimization evidence | Для локализации причины ошибки или риска до apply | `mode` и bounded supplied evidence | Compact findings + artifact paths · `local` | [Local diagnostics policy](mcp/response_contracts.md#sql-and-performance-diagnostics) |
| `dl_reference` | Ищет bounded source-traced rules, recipes, formulas и API policy | Когда нужен точный route, capability, error или source trace | `mode`, query/name, char budget | До пяти rules, next tools и source metadata · `local` | [Packaged docs provenance](sources.md#документационный-snapshot) |

## Валидация и object lifecycle planning

| Инструмент | Назначение | Когда использовать | Основной input | Результат и класс | Основание |
| --- | --- | --- | --- | --- | --- |
| `dl_validate_project` | Проверяет route, bundles, payloads, SQL, privacy и dashboard contracts | До сборки live payload plan | `project_root` и validation options | Pass/blocking report · `local` | [Local policy](sources.md#три-слоя-истины) |
| `dl_build_payload_plan` | Компилирует validated artifacts в dry-run DataLens payload plan | После project/object validation | Project artifacts и target metadata | Intended methods/targets/files, без write · `local` | [API contracts + Safe Apply](safe-apply.md) |
| `dl_build_validation_evidence_report` | Разделяет static, API, save, publish и browser evidence | Перед handoff и после controlled run | Evidence/artifact paths | Proof-level report · `local` | [Proof levels](safe-apply.md#proof-levels) |
| `dl_validate_object` | Проверяет object payload по compiled API schema и safety policy | Перед create/update planner | `object_type`, payload | Schema/policy findings, без mutation · `local` | [Compiled API contracts](sources.md#public-api-contracts) |
| `dl_plan_object_create` | Строит guarded create plan для поддерживаемого object type | Для нового dashboard/chart/dataset/connection с известным location | `object_type`, named source adapter/payload | Method, compiled payload, blockers · `local` | Create methods в [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) |
| `dl_plan_object_update` | Строит update plan из fresh saved readback | Для изменения существующего объекта | `object_type`, fresh object и desired overlay | Revision-preserving update plan · `local` | Update methods + [Safe Apply](safe-apply.md) |
| `dl_plan_guarded_dataset_update` | Планирует `getDataset` → `validateDataset` → `updateDataset` → saved readback | При изменении dataset fields/model | Dataset ID, current/proposed dataset, affected chart refs | GUID preservation и blocking report · `local` | Dataset methods в [API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/validateDataset) |
| `dl_plan_dashboard_tab_update` | Добавляет или заменяет одну tab, сохраняя остальной dashboard | Для bounded tab change | Fresh dashboard, tab, replace/append intent | Minimal dashboard overlay plan · `local` | [Dashboard model](https://yandex.cloud/ru/docs/datalens/concepts/dashboard/) |
| `dl_reconcile_partial_creates` | Сопоставляет planned creates с уже появившимися entries | После uncertain/partial create перед retry | Workbook ID, planned objects, optional entries payload | Reuse/create/manual-review decisions · `read-only API + local` | Workbook inventory + [Safe Apply](safe-apply.md) |
| `dl_compile_guarded_rpc_request` | Фиксирует method, target, base revision, payload hash и readback contract | Перед передачей update в safe apply | Method, payload, fresh-read and branch metadata | Guarded RPC request artifact · `local` | [Compiled API contracts](sources.md#public-api-contracts) |

## Safe apply, save и publish

| Инструмент | Назначение | Когда использовать | Основной input | Результат и класс | Основание |
| --- | --- | --- | --- | --- | --- |
| `dl_create_safe_apply_plan` | Создает unapproved save-first plan | После validation и payload planning | Project root, targets/actions, readback mode | Guarded plan с blockers и approval state · `local` | [Safe Apply](safe-apply.md) |
| `dl_execute_safe_apply` | Выполняет approved actions с fresh read и revision preservation | Только после review и включения требуемых gates | Approved plan, runtime/tool approval | Save/publish action results и artifacts · `guarded write` | [Safe Apply](safe-apply.md) |
| `dl_create_publish_from_saved_plan` | Создает publish action только из saved readback | После успешного save и saved runtime gate, если intent допускает publish | Saved readback artifact, target/type | Plan с expected `revId`/`savedId` · `local` | [Explicit publish lane](safe-apply.md#explicit-publish-lane) |
| `dl_readback_and_report` | Читает saved/published state и создает deployment report | После save, publish или offline dry run | Targets, branch, execution/readback artifacts | Compact proof + deployment report · `read-only API + local` | [Response contract](mcp/response_contracts.md#safe-apply-savepublishreadback-plan) |

## Project-live manifest workflow

| Инструмент | Назначение | Когда использовать | Основной input | Результат и класс | Основание |
| --- | --- | --- | --- | --- | --- |
| `dl_detect_project_live_workflows` | Находит allowlisted project manifest или просит adapter | Для downstream repo с собственными scripts | `project_root` | Detected workflows или `adapter_required` · `local` | [Project workflow](project_workflow.md) |
| `dl_plan_project_manifest` | Preview manifest и optional approved local write | Когда manifest отсутствует | `project_root`, approval/write flag | Proposed manifest или записанный approved file · `local` | [Project workflow](project_workflow.md) |
| `dl_plan_project_live_workflow` | Разбирает объявленный action без выполнения | Перед dry-run/apply/retire | Project root, workflow/action | Exact argv, targets, env names, evidence checks · `local` | [Project workflow](project_workflow.md) |
| `dl_run_project_live_dry_run` | Запускает только manifest-declared dry-run в allowlisted env | После review плана и `execute_now=true` | Project/action, manifest permissions | Redacted stdout/stderr и summary pointers · `local command` | [Project-live policy](policy_vocabulary.md) |
| `dl_run_project_live_apply` | Запускает approved manifest apply/publish action за live gates | Для проекта с существующим guarded executor | Project/action, approval и runtime gates | Execution summary/evidence · `guarded write + local command` | [Project-live policy](project_workflow.md) |
| `dl_read_project_live_summary` | Нормализует declared JSON summary и проверяет evidence coverage | После dry-run/apply или для audit | Project root, action/summary path | Changed counts, branch state, blockers · `local` | [Manifest summary](policy_vocabulary.md) |

## Maintenance и source availability

| Инструмент | Назначение | Когда использовать | Основной input | Результат и класс | Основание |
| --- | --- | --- | --- | --- | --- |
| `dl_run_live_maintenance_update` | Планирует и валидирует runtime-first maintenance по supplied evidence | Для bounded fix известного live target | Target/intent, guarded execution and runtime evidence | Delivery stage/final handoff artifact; сам не пишет · `local` | [Delta v8](safe-apply.md#delta-v8-runtime-first-default) |
| `dl_build_dashboard_source_availability_matrix` | Собирает единую матрицу availability по supplied evidence | Когда tabs/charts зависят от разных source states | Source/environment/consumer evidence | `OK`/`NO_DATA`/`NO_TABLE`/`ERROR`/`UNKNOWN` rows · `local` | [Source evidence contract](mcp/response_contracts.md#sql-and-performance-diagnostics) |
| `dl_validate_source_availability_consumers` | Проверяет consumers против одной availability truth | Перед source-related publish | Matrix и consumer requirements | Conflicts и publish blockers · `local` | [Local maintenance policy](safe-apply.md) |
| `dl_plan_source_availability_patch` | Планирует bounded correction без самостоятельного query | После валидированной availability matrix | Matrix, target and desired correction | No-write patch plan · `local` | [Local maintenance policy](safe-apply.md) |

## API catalog

| Инструмент | Назначение | Когда использовать | Основной input | Результат и класс | Основание |
| --- | --- | --- | --- | --- | --- |
| `dl_list_api_methods` | Перечисляет curated DataLens methods и support status | Чтобы проверить наличие и policy операции | Optional tag/status filters | Compact method catalog · `local` | [DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/) |
| `dl_get_api_method_schema` | Возвращает bounded schema конкретного method | Перед lifecycle planning или при missing input | Method name | Request fields, support policy и doc URL · `local` | [Compiled API contracts](sources.md#public-api-contracts) |

## Что не является публичным инструментом

Raw RPC, granular route/template builders, standalone requirements helpers и DQ/data-evidence compatibility tools могут существовать в коде для tests и внутренних flows, но отсутствуют в нормальном `tools/list`. Не включайте test-only environment flags в пользовательскую конфигурацию и не стройте публичные инструкции вокруг hidden calls.
