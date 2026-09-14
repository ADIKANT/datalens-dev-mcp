# Прямые операции DataLens

[English](usage-flow_en.md) · [Подключение](codex_setup.md) · [Инструменты](tools.md)

Работайте из точного dashboard project/subproject через установленный domain skill. Начните с указанного объекта; используйте уже известные installation и runtime. `dl_server_info` нужен при неизвестном или изменившемся runtime, `dl_auth_check` — для проверки доступа. SDK/reference читайте адресно при неизвестном контракте или версии.

| Задача | Короткий маршрут и достаточная проверка |
| --- | --- |
| Вопрос о metadata | `dl_object_get` с summary/projection нужных полей → ответ. Inventory и relations только по необходимости |
| Описание или другая точечная metadata-правка | Полный saved target → узкий patch через `dl_object_update` → saved readback из результата операции |
| Dataset: поле, формула, фильтр, source | [Dataset/Wizard](../skills/datalens-dataset-wizard/SKILL.md): сохранить неизвестные поля и обе revision; применимые validation/preview → update/readback |
| Одна вкладка Editor | [Editor](../skills/datalens-editor/SKILL.md): сохранить остальные tabs/aliases → validation изменённого source → update/readback → Browser при изменении поведения или вида |
| Dashboard filter/layout/composition | [Dashboard](../skills/datalens-dashboard/SKILL.md): прочитать затронутые bindings/dependencies, сохранить соседей → validate/update/readback → проверить фильтр/геометрию в Browser |
| Shared renderer | Изменять в его source project в разрешённом scope; проверить затронутое семейство и потребителей. Не применять этот цикл к одиночной metadata-правке |

Для нового стандартного чарта предпочтителен Wizard; существующая технология сохраняется. Для зарегистрированного Editor recipe используйте `dl_authoring_defaults` → `dl_compile_recipe`; передавайте компактный `draft_reference` в validation/create, а artifact path с точной identity/revision — в update. Не воспроизводите packaged JavaScript в ответе. При новой композиции проверьте batch через `dl_editor_validate`, создайте зависимости по порядку и передайте `visual_contract` в item `presentation`.

`dl_object_diff` опционален: он читает один target и возвращает изменённые пути/значения. `include_proposed=true` добавляет полный proposed snapshot, если он действительно нужен. Полные данные в MCP находятся в `structuredContent`; text для object/snapshot/diff содержит краткое описание. Не запускайте workbook graph scan после точечного update.

Operation result содержит identity, status, изменённые поля, revision и границу readback. `no_change` означает совпадение намерения со свежим saved state без внешней записи. Полные redacted детали доступны по `detail_reference` через `dl_operation_get(include_detail=true)`. Повторное чтение нужно при неразрешённой детали или drift, а не автоматически для получения уже подтверждённой revision.

Правила разрешения, save-only, публикации и unknown write находятся в [границах поручения и доставки](../skills/datalens-dashboard/references/authorized-scope.md). Запрошенная публикация выполняется через `dl_object_publish` из saved revision и подтверждается published readback. Dataset/Connection не имеют отдельной publish branch. Неопределённый результат требует `dl_operation_reconcile`, а не повторной записи.

JSON/static validation доказывает локальный контракт, но не смысл метрики и render. Data preview нужен при затронутых данных; Browser read-only — при затронутом отображении/поведении, после API и применимых data checks. Metadata-only, read-only и packaging не требуют визуального цикла. Для KPI, времени, шкал и композиции читайте только применимый раздел [visualization decisions](../skills/datalens-dashboard/references/decision-quality.md).

Backup, scoped cleanup и standalone HTML Page относятся к [Maintenance](../skills/datalens-maintenance/SKILL.md). Page content create/update остаётся недоступным без доказанного content readback. Пакетный smoke и fake-HTTP сценарии — локальная защита контракта; фактически пройденная DataLens-задача требует наблюдаемого результата на разрешённом объекте. Недоступную live-проверку укажите отдельно.
