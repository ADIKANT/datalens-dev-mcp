/*
 * Advanced Editor template contract:
 * - Source/data contract: rows expose resource, interval, status, and optional link fields.
 * - Params/config: explicit request, timezone, as_of, limits, and canceled statuses are injected.
 * - Prepare/model normalization: timestamps, ordering, lanes, conflicts, and caps are deterministic.
 * - Render lifecycle: render is exported only as Editor.wrapFn and returns Editor.generateHtml.
 * - Layout/scales: interval positions use the validated bounded time range and deterministic lanes.
 * - Labels/tooltips: item, status, conflict, and anomaly labels remain readable without guessed data.
 * - Theme tokens: colors and spacing come from shared HOUSE_STYLE tokens.
 * - Interactions: only validated safe links are interactive; rejected links remain plain text.
 * - Extension points: change schema, params, or shared helpers before adding ad hoc behavior.
 */
/*
 * Explicit-only resource schedule contract:
 * - source timestamps require Z or a numeric offset;
 * - timezone and as_of are injected, never read from the browser clock;
 * - lanes and conflicts are deterministic and bounded;
 * - any invalid input or cap breach produces a table_node fallback model.
 */
/* __DATALENS_SHARED_STYLE_TOKENS__ */
/* __DATALENS_SHARED_RENDER_HELPERS__ */

const params = Editor.getParams ? (Editor.getParams() || {}) : {};
function paramValue(name, fallback) {
  const value = params[name];
  if (Array.isArray(value)) return value.length ? value[0] : fallback;
  return value == null || value === '' ? fallback : value;
}
function paramList(name, fallback) {
  const value = params[name];
  if (Array.isArray(value)) return value.flat().map((item) => String(item).toLowerCase());
  if (value == null || value === '') return fallback;
  return String(value).split(',').map((item) => item.trim().toLowerCase()).filter(Boolean);
}
function boundedInteger(name, fallback, maximum) {
  const value = Number(paramValue(name, fallback));
  return Number.isInteger(value) && value > 0 ? Math.min(value, maximum) : fallback;
}
function paramBoolean(name, fallback) {
  const value = String(paramValue(name, fallback ? 'true' : 'false')).trim().toLowerCase();
  if (value === 'true') return true;
  if (value === 'false') return false;
  return fallback;
}

const ISO_OFFSET_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?(Z|[+-]\d{2}:\d{2})$/;
function lexicalCompare(left, right) {
  const a = String(left);
  const b = String(right);
  return a < b ? -1 : (a > b ? 1 : 0);
}
function validTimeZone(value) {
  if (!String(value || '').trim()) return false;
  try {
    new Intl.DateTimeFormat('en-US', {timeZone: value}).format(0);
    return true;
  } catch (_error) {
    return false;
  }
}
function utf8ByteLength(value) {
  let bytes = 0;
  for (const character of String(value)) {
    const point = character.codePointAt(0);
    if (point <= 0x7F) bytes += 1;
    else if (point <= 0x7FF) bytes += 2;
    else if (point <= 0xFFFF) bytes += 3;
    else bytes += 4;
  }
  return bytes;
}
function strictTimestamp(value) {
  const text = String(value == null ? '' : value).trim();
  const match = ISO_OFFSET_RE.exec(text);
  if (!match) return null;
  const milliseconds = Date.parse(text);
  if (!Number.isFinite(milliseconds)) return null;
  let offsetMinutes = 0;
  if (match[8] !== 'Z') {
    const sign = match[8][0] === '-' ? -1 : 1;
    const offsetHour = Number(match[8].slice(1, 3));
    const offsetMinute = Number(match[8].slice(4, 6));
    if (offsetHour > 23 || offsetMinute > 59) return null;
    offsetMinutes = sign * (offsetHour * 60 + offsetMinute);
  }
  const local = new Date(milliseconds + offsetMinutes * 60000);
  const expectedMs = Number((match[7] || '').padEnd(3, '0'));
  if (local.getUTCFullYear() !== Number(match[1]) || local.getUTCMonth() + 1 !== Number(match[2]) ||
      local.getUTCDate() !== Number(match[3]) || local.getUTCHours() !== Number(match[4]) ||
      local.getUTCMinutes() !== Number(match[5]) || local.getUTCSeconds() !== Number(match[6]) ||
      local.getUTCMilliseconds() !== expectedMs) return null;
  return {text, milliseconds};
}

const limits = {
  rows: boundedInteger('max_rows', 1000, 1000),
  resources: boundedInteger('max_resources', 50, 50),
  lanes: boundedInteger('max_lanes_per_resource', 8, 8),
  spanDays: boundedInteger('max_span_days', 90, 90),
  modelBytes: boundedInteger('max_model_bytes', 120000, 120000),
};
const timezone = String(paramValue('timezone', '')).trim();
const asOf = strictTimestamp(paramValue('as_of', ''));
const ignoredStatuses = new Set(paramList('ignored_conflict_statuses', ['cancelled', 'canceled']));
const doneStatuses = new Set(paramList('done_statuses', ['done', 'completed', 'closed']));
const allowHttpLinks = paramBoolean('allow_http_links', false);
const sourceRows = normalizeRows('rows');

