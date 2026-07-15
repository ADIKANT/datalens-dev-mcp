# Карта требований и canvas дашборда

Шаблоны из `templates/requirements/` помогают зафиксировать требования до планирования объектов.

## Dashboard Map

Карта описывает роли, решения, процессы, состояния, источники, качество данных, метрики, разрезы, grain, связи объектов и навигацию.

## Dashboard Canvas

Canvas одного дашборда содержит цель, аудиторию, сценарии, решения, данные, метрики, визуальные блоки, селекторы, связи и критерии приёмки.

## Публичный MCP flow

1. Заполните требования в project root.
2. Используйте `dl_validate_project`, чтобы проверить полноту и связи.
3. При необходимости получите справку через `dl_reference`.
4. Создайте object plans через `dl_plan_object_create` или `dl_plan_object_update`.
5. Соберите `dl_build_payload_plan` и Safe Apply plan.
6. Выполните plan-only, save-only или полный цикл согласно пользовательскому запросу.

Отсутствующие audience, business action, freshness, metric definition, fields или relations должны приводить к точному вопросу. Селекторы указывают targets и reset/default behavior. Native title и hint сохраняются.
