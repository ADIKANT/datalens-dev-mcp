# Installed public autonomy canary

[Русский](#русский) · [English](#english) · [Project home](../README_en.md)

## Русский

Этот canary доказывает автономный цикл через установленный wheel и публичный
stdio MCP-контракт. Runner не импортирует внутренние API, pipeline, editor,
`WorkflowEngine`, `ProjectJournal` или Safe Apply. Он принимает только заранее
выбранный dedicated dashboard, точные object/tab ID и явные флаги разрешённой
live-записи.

Успешный прогон обязан:

1. проверить чистый frozen Git head и источник установленного пакета `0.5.0`;
2. увидеть ровно восемь инструментов `autonomous-v2`;
3. построить hash-bound план для одного изменения
   `/data/supportDescription`;
4. выполнить ровно один save и saved readback;
5. остановить stdio-процесс, запустить новый и продолжить ту же задачу;
6. выполнить ровно один publish из сохранённого состояния и published readback;
7. подтвердить typed `getDatasetData` evidence без raw rows inline;
8. подтвердить ноль browser-вызовов при политике `forbidden`;
9. доказать ноль записей для заранее подготовленного stale-revision плана;
10. записать schema-valid receipt с hash исходников и доказательств.

Пример команды использует placeholders, а не реальные идентификаторы:

```bash
python3 scripts/run_public_autonomy_canary.py \
  --python /absolute/path/to/installed-venv/bin/python \
  --project-root /absolute/path/to/canary-project \
  --target-url https://datalens.example/DASHBOARD_ID \
  --object-id DASHBOARD_ID \
  --tab-id TAB_ID \
  --env-file /absolute/path/to/env \
  --expected-head GIT_HEAD \
  --marker "controlled public autonomy canary" \
  --out artifacts/autonomy/public-autonomy-canary.json \
  --allow-live-writes \
  --confirm-dedicated-target
```

Canary не удаляет объект и оставляет ограниченный marker на dedicated target.
Повторять завершённый прогон на том же target нельзя: один новый контролируемый
прогон предназначен для одного frozen release candidate.

## English

This canary proves the autonomous workflow through an installed wheel and the
public stdio MCP contract. The runner does not import internal API, pipeline,
editor, `WorkflowEngine`, `ProjectJournal`, or Safe Apply implementation code.
It accepts only a preselected dedicated dashboard, exact object/tab IDs, and
explicit live-write flags.

A successful run must verify a clean frozen Git head, exactly eight
`autonomous-v2` tools, one save plus saved readback, a process restart, one
publish from saved state plus published readback, typed bounded dataset proof,
zero browser calls under the forbidden policy, and zero stale-plan writes. The
schema-valid receipt binds the installed build, source tree, immutable plan,
target/style bindings, and evidence artifacts by hash.

`getDatasetData` remains an experimental read-only provider route without
saved/published revision semantics. The canary consumes its normalized typed
profile and explicit sampling limitations; it never embeds raw sampled rows in
the receipt.