function fallback(reason, observed) {
  return {
    required: true,
    family: 'table_node',
    reason,
    observed: observed || {},
    timezone: timezone || 'unspecified',
    theme: themeName(),
    style: HOUSE_STYLE,
  };
}

function buildModel() {
  if (!paramBoolean('explicit_request', false)) return fallback('explicit_request_required');
  if (!validTimeZone(timezone)) return fallback('invalid_or_missing_iana_timezone');
  if (!asOf) return fallback('invalid_or_missing_as_of');
  if (sourceRows.length > limits.rows) return fallback('row_cap_exceeded', {rows: sourceRows.length, maximum: limits.rows});
  const items = [];
  for (let index = 0; index < sourceRows.length; index += 1) {
    const row = sourceRows[index] || {};
    const resourceId = String(row.resource_id || '').trim();
    const resourceName = String(row.resource_name || '').trim();
    const itemId = String(row.item_id || '').trim();
    const start = strictTimestamp(row.start_at);
    const end = strictTimestamp(row.end_at);
    const status = String(row.status || '').trim();
    if (!resourceId || !resourceName || !itemId || !status || !start || !end || end.milliseconds <= start.milliseconds) {
      return fallback('invalid_interval_row', {row_index: index});
    }
    const href = safeUri(row.link, {allowHttp: allowHttpLinks});
    items.push({
      resourceId, resourceName, itemId, status,
      statusKey: status.toLowerCase(),
      startAt: start.text, endAt: end.text,
      startMs: start.milliseconds, endMs: end.milliseconds,
      owner: String(row.owner || ''), href,
      conflict: false, lane: 0,
      anomaly: doneStatuses.has(status.toLowerCase()) && start.milliseconds > asOf.milliseconds ? 'completed_after_as_of' : '',
    });
  }
  items.sort((left, right) => lexicalCompare(left.resourceId, right.resourceId) || left.startMs - right.startMs ||
    left.endMs - right.endMs || lexicalCompare(left.itemId, right.itemId));
  const resources = [];
  const byResource = new Map();
  for (const item of items) {
    if (!byResource.has(item.resourceId)) {
      const resource = {id: item.resourceId, name: item.resourceName, items: [], laneCount: 0};
      byResource.set(item.resourceId, resource);
      resources.push(resource);
    }
    byResource.get(item.resourceId).items.push(item);
  }
  if (resources.length > limits.resources) return fallback('resource_cap_exceeded', {resources: resources.length, maximum: limits.resources});
  const minStart = items.length ? Math.min(...items.map((item) => item.startMs)) : asOf.milliseconds;
  const maxEnd = items.length ? Math.max(...items.map((item) => item.endMs)) : asOf.milliseconds;
  const spanDays = (maxEnd - minStart) / 86400000;
  if (spanDays > limits.spanDays) return fallback('span_cap_exceeded', {span_days: spanDays, maximum: limits.spanDays});

  let conflictCount = 0;
  for (const resource of resources) {
    const laneEnds = [];
    const active = [];
    for (const item of resource.items) {
      let lane = laneEnds.findIndex((endMs) => endMs <= item.startMs);
      if (lane < 0) lane = laneEnds.length;
      laneEnds[lane] = item.endMs;
      item.lane = lane;
      while (active.length && active[0].endMs <= item.startMs) active.shift();
      if (!ignoredStatuses.has(item.statusKey)) {
        for (const previous of active) {
          if (!ignoredStatuses.has(previous.statusKey) && previous.endMs > item.startMs) {
            if (!previous.conflict) conflictCount += 1;
            previous.conflict = true;
            if (!item.conflict) conflictCount += 1;
            item.conflict = true;
          }
        }
      }
      active.push(item);
      active.sort((left, right) => left.endMs - right.endMs || lexicalCompare(left.itemId, right.itemId));
    }
    resource.laneCount = laneEnds.length;
    if (resource.laneCount > limits.lanes) {
      return fallback('lane_cap_exceeded', {resource_id: resource.id, lanes: resource.laneCount, maximum: limits.lanes});
    }
  }
  const model = {
    required: false,
    explicitOnly: true,
    timezone,
    asOf: asOf.text,
    timeRange: {startMs: minStart, endMs: maxEnd, spanDays},
    resources,
    counts: {items: items.length, resources: resources.length, conflicts: conflictCount},
    allowHttpLinks,
    theme: themeName(),
    style: HOUSE_STYLE,
  };
  const modelBytes = utf8ByteLength(JSON.stringify({...model, style: undefined}));
  if (modelBytes > limits.modelBytes) return fallback('model_cap_exceeded', {model_bytes: modelBytes, maximum: limits.modelBytes});
  return model;
}

