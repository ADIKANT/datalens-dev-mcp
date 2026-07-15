# Модель выбора операции DataLens

Основное руководство: [`docs/route-policy.md`](../route-policy.md). Правила хранятся в `config/route_selection_policy_v5.json`.

Сначала сервер определяет вид операции, затем технологию чарта.

| Вид операции | Route | Объект |
| --- | --- | --- |
| Стандартный чарт | `wizard_native` | `wizard_chart` |
| Явно запрошенный JavaScript | `editor_advanced` | `editor_chart` |
| Специализированная JavaScript-таблица | `editor_table` | `editor_chart` |
| Markdown | `editor_markdown` | `editor_chart` |
| JavaScript-контрол | `editor_js_control` | `editor_chart` |
| Прямой запрос QL | `ql_explicit` | `ql_chart` |
| Датасет | `dataset_operation` | `dataset` |
| Подключение | `connector_operation` | `connection` |
| Вкладки, layout и связи | `dashboard_relation_operation` | `dashboard` |

Порядок выбора:

1. Сохранить технологию и visualization ID существующего объекта из актуального readback.
2. Учесть прямой запрос Wizard, JavaScript или QL.
3. Направить connection/dataset/dashboard relation в соответствующий object route.
4. Использовать Editor для документированной возможности, отсутствующей у подходящего Wizard-чарта.
5. Для остальных стандартных чартов выбрать Wizard.
6. При недостатке цели, метрики или структуры данных задать точный вопрос.

QL выбирается только по прямому запросу и использует явный payload или актуальный saved seed. Вычисляемые поля находятся в dataset config. Обязательные поля чарта проверяются по схеме датасета, когда она доступна.
