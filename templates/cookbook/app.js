(() => {
  'use strict';

  const payload = JSON.parse(document.getElementById('cookbook-data').textContent);
  const base = document.body.dataset.base || './';
  const query = new URLSearchParams(window.location.search);
  const state = {
    lang: query.get('lang') === 'en' ? 'en' : 'ru',
    theme: 'light',
    viewport: 'dashboard',
    tab: '',
    filter: '',
    sourceMode: 'dataset',
    caseObject: '',
  };

  const ui = {
    ru: {
      tips: 'Советы', library: 'Визуализации', cases: 'Кейсы применения',
      subtitle: 'Готовые типизированные рецепты JavaScript для DataLens Editor',
      search: 'Найти визуализацию', preview: 'Интерактивный предпросмотр',
      synthetic: 'Синтетический локальный предпросмотр — не доказательство рендера в опубликованном DataLens',
      useCase: 'Когда использовать', behavior: 'Особенности поведения',
      sourceContract: 'Контракт Sources', alias: 'Alias', meaning: 'Назначение',
      typeFormat: 'Тип / формат', nullBehavior: 'Поведение null', example: 'Пример',
      noSource: 'Внешний источник не требуется.', code: 'Код для DataLens', support: 'Вспомогательные файлы',
      copy: 'Копировать', copied: 'Скопировано', open: 'Открыть исходник', download: 'Скачать',
      markdown: 'Markdown', parameterMap: 'Карта параметров', owner: 'Владелец', readers: 'Читатели',
      type: 'Тип', defaultValue: 'По умолчанию', purpose: 'Назначение', copyOrder: 'Объекты и порядок копирования',
      dataset: 'Dataset', clickhouse: 'ClickHouse', sourceMode: 'Режим Sources',
      emptyLibrary: 'Ничего не найдено', allRecipes: 'Все 34 самостоятельных рецепта',
      linkedCases: 'Три примера, где селекторы, чарты и таблицы используют общие Params.',
      previewError: 'Не удалось построить предпросмотр', object: 'Объект', tabs: 'Вкладки',
      whatChanges: 'Для обычного переноса замените только Meta и Sources. Необязательные настройки находятся в блоке CUSTOMIZE.',
      groups: {kpi: 'Показатели', time: 'Временные ряды', category: 'Сравнение категорий', matrix: 'Матрицы', flow: 'Потоки', distribution: 'Распределения', relationship: 'Связи', part: 'Части целого', table: 'Таблицы', selector: 'Селекторы'},
      viewports: {compact: 'Компактный', dashboard: 'Дашборд', wide: 'Широкий'},
      themes: {light: 'Светлая', dark: 'Тёмная'},
    },
    en: {
      tips: 'Tips', library: 'Visualizations', cases: 'Use cases',
      subtitle: 'Copy-ready typed JavaScript recipes for DataLens Editor',
      search: 'Find a visualization', preview: 'Interactive preview',
      synthetic: 'Synthetic local preview — not proof of rendering in published DataLens',
      useCase: 'When to use it', behavior: 'Specific behavior',
      sourceContract: 'Sources contract', alias: 'Alias', meaning: 'Purpose',
      typeFormat: 'Type / format', nullBehavior: 'Null behavior', example: 'Example',
      noSource: 'No external source is required.', code: 'DataLens code', support: 'Support files',
      copy: 'Copy', copied: 'Copied', open: 'Open source', download: 'Download',
      markdown: 'Markdown', parameterMap: 'Parameter map', owner: 'Owner', readers: 'Readers',
      type: 'Type', defaultValue: 'Default', purpose: 'Purpose', copyOrder: 'Objects and copy order',
      dataset: 'Dataset', clickhouse: 'ClickHouse', sourceMode: 'Sources mode',
      emptyLibrary: 'Nothing found', allRecipes: 'All 34 standalone recipes',
      linkedCases: 'Three examples where selectors, charts, and tables share Params.',
      previewError: 'Preview could not be built', object: 'Object', tabs: 'Tabs',
      whatChanges: 'For a normal transfer, replace only Meta and Sources. Optional settings live in the CUSTOMIZE block.',
      groups: {kpi: 'KPI', time: 'Time series', category: 'Category comparison', matrix: 'Matrices', flow: 'Flows', distribution: 'Distributions', relationship: 'Relationships', part: 'Part to whole', table: 'Tables', selector: 'Selectors'},
      viewports: {compact: 'Compact', dashboard: 'Dashboard', wide: 'Wide'},
      themes: {light: 'Light', dark: 'Dark'},
    },
  };

  function t(key) { return ui[state.lang][key]; }
  function localized(value) { return value && typeof value === 'object' ? value[state.lang] : String(value || ''); }
  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function link(path) { return `${base}${path}${path.includes('?') ? '&' : '?'}lang=${state.lang}`; }
  function currentLangUrl() {
    const url = new URL(window.location.href);
    url.searchParams.set('lang', state.lang);
    return url;
  }

  function renderTopbar() {
    document.documentElement.lang = state.lang;
    document.getElementById('topbar').innerHTML = `
      <a class="brand" href="${link('index.html')}">
        <span>JavaScript Visualization Cookbook</span><small>${esc(t('subtitle'))}</small>
      </a>
      <nav class="primary-nav" aria-label="Cookbook">
        <a class="${payload.page_type === 'tips' ? 'is-active' : ''}" href="${link('index.html')}">${esc(t('tips'))}</a>
        <a class="${['library', 'recipe'].includes(payload.page_type) ? 'is-active' : ''}" href="${link('visualizations/index.html')}">${esc(t('library'))}</a>
        <a class="${['cases_index', 'case'].includes(payload.page_type) ? 'is-active' : ''}" href="${link('cases/index.html')}">${esc(t('cases'))}</a>
      </nav>
      <button id="language-toggle" class="language-toggle" type="button">${state.lang === 'ru' ? 'EN' : 'RU'}</button>
    `;
    document.getElementById('language-toggle').addEventListener('click', () => {
      state.lang = state.lang === 'ru' ? 'en' : 'ru';
      window.history.replaceState({}, '', currentLangUrl());
      state.tab = '';
      render();
    });
  }

  function renderSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (payload.page_type === 'tips') {
      sidebar.innerHTML = `<div class="side-title">${esc(t('tips'))}</div>${payload.tips.map(item => `<a href="#${esc(item.id)}">${esc(localized(item.title))}</a>`).join('')}`;
      return;
    }
    if (payload.page_type === 'cases_index' || payload.page_type === 'case') {
      sidebar.innerHTML = `<div class="side-title">${esc(t('cases'))}</div>${payload.cases.map(item => `<a class="${payload.case && payload.case.slug === item.slug ? 'is-active' : ''}" href="${link(`cases/${item.slug}/index.html`)}">${esc(localized(item.title))}</a>`).join('')}`;
      return;
    }
    const groups = [...new Set(payload.recipes.map(item => item.group))];
    sidebar.innerHTML = `
      <label class="search"><span class="sr-only">${esc(t('search'))}</span><input id="recipe-search" value="${esc(state.filter)}" placeholder="${esc(t('search'))}"></label>
      <div id="recipe-links"></div>
    `;
    const renderLinks = () => {
      const needle = state.filter.trim().toLowerCase();
      document.getElementById('recipe-links').innerHTML = groups.map(group => {
        const items = payload.recipes.filter(item => item.group === group && (!needle || `${item.family} ${localized(item.title)} ${localized(item.summary)}`.toLowerCase().includes(needle)));
        if (!items.length) return '';
        return `<section class="side-group"><h2>${esc(t('groups')[group] || group)}</h2>${items.map(item => `<a class="${payload.recipe && payload.recipe[state.lang].slug === item.slug ? 'is-active' : ''}" href="${link(`recipes/${item.slug}/index.html`)}"><span>${esc(localized(item.title))}</span><code>${esc(item.family)}</code></a>`).join('')}</section>`;
      }).join('') || `<p class="muted">${esc(t('emptyLibrary'))}</p>`;
    };
    renderLinks();
    document.getElementById('recipe-search').addEventListener('input', event => { state.filter = event.target.value; renderLinks(); });
  }

  function renderTips() {
    document.getElementById('content').innerHTML = `
      <article class="landing"><header class="hero"><span class="kicker">JavaScript Visualization Cookbook</span><h1>${esc(t('tips'))}</h1><p>${esc(t('whatChanges'))}</p></header>
      <div class="tips-grid">${payload.tips.map((item, index) => `<section id="${esc(item.id)}" class="tip-card"><span>${String(index + 1).padStart(2, '0')}</span><h2>${esc(localized(item.title))}</h2><p>${esc(localized(item.body))}</p></section>`).join('')}</div>
      </article>`;
  }

  function renderLibrary() {
    document.getElementById('content').innerHTML = `
      <article class="landing"><header class="hero"><span class="kicker">34</span><h1>${esc(t('library'))}</h1><p>${esc(t('allRecipes'))}</p></header>
      <div class="card-grid">${payload.recipes.map(item => `<a class="catalog-card" href="${link(`recipes/${item.slug}/index.html`)}"><span>${esc(t('groups')[item.group] || item.group)}</span><h2>${esc(localized(item.title))}</h2><p>${esc(localized(item.summary))}</p><code>${esc(item.family)} · ${esc(item.variant)}</code></a>`).join('')}</div></article>`;
  }

  function renderCasesIndex() {
    document.getElementById('content').innerHTML = `
      <article class="landing"><header class="hero"><span class="kicker">3</span><h1>${esc(t('cases'))}</h1><p>${esc(t('linkedCases'))}</p></header>
      <div class="case-list">${payload.cases.map((item, index) => `<a class="case-card" href="${link(`cases/${item.slug}/index.html`)}"><span>0${index + 1}</span><div><h2>${esc(localized(item.title))}</h2><p>${esc(localized(item.summary))}</p><code>${esc(item.kind)}</code></div></a>`).join('')}</div></article>`;
  }

  function sourceTable(fields) {
    if (!fields.length) return `<p class="muted">${esc(t('noSource'))}</p>`;
    return `<div class="table-scroll"><table><thead><tr><th>${esc(t('alias'))}</th><th>${esc(t('meaning'))}</th><th>${esc(t('typeFormat'))}</th><th>${esc(t('nullBehavior'))}</th><th>${esc(t('example'))}</th></tr></thead><tbody>${fields.map(field => `<tr><td><code>${esc(field.alias)}</code><small>${field.nullable ? 'nullable' : 'required'}</small></td><td>${esc(field.meaning)}</td><td><code>${esc(field.type)}</code><br>${esc(field.format)}</td><td>${esc(field.null_behavior)}</td><td><code>${esc(JSON.stringify(field.example))}</code></td></tr>`).join('')}</tbody></table></div>`;
  }

  function fileList(recipe) {
    return [
      ...recipe.tab_order.map(name => ({name, content: recipe.tabs[name], kind: 'tab'})),
      ...Object.entries(recipe.support_files).map(([name, content]) => ({name, content, kind: 'support'})),
    ];
  }

  function renderRecipe() {
    const recipe = payload.recipe[state.lang];
    const files = fileList(recipe);
    if (!state.tab || !files.some(item => item.name === state.tab)) state.tab = files.some(item => item.name === 'sources.js') ? 'sources.js' : files[0].name;
    const current = files.find(item => item.name === state.tab);
    const codePath = `recipes/${recipe.slug}/code/${state.lang}/${current.name}`;
    document.getElementById('content').innerHTML = `
      <article class="recipe"><header class="recipe-header"><div><span class="kicker"><code>${esc(recipe.family)}</code> · ${esc(recipe.variant)} · ${esc(recipe.route)}</span><h1>${esc(recipe.title)}</h1><p>${esc(recipe.summary)}</p></div><a class="outline-button" href="${base}recipes/${esc(recipe.slug)}/README${state.lang === 'en' ? '_en' : ''}.md">${esc(t('markdown'))}</a></header>
      ${previewPanel()}
      <div class="two-column"><section class="info-card"><h2>${esc(t('useCase'))}</h2><p>${esc(recipe.use_case)}</p></section><section class="info-card"><h2>${esc(t('behavior'))}</h2><p>${esc(recipe.behavior)}</p></section></div>
      <section class="section-block"><h2>${esc(t('sourceContract'))}</h2>${sourceTable(recipe.source_contract)}</section>
      <section class="edit-note"><p>${esc(t('whatChanges'))}</p></section>
      <section class="code-section"><div class="section-heading"><h2>${esc(t('code'))}</h2></div>${codeTabs(files, current, codePath)}</section>
      </article>`;
    wirePreviewControls(() => renderRecipe());
    wireCodeControls(files, () => renderRecipe(), current);
    mountRecipePreview(recipe);
  }

  function previewPanel() {
    return `<section class="preview-panel"><div class="preview-heading"><div><h2>${esc(t('preview'))}</h2><p>${esc(t('synthetic'))}</p></div><div class="preview-switches"><div class="segmented">${Object.keys(payload.viewports).map(name => `<button data-viewport="${name}" class="${state.viewport === name ? 'is-active' : ''}">${esc(t('viewports')[name])}</button>`).join('')}</div><div class="segmented">${['light', 'dark'].map(name => `<button data-theme="${name}" class="${state.theme === name ? 'is-active' : ''}">${esc(t('themes')[name])}</button>`).join('')}</div></div></div><div id="preview-mount" class="preview-mount"></div></section>`;
  }

  function codeTabs(files, current, codePath) {
    return `<div class="code-tabs" role="tablist">${files.map(file => `<button data-code-tab="${esc(file.name)}" class="${file.name === state.tab ? 'is-active' : ''}">${esc(file.name)}</button>`).join('')}</div><div class="code-toolbar"><span>${esc(current.kind === 'support' ? t('support') : t('tabs'))}</span><div><button id="copy-code">${esc(t('copy'))}</button><a href="${base}${esc(codePath)}" target="_blank" rel="noopener">${esc(t('open'))}</a><a href="${base}${esc(codePath)}" download>${esc(t('download'))}</a></div></div><pre><code>${esc(current.content)}</code></pre>`;
  }

  function wirePreviewControls(rerender) {
    document.querySelectorAll('[data-viewport]').forEach(button => button.addEventListener('click', () => { state.viewport = button.dataset.viewport; rerender(); }));
    document.querySelectorAll('[data-theme]').forEach(button => button.addEventListener('click', () => { state.theme = button.dataset.theme; rerender(); }));
  }

  function wireCodeControls(files, rerender, current) {
    document.querySelectorAll('[data-code-tab]').forEach(button => button.addEventListener('click', () => { state.tab = button.dataset.codeTab; rerender(); document.querySelector('.code-section').scrollIntoView({block: 'start'}); }));
    const copy = document.getElementById('copy-code');
    if (copy) copy.addEventListener('click', async () => { await copyText(current.content); copy.textContent = t('copied'); window.setTimeout(() => { copy.textContent = t('copy'); }, 1200); });
  }

  async function copyText(value) {
    if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(value); return; }
    const node = document.createElement('textarea'); node.value = value; node.setAttribute('readonly', ''); node.style.position = 'fixed'; node.style.opacity = '0'; document.body.appendChild(node); node.select(); document.execCommand('copy'); node.remove();
  }

  function mountRecipePreview(recipe) {
    const viewport = payload.viewports[state.viewport];
    const frame = document.createElement('iframe');
    frame.className = 'preview-frame'; frame.title = `${recipe.title} preview`; frame.setAttribute('sandbox', 'allow-scripts');
    frame.style.width = `${Math.min(viewport.width, 960)}px`; frame.style.height = `${viewport.height}px`;
    frame.srcdoc = recipePreviewDocument({
      lang: state.lang, route: recipe.route, theme: state.theme, width: viewport.width, height: viewport.height,
      tabs: recipe.tabs, fixture_rows: recipe.fixture_rows, source_columns: recipe.source_contract.map(field => field.alias),
      params: recipe.params, error_label: t('previewError'),
    });
    document.getElementById('preview-mount').appendChild(frame);
  }

  function commonPreviewHead(lang, theme) {
    return `<html lang="${lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
      :root{color-scheme:light;--g-color-base-background:#fff;--g-color-base-float:#fff;--g-color-base-generic:#f2f4f7;--g-color-base-generic-medium:#eef2f6;--g-color-base-neutral-light:#f2f4f7;--g-color-text-primary:#111827;--g-color-text-secondary:#667085;--g-color-text-hint:#98a2b3;--g-color-line-generic:#e5e7eb;--g-color-base-positive-light:#e6f4ea;--g-color-base-warning-light:#fff4e5;--g-color-base-danger-light:#fdecec;--g-color-text-positive:#0b8043;--g-color-text-warning:#9a6700;--g-color-text-danger:#b3261e}
      :root[data-theme="dark"]{color-scheme:dark;--g-color-base-background:#15171a;--g-color-base-float:#202328;--g-color-base-generic:#292d33;--g-color-base-generic-medium:#30353d;--g-color-base-neutral-light:#30353d;--g-color-text-primary:#f5f7fa;--g-color-text-secondary:#bdc5d1;--g-color-text-hint:#8b95a5;--g-color-line-generic:#3c424c;--g-color-base-positive-light:#173c2a;--g-color-base-warning-light:#443319;--g-color-base-danger-light:#472123;--g-color-text-positive:#65d799;--g-color-text-warning:#f1bd63;--g-color-text-danger:#ff8588}
      *{box-sizing:border-box}html,body,#root{width:100%;height:100%;margin:0}body{background:var(--g-color-base-background);color:var(--g-color-text-primary);font-family:Arial,sans-serif;overflow:hidden}.error{height:100%;display:grid;place-items:center;padding:18px;color:var(--g-color-text-danger);background:var(--g-color-base-danger-light);font:600 12px/1.45 ui-monospace,monospace;white-space:pre-wrap}.table-wrap{height:100%;overflow:auto;padding:10px}.native-table{min-width:100%;border-collapse:separate;border-spacing:0;font-size:12px}.native-table th,.native-table td{padding:8px 10px;border-right:1px solid var(--g-color-line-generic);border-bottom:1px solid var(--g-color-line-generic);text-align:left;white-space:nowrap;background:var(--g-color-base-background)}.native-table th{position:sticky;top:0;z-index:3;background:var(--g-color-base-generic);color:var(--g-color-text-secondary)}.native-table .pinned{position:sticky;left:0;z-index:2;background:var(--g-color-base-float)}.native-table th.pinned{z-index:4;background:var(--g-color-base-generic)}.bar-cell{position:relative;min-width:120px}.bar-cell i{position:absolute;inset:4px auto 4px 0;background:#2b75e2;opacity:.22}.bar-cell span{position:relative}.status-pill{padding:3px 7px;border-radius:999px;background:var(--g-color-base-generic);font-weight:700}.controls{height:100%;display:flex;align-content:flex-start;align-items:flex-start;gap:10px;flex-wrap:wrap;padding:16px}.control{display:grid;grid-template-columns:minmax(76px,auto) minmax(110px,1fr);align-items:center;gap:8px;min-height:40px}.control label{font-size:12px;color:var(--g-color-text-secondary)}.control select,.control input{width:100%;min-height:36px;border:1px solid var(--g-color-line-generic);border-radius:6px;background:var(--g-color-base-float);color:var(--g-color-text-primary);padding:7px 9px}.tooltip{position:fixed;z-index:10;display:none;max-width:calc(100vw - 16px);pointer-events:none;filter:drop-shadow(0 8px 22px rgba(15,23,42,.18))}
    </style></head><body><div id="root"></div><div id="tooltip" class="tooltip"></div>`;
  }

  function encodedPayload(value) { return JSON.stringify(value).replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026'); }

  function recipePreviewDocument(value) {
    return `<!doctype html>${commonPreviewHead(value.lang, value.theme)}<script id="payload" type="application/json">${encodedPayload(value)}</script><script>
      (()=>{'use strict';const payload=JSON.parse(document.getElementById('payload').textContent);document.documentElement.dataset.theme=payload.theme;const root=document.getElementById('root');const tooltip=document.getElementById('tooltip');const params={...(payload.params||{}),theme:[payload.theme]};const events=[{event:'metadata',data:{names:payload.source_columns}},...payload.fixture_rows.map(row=>({event:'row',data:payload.source_columns.map(name=>row[name]===undefined?null:row[name])}))];const Editor={getLoadedData:()=>({rows:events}),getParams:()=>params,getParam:name=>params[name]||[],getId:name=>name,wrapFn:value=>value,generateHtml:value=>String(value==null?'':value)};${previewRuntimeSource()}try{renderRoute(payload.route,payload.tabs,payload.width,payload.height,Editor,root,tooltip);}catch(error){root.innerHTML='<div class="error">'+escapeHtml(payload.error_label+': '+(error&&error.message||error))+'</div>';}})();
    </script></body></html>`;
  }

  function previewRuntimeSource() {
    return `
      function execute(source,Editor){const module={exports:{}};new Function('module','exports','Editor','require',source)(module,module.exports,Editor,name=>{if(name==='libs/dataset/v2')return{buildSource:value=>value};throw new Error('Unsupported require: '+name)});return module.exports;}
      function escapeHtml(value){return String(value==null?'':value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
      function flatHead(head){const result=[];(head||[]).forEach(item=>{if(Array.isArray(item.sub))result.push(...flatHead(item.sub));else result.push(item)});return result;}
      function renderTable(result,root){const heads=flatHead(result.head);const rows=Array.isArray(result.rows)?result.rows:[];const maximum=Math.max(1,...rows.flatMap(row=>(row.cells||[]).map(cell=>Number(cell.value)||0)));root.innerHTML='<div class="table-wrap"><table class="native-table"><thead><tr>'+heads.map(head=>'<th class="'+(head.pinned?'pinned':'')+'" title="'+escapeHtml(head.hint||'')+'">'+escapeHtml(head.name||head.id)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+(row.cells||[]).map((cell,index)=>{const head=heads[index]||{};const text=cell.formattedValue==null?cell.value:cell.formattedValue;if(head.type==='bar'||head.type==='progress'){const width=Math.max(0,Math.min(100,(Number(cell.value)||0)/(Number(head.max)||maximum)*100));return '<td class="bar-cell"><i style="width:'+width+'%"></i><span>'+escapeHtml(text)+'</span></td>'}if(head.type==='link'&&/^https:\\/\\//i.test(String(cell.href||cell.value||'')))return '<td><a href="'+escapeHtml(cell.href||cell.value)+'" target="_blank" rel="noopener">'+escapeHtml(text||'Open')+'</a></td>';if(head.type==='status')return '<td><span class="status-pill">'+escapeHtml(text)+'</span></td>';return '<td class="'+(head.pinned?'pinned':'')+'">'+escapeHtml(text)+'</td>'}).join('')+'</tr>').join('')+'</tbody></table></div>';}
      function renderControls(result,root){const controls=Array.isArray(result.controls)?result.controls:[];root.innerHTML='<div class="controls">'+controls.map(control=>{const width=String(control.width||'94%');if(control.type==='range-datepicker')return '<div class="control" style="width:'+escapeHtml(width)+'"><label>'+escapeHtml(control.label)+'</label><span style="display:flex;gap:6px"><input aria-label="From"><input aria-label="To"></span></div>';const options=(control.content||[]).map(item=>'<option value="'+escapeHtml(item.value)+'">'+escapeHtml(item.title)+'</option>').join('');return '<div class="control" style="width:'+escapeHtml(width)+'"><label>'+escapeHtml(control.label)+'</label><select '+(control.multiselect?'multiple':'')+'>'+options+'</select></div>'}).join('')+'</div>';}
      function wireTooltip(exported,root,tooltip){const renderer=exported&&exported.tooltip&&exported.tooltip.renderer;if(!renderer||typeof renderer.fn!=='function')return;root.addEventListener('pointermove',event=>{const target=event.target.closest&&event.target.closest('[data-id]');if(!target){tooltip.style.display='none';return}const value=renderer.fn({target},...renderer.args);if(!value){tooltip.style.display='none';return}tooltip.innerHTML=value;tooltip.style.display='block';tooltip.style.left=Math.min(Math.max(8,window.innerWidth-330),Math.max(8,event.clientX+12))+'px';tooltip.style.top=Math.min(Math.max(8,window.innerHeight-190),Math.max(8,event.clientY+12))+'px'});root.addEventListener('pointerleave',()=>{tooltip.style.display='none'});}
      function renderRoute(route,tabs,width,height,Editor,root,tooltip){if(route==='editor_advanced'){const exported=execute(tabs['prepare.js'],Editor);if(!exported.render||typeof exported.render.fn!=='function')throw new Error('prepare.js has no render');root.innerHTML=exported.render.fn({width,height},...exported.render.args);wireTooltip(exported,root,tooltip);return}if(route==='editor_table'){renderTable(execute(tabs['prepare.js'],Editor),root);return}if(route==='editor_js_control'){renderControls(execute(tabs['controls.js'],Editor),root);return}throw new Error('Unsupported route: '+route);}
    `;
  }

  function renderCase() {
    const caseData = payload.case;
    if (!state.caseObject || !caseData.objects.some(item => item.id === state.caseObject)) state.caseObject = caseData.objects[0].id;
    const object = caseData.objects.find(item => item.id === state.caseObject);
    const localizedObject = object.localized[state.lang];
    const tabs = localizedObject.modes[state.sourceMode];
    const files = Object.entries(tabs).map(([name, content]) => ({name, content, kind: 'tab'}));
    if (!state.tab || !files.some(item => item.name === state.tab)) state.tab = files.some(item => item.name === 'sources.js') ? 'sources.js' : files[0].name;
    const current = files.find(item => item.name === state.tab);
    const codePath = `cases/${caseData.slug}/objects/${object.id}/${state.sourceMode}/code/${state.lang}/${current.name}`;
    document.getElementById('content').innerHTML = `
      <article class="case-page"><header class="recipe-header"><div><span class="kicker"><code>${esc(caseData.kind)}</code></span><h1>${esc(caseData.title[state.lang])}</h1><p>${esc(caseData.summary[state.lang])}</p></div><a class="outline-button" href="${base}cases/${esc(caseData.slug)}/README${state.lang === 'en' ? '_en' : ''}.md">${esc(t('markdown'))}</a></header>
      ${previewPanel()}
      <section class="section-block"><h2>${esc(t('parameterMap'))}</h2>${parameterTable(caseData.params)}</section>
      <section class="section-block"><div class="section-heading"><h2>${esc(t('copyOrder'))}</h2><div><span class="mode-label">${esc(t('sourceMode'))}</span><div class="segmented">${caseData.source_modes.map(mode => `<button data-source-mode="${mode}" class="${state.sourceMode === mode ? 'is-active' : ''}">${esc(t(mode))}</button>`).join('')}</div></div></div><div class="object-tabs">${caseData.objects.map(item => `<button data-case-object="${esc(item.id)}" class="${item.id === state.caseObject ? 'is-active' : ''}"><span>${esc(item.localized[state.lang].title)}</span><code>${esc(item.route)}</code></button>`).join('')}</div>${sourceTable(localizedObject.source_contract)}</section>
      <section class="code-section"><div class="section-heading"><h2>${esc(localizedObject.title)} · ${esc(t(state.sourceMode))}</h2></div>${codeTabs(files, current, codePath)}</section>
      </article>`;
    wirePreviewControls(() => renderCase());
    document.querySelectorAll('[data-source-mode]').forEach(button => button.addEventListener('click', () => { state.sourceMode = button.dataset.sourceMode; state.tab = 'sources.js'; renderCase(); }));
    document.querySelectorAll('[data-case-object]').forEach(button => button.addEventListener('click', () => { state.caseObject = button.dataset.caseObject; state.tab = 'sources.js'; renderCase(); }));
    wireCodeControls(files, () => renderCase(), current);
    mountCasePreview(caseData);
  }

  function parameterTable(params) {
    return `<div class="table-scroll"><table><thead><tr><th>Param</th><th>${esc(t('owner'))}</th><th>${esc(t('readers'))}</th><th>${esc(t('type'))}</th><th>${esc(t('defaultValue'))}</th><th>${esc(t('purpose'))}</th></tr></thead><tbody>${params.map(item => `<tr><td><code>${esc(item.name)}</code></td><td><code>${esc(item.owner)}</code></td><td>${item.readers.map(value => `<code>${esc(value)}</code>`).join(' ')}</td><td><code>${esc(item.type)}</code></td><td><code>${esc(JSON.stringify(item.default))}</code></td><td>${esc(item.purpose[state.lang])}</td></tr>`).join('')}</tbody></table></div>`;
  }

  function mountCasePreview(caseData) {
    const viewport = payload.viewports[state.viewport];
    const objects = caseData.objects.map(item => ({id:item.id,route:item.route,role:item.role,title:item.localized[state.lang].title,source_contract:item.localized[state.lang].source_contract,tabs:item.localized[state.lang].modes.dataset}));
    const frame = document.createElement('iframe'); frame.className='preview-frame case-preview-frame'; frame.title=`${caseData.title[state.lang]} preview`; frame.setAttribute('sandbox','allow-scripts'); frame.style.width=`${Math.min(viewport.width,960)}px`; frame.style.height=`${Math.max(640,viewport.height*2)}px`;
    frame.srcdoc = casePreviewDocument({lang:state.lang,kind:caseData.kind,theme:state.theme,width:viewport.width,height:viewport.height,params:caseData.params,objects,error_label:t('previewError')});
    document.getElementById('preview-mount').appendChild(frame);
  }

  function casePreviewDocument(value) {
    return `<!doctype html>${commonPreviewHead(value.lang,value.theme)}<style>body{overflow:auto}.case-root{padding:10px;display:grid;gap:10px}.case-controls{min-height:92px;border:1px solid var(--g-color-line-generic);border-radius:10px;overflow:hidden}.case-widgets{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.case-widget{height:${Math.max(220, Math.min(340, value.height))}px;border:1px solid var(--g-color-line-generic);border-radius:10px;overflow:hidden;background:var(--g-color-base-background)}.case-widget[data-route="editor_table"]{grid-column:1/-1}.case-widget h2{height:34px;margin:0;padding:9px 11px;font-size:12px;color:var(--g-color-text-secondary);border-bottom:1px solid var(--g-color-line-generic)}.case-widget>div{height:calc(100% - 34px)}@media(max-width:520px){.case-widgets{grid-template-columns:1fr}.case-widget{grid-column:1!important}}</style><script id="payload" type="application/json">${encodedPayload(value)}</script><script>
      (()=>{'use strict';const payload=JSON.parse(document.getElementById('payload').textContent);document.documentElement.dataset.theme=payload.theme;const root=document.getElementById('root');root.className='case-root';const confirmed=Object.fromEntries(payload.params.map(item=>[item.name,[...item.default]]));confirmed.theme=[payload.theme];const draft={from:(confirmed.dateFrom||[])[0]||'',to:(confirmed.dateTo||[])[0]||''};let loadedRows=[];const Editor={getLoadedData:()=>({rows:loadedRows}),getParams:()=>confirmed,getParam:name=>confirmed[name]||[],updateParams:patch=>{Object.entries(patch||{}).forEach(([key,value])=>{confirmed[key]=Array.isArray(value)?value:[value]});renderVisuals()},getId:name=>name,wrapFn:value=>value,generateHtml:value=>String(value==null?'':value)};${previewRuntimeSource()}
      function sourceEvents(fields,rows){const names=fields.map(item=>item.alias);return[{event:'metadata',data:{names}},...rows.map(row=>({event:'row',data:names.map(name=>row[name]===undefined?null:row[name])}))]}
      function days(){const from=new Date((confirmed.dateFrom||[])[0]);const to=new Date((confirmed.dateTo||[])[0]);const value=Math.floor((to-from)/86400000)+1;return Number.isFinite(value)&&value>0?value:30}
      function step(){const requested=String((confirmed.timeStep||['auto'])[0]);if(requested!=='auto')return requested;return days()<=14?'day':days()<=60?'week':'month'}
      function factor(){return 1+((confirmed.category||[]).length?0.18:0)+((confirmed.status||[]).length?0.11:0)}
      function rowsFor(role){const f=factor();if(payload.kind==='period_comparison'){if(role==='kpi')return[{current_value:Math.round((118+days()*.7)*10)/10,comparator_value:Math.round((108+days()*.55)*10)/10}];if(role==='trend'){const s=step();const count=s==='day'?7:s==='week'?8:6;const current=payload.lang==='ru'?'Текущий период':'Current period';const comparison=payload.lang==='ru'?'Сравнение':'Comparison';return Array.from({length:count},(_,index)=>[{bucket:s+' '+(index+1),metric:current,value:42+index*5+(index%3)*3},{bucket:s+' '+(index+1),metric:comparison,value:38+index*4+(index%2)*2}]).flat()}}
        if(payload.kind==='filters_detail'){if(role==='summary'){const cur=payload.lang==='ru'?'Текущий':'Current';const cmp=payload.lang==='ru'?'Сравнение':'Comparison';return['A','B','C'].flatMap((label,index)=>[{label:'Category '+label,group:cur,value:Math.round((72-index*14)*f)},{label:'Category '+label,group:cmp,value:Math.round((63-index*12)*f)}])}if(role==='detail')return Array.from({length:6},(_,index)=>({entity_id:'OBJ-'+(1042+index),entity_name:(payload.lang==='ru'?'Объект ':'Object ')+(1042+index),status:index%3?'ready':'warning',owner:index%2?(payload.lang==='ru'?'Команда A':'Team A'):null,updated_at:'2026-01-'+String(10+index).padStart(2,'0')+'T12:30:00Z',amount:Math.round((780+index*135)*f)}))}
        if(payload.kind==='status_monitoring'){if(role==='kpi')return[{current_value:Math.round(128*f)}];if(role==='heatmap'){const xs=payload.lang==='ru'?['Пн','Вт','Ср']:['Mon','Tue','Wed'];const ys=payload.lang==='ru'?['Утро','Вечер']:['Morning','Evening'];return ys.flatMap((group,y)=>xs.map((label,x)=>({label,group,value:Math.round((18+x*13+y*27)*f),target:0})))}if(role==='status_table')return Array.from({length:5},(_,index)=>({entity_id:'CHK-'+(201+index),item:(payload.lang==='ru'?'Проверка ':'Check ')+(index+1),status:index%3===0?'warning':'ready',updated_at:'2026-01-'+String(15+index).padStart(2,'0')+'T10:00:00Z',details_url:'https://example.invalid/item/'+(201+index)}))}return[]}
      function renderControlsObject(object){loadedRows=[];const exported=execute(object.tabs['controls.js'],Editor);const controls=exported.controls||[];const mount=document.createElement('div');mount.className='case-controls';mount.innerHTML='<div class="controls">'+controls.map((control,index)=>{if(control.type==='range-datepicker')return '<div class="control" style="width:'+escapeHtml(control.width||'94%')+'"><label>'+escapeHtml(control.label)+'</label><span style="display:flex;gap:6px"><input data-range="from" type="date" value="'+escapeHtml(draft.from)+'"><input data-range="to" type="date" value="'+escapeHtml(draft.to)+'"></span></div>';const options=(control.content||[]).map(item=>'<option value="'+escapeHtml(item.value)+'" '+((confirmed[control.param]||[]).includes(item.value)?'selected':'')+'>'+escapeHtml(item.title)+'</option>').join('');return '<div class="control" style="width:'+escapeHtml(control.width||'46%')+'"><label>'+escapeHtml(control.label)+'</label><select data-control="'+index+'" '+(control.multiselect?'multiple':'')+'>'+options+'</select></div>'}).join('')+'</div>';mount.querySelectorAll('[data-range]').forEach(input=>input.addEventListener('input',()=>{draft[input.dataset.range]=input.value;if(/^\\d{4}-\\d{2}-\\d{2}$/.test(draft.from)&&/^\\d{4}-\\d{2}-\\d{2}$/.test(draft.to)&&draft.from<=draft.to){confirmed.dateFrom=[draft.from];confirmed.dateTo=[draft.to];renderVisuals()}}));mount.querySelectorAll('[data-control]').forEach(select=>select.addEventListener('change',()=>{const control=controls[Number(select.dataset.control)];const values=select.multiple?[...select.selectedOptions].map(item=>item.value).filter(Boolean):[select.value].filter(Boolean);confirmed[control.param]=values;renderVisuals()}));root.appendChild(mount)}
      function renderVisuals(){const widgets=root.querySelector('.case-widgets');if(!widgets)return;widgets.innerHTML='';payload.objects.filter(item=>item.role!=='controls').forEach(object=>{const shell=document.createElement('section');shell.className='case-widget';shell.dataset.route=object.route;shell.innerHTML='<h2>'+escapeHtml(object.title)+'</h2><div></div>';const mount=shell.lastElementChild;const tooltip=document.createElement('div');tooltip.className='tooltip';shell.appendChild(tooltip);try{loadedRows=sourceEvents(object.source_contract,rowsFor(object.role));renderRoute(object.route,object.tabs,payload.width,Math.max(180,payload.height-34),Editor,mount,tooltip)}catch(error){mount.innerHTML='<div class="error">'+escapeHtml(payload.error_label+': '+(error&&error.message||error))+'</div>'}widgets.appendChild(shell)})}
      try{const controls=payload.objects.find(item=>item.role==='controls');if(controls)renderControlsObject(controls);const widgets=document.createElement('div');widgets.className='case-widgets';root.appendChild(widgets);renderVisuals()}catch(error){root.innerHTML='<div class="error">'+escapeHtml(payload.error_label+': '+(error&&error.message||error))+'</div>'}})();
    </script></body></html>`;
  }

  function render() {
    renderTopbar(); renderSidebar();
    if (payload.page_type === 'tips') renderTips();
    else if (payload.page_type === 'library') renderLibrary();
    else if (payload.page_type === 'cases_index') renderCasesIndex();
    else if (payload.page_type === 'recipe') renderRecipe();
    else if (payload.page_type === 'case') renderCase();
  }

  render();
})();
