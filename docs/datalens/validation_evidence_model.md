# Модель подтверждения результата

`dl_build_validation_evidence_report` фиксирует, что именно было проверено:

- синтаксис JavaScript и статический SQL lint;
- dashboard payload и layout;
- план Safe Apply и target lock;
- summary проектного dry-run;
- saved readback;
- published readback;
- чтение Editor-объекта и layout дашборда;
- проверка изменённой вкладки или объекта в DataLens;
- матрица доступности источников;
- результаты чтения схем или данных из разрешённого read-only источника;
- уровни подтверждения и оставшиеся ручные проверки.

Уровни подтверждения:

- `source_static`;
- `installed_static`;
- `live_read_only_api`;
- `save_readback`;
- `publish_readback`;
- `browser_rendered`;
- `controlled_live_write`.

Если прямое выполнение SQL не поддерживается выбранным методом, отчёт фиксирует статический lint, сгенерированный запрос, API-readback и рекомендуемую проверку DataLens. Отсутствие engine evidence помечается как неподтверждённый этап, а не как успешное выполнение.

API-readback подтверждает структуру объекта. Видимое изменение считается проверенным в runtime после проверки изменённой вкладки или объекта в DataLens. Если такая проверка недоступна, итоговый статус — `runtime_not_verified`.

Browser evidence версии `datalens.browser_capture.v2` фиксирует
`change_scope`. Для `content` достаточно одного viewport. Для `layout` и
`dashboard` обязательны разные compact (`<=1280`) и wide (`>=1366`) профили.
Каждый профиль подтверждает размеры viewport, привязку изменённых ID,
отсутствие горизонтального overflow более 2 px, видимость без clipping и
декодируемый screenshot с совпадающим SHA-256.

Версия `datalens.browser_capture.v3` сохраняет этот контракт и дополнительно
требует для каждого viewport явные массивы `truncated_text_object_ids` и
`overlap_pairs`. Для успешного evidence оба массива пусты. Наличие обрезанного
текста или пересечения объектов блокирует visual runtime gate. V1/V2 остаются
доступны для чтения исторических evidence.