const model = buildModel();
module.exports = {
  render: Editor.wrapFn({
    args: [model],
    fn: function(options, data) {
      function esc(value) {
        return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      }
      function safeHref(value, allowHttp) {
        const text = String(value == null ? '' : value).trim();
        if (!text || /[\u0000-\u001F\u007F\s]/.test(text) || text.indexOf(String.fromCharCode(92)) !== -1 || text.startsWith('//')) return '';
        if (/^https?:/i.test(text)) {
          try {
            const parsed = new URL(text);
            if (!parsed.hostname || parsed.username || parsed.password) return '';
            if (parsed.protocol === 'https:') return text;
            if (parsed.protocol === 'http:') return allowHttp === true ? text : '';
            return '';
          } catch (_error) { return ''; }
        }
        if (text.includes('://')) return '';
        return /^[A-Za-z][A-Za-z0-9+.-]*:/.test(text) ? '' : text;
      }
      const style = (data.style.themes && data.style.themes[data.theme]) || data.style;
      const requestedWidth = Number(options && options.width);
      const requestedHeight = Number(options && options.height);
      const width = Number.isFinite(requestedWidth) && requestedWidth > 0 ? requestedWidth : 640;
      const height = Number.isFinite(requestedHeight) && requestedHeight > 0 ? requestedHeight : 340;
      const compact = width < 560;
      const dense = height < 260;
      if (data.required) {
        return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:14px;background:${style.colors.surface};color:${style.colors.text};font-family:Inter,Arial,sans-serif;"><b>TABLE FALLBACK REQUIRED</b><div style="margin-top:6px;color:${style.colors.textMuted};">${esc(data.reason)}</div></div>`);
      }
      const start = data.timeRange.startMs;
      const span = Math.max(1, data.timeRange.endMs - start);
      const resourceHtml = data.resources.map((resource) => {
        const laneHeight = dense ? 28 : 32;
        const items = resource.items.map((item) => {
          const left = ((item.startMs - start) / span) * 100;
          const itemWidth = Math.max(1.5, ((item.endMs - item.startMs) / span) * 100);
          const stateText = item.conflict ? 'CONFLICT' : (item.anomaly ? 'ANOMALY' : item.status || 'scheduled');
          const color = item.conflict ? style.colors.critical : (item.anomaly ? style.colors.warning : style.colors.primary);
          const label = `<b>${esc(item.itemId)}</b><span style="margin-left:5px;">${esc(stateText)}</span>`;
          const safeLink = safeHref(item.href, data.allowHttpLinks);
          const content = safeLink ? `<a href="${safeHref(item.href, data.allowHttpLinks)}" style="color:inherit;text-decoration:underline;">${label}</a>` : `<span>${label}</span>`;
          return `<div data-state="${esc(stateText)}" title="${esc(item.itemId)} · ${esc(stateText)}" style="position:absolute;box-sizing:border-box;left:${left}%;width:${itemWidth}%;top:${item.lane * laneHeight}px;height:${dense ? 22 : 26}px;padding:${dense ? 3 : 5}px ${compact ? 4 : 7}px;border:1px solid ${color};border-left-width:${compact ? 2 : 4}px;border-radius:4px;background:${style.colors.surfaceMuted};color:${style.colors.text};overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:${dense || compact ? 10 : 11}px;">${content}</div>`;
        }).join('');
        const rowLayout = compact
          ? 'grid-template-columns:1fr;grid-template-rows:auto auto;'
          : 'grid-template-columns:minmax(0,0.24fr) minmax(0,0.76fr);grid-template-rows:1fr;';
        return `<div style="display:grid;${rowLayout}border-top:1px solid ${style.colors.border};"><div style="padding:${compact ? 5 : 8}px;background:${style.colors.surface};color:${style.colors.text};font-size:${compact ? 11 : 12}px;font-weight:700;min-width:0;overflow:hidden;text-overflow:ellipsis;">${esc(resource.name)}</div><div style="position:relative;min-width:0;min-height:${Math.max(1, resource.laneCount) * laneHeight}px;">${items}</div></div>`;
      }).join('');
      return Editor.generateHtml(`<div style="box-sizing:border-box;width:100%;height:100%;padding:${compact ? 6 : 10}px ${compact ? 6 : 12}px;background:${style.colors.surface};font-family:Inter,Arial,sans-serif;overflow-x:hidden;overflow-y:auto;"><div style="position:sticky;top:0;z-index:3;padding:4px 0 ${dense ? 5 : 8}px;background:${style.colors.surface};color:${style.colors.textMuted};font-size:${compact ? 10 : 11}px;">${esc(data.timezone)} · ${esc(data.asOf)} · CONFLICTS ${data.counts.conflicts}</div>${resourceHtml || `<div style="color:${style.colors.textSubtle};">NO SCHEDULE DATA</div>`}</div>`);
    },
  }),
};
