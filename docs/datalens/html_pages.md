# Генерация HTML для DataLens

[English](html_pages_en.md)

Сервер различает два несовместимых HTML-контракта:

- `Editor.generateHtml(arg)` создаёт allowlist-разметку внутри Advanced Editor
  chart. Обычная строка экранируется; теги, атрибуты, URL и тема проверяются
  контрактом Editor.
- standalone HTML page — полный UTF-8 документ для изолированного iframe. Это
  не chart и не вызов `Editor.generateHtml`.

## Быстрый путь

Передайте `html_page` существующему `dl_generate_editor_bundle`:

```json
{
  "project_root": "/absolute/project",
  "widget_id": "quality_report",
  "html_page": {
    "title": "Quality report",
    "lang": "ru",
    "summary": "Synthetic example",
    "body_html": "<main class=\"dl-page\"><h1>Quality</h1><div id=\"app\"></div></main>",
    "style_css": "#app{display:grid;gap:12px}",
    "script_js": "document.getElementById('app').textContent=String(window.datalensPage.data.value);",
    "data": {"value": 100}
  }
}
```

Результат содержит только путь, размер, SHA-256 и итог проверки. Сам HTML не
возвращается inline, поэтому размер ответа MCP не растёт вместе со страницей.
Документ сохраняется в `artifacts/html_pages/<widget_id>.html`.

Повторная проверка выполняется тем же runtime validator:

```json
{
  "project_root": "/absolute/project",
  "artifact_paths": ["artifacts/html_pages/quality_report.html"]
}
```

`dl_validate_editor_runtime_contract` распознаёт расширение `.html`
автоматически. Один документ ограничен 10 MiB, рекомендуемый предел — 5 MiB.
Эти значения измеряются в байтах локального UTF-8 artifact. Public API отдельно
ограничивает поле `content` 10 485 760 символами; перед планом проверяются оба
контракта.

## Sandbox-контракт

Генератор по умолчанию создаёт self-contained документ и добавляет:

- `theme` и `lang` из query parameters;
- `window.datalensPage.data` с безопасно встроенным JSON;
- `EXPORT` и `OPEN_URL` через `parent.postMessage`;
- responsive CSS без внешней зависимости;
- UTF-8 charset в начале документа.

Строгая проверка блокирует собственный CSP, вложенные `iframe`, `object`,
`embed`, `form` и `base`, persistent storage, cookies, network APIs, workers,
dialogs, popups и parent navigation. Разрешённые skill-контрактом CDN origins
проверяются явно; сгенерированный шаблон их не требует.

## Сохранение и публикация

Локальный генератор не выполняет live-запись сам. После строгой проверки его
content можно передать в общий lifecycle с `object_type=html_page`:

- `createHtmlPage` создаёт страницу по `key` либо по паре `workbookId` + `name`;
- `getHtmlPage` читает `saved` или `published` ветку;
- `updateHtmlPage` сохраняет новый content;
- publish отправляет только `{entryId, revId, mode: "publish"}`, собранный из
  проверенного saved readback.

Таким образом HTML Page проходит те же target/revision checks, save-first,
saved readback, publish-from-saved и published readback, что и другие
revisioned объекты. `deleteHtmlPage` остаётся заблокирован общей политикой
whole-object deletion. Source contract сообщает
`publication.status=guarded_api_available`.

Источники:

- [официальный `Editor.generateHtml`](https://yandex.cloud/ru/docs/datalens/charts/editor/methods#gen-html);
- [официальные HTML-страницы](https://yandex.cloud/ru/docs/datalens/html-pages/);
- [DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/);
- [`datalens-html-pages` public skill](https://github.com/datalens-tech/datalens-skills/tree/8fbb3aabac6b09d4c44f053fa63affea1dc386f7/skills/datalens-html-pages);
- [реализация allowlist HTML generator](https://github.com/datalens-tech/datalens-ui/tree/f581b7c31d6e9189ebeb1e1632b5fe7570534fb8/src/ui/libs/DatalensChartkit/modules/html-generator).
