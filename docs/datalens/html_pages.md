# HTML в DataLens

[English](html_pages_en.md)

Маршрут определяет потребитель: HTML внутри таблицы или чарта Editor следует [контракту Editor](../../skills/datalens-editor/references/editor-authoring.md), а отдельная Page — [контракту Page и её iframe](../../skills/datalens-maintenance/references/html-pages.md). Это разные типы объектов и среды исполнения.

Текущий интерфейс использует typed object operations. Исторический путь генерации HTML через `dl_generate_editor_bundle` / `dl_validate_editor_runtime_contract` больше не доступен. При необходимости подготовьте разрешённый локальный UTF-8 artifact; для поддерживаемых операций провайдера используйте текущие schemas и существующий защищённый lifecycle. Наличие reference не доказывает поддержку инсталляции и не создаёт upload endpoint.

Specs SDK v3.0.0 содержат Page create/get/update/delete, но `GetHtmlPageResult` возвращает metadata и `meta.objectId` без HTML content. Adapter отклоняет создание Page и изменение содержимого до отправки провайдеру, пока чтение сохранённого content нельзя проверить. Завершите разрешённый локальный artifact и укажите этот конкретный неподдерживаемый шаг.

Чтение metadata и проверенная публикация существующей точной saved revision остаются отдельными поддерживаемыми операциями. Публикация использует revision/mode в update, а не отдельный endpoint; она не доказывает, что adapter создал или прочитал content этой версии. Сохраняйте точные target/revision checks, reconciliation квитанции и readback saved/published identity.

Разделяйте локальный artifact/lint, saved state, published state и render в платформенном iframe. Локальный Browser preview не воспроизводит CSP платформы или export через host. Корректный readback metadata или revision не подтверждает HTML content и не доказывает исправление пустой Page.
