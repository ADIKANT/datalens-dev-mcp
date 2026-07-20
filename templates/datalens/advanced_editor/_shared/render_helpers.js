// Source/data contract helpers: keep escaping, compact formatting, row normalization,
// and theme detection shared so family templates stay small and auditable.
function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatCompact(value) {
  if (value == null || value === '' || !Number.isFinite(Number(value))) return 'N/A';
  const number = Number(value);
  const abs = Math.abs(number);
  if (abs >= 1000000) return `${(number / 1000000).toFixed(1).replace(/\.0$/, '')}M`;
  if (abs >= 1000) return `${(number / 1000).toFixed(1).replace(/\.0$/, '')}K`;
  return String(Math.round(number * 10) / 10).replace(/\.0$/, '');
}

function formatDateLabel(value) {
  const text = String(value == null ? '' : value).trim();
  const daily = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$/);
  if (daily) return `${daily[3]}.${daily[2]}.${daily[1].slice(2)}`;
  const monthly = text.match(/^(\d{4})-(\d{2})$/);
  if (monthly) return `${monthly[2]}.${monthly[1].slice(2)}`;
  return text || 'N/A';
}

function niceAxis(maxValue, tickCount) {
  const maximum = Number(maxValue);
  const count = Math.max(2, Math.round(Number(tickCount) || 4));
  if (!Number.isFinite(maximum) || maximum <= 0) return {max: 1, step: 1, ticks: [0, 1]};
  const rough = maximum / count;
  const power = Math.pow(10, Math.floor(Math.log10(rough)));
  const fraction = rough / power;
  const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
  const step = niceFraction * power;
  const niceMax = Math.ceil(maximum / step) * step;
  const ticks = [];
  for (let value = 0; value <= niceMax + step / 2; value += step) ticks.push(Number(value.toPrecision(12)));
  return {max: niceMax, step, ticks};
}

// URI safety: HTTPS and relative references are allowed by default. HTTP is
// opt-in; rejected values stay visible as plain text instead of clickable links.
function safeUri(value, options) {
  const policy = options || {};
  const allowHttp = policy.allowHttp === true;
  const allowRelative = policy.allowRelative !== false;
  const text = String(value == null ? '' : value)
    .replace(/&#(x[0-9a-f]+|\d+);?/gi, (_match, code) => {
      const point = code[0].toLowerCase() === 'x' ? parseInt(code.slice(1), 16) : parseInt(code, 10);
      return Number.isInteger(point) && point >= 0 && point <= 0x10FFFF ? String.fromCodePoint(point) : '\uFFFD';
    })
    .replace(/&colon;/gi, ':')
    .replace(/&tab;/gi, '\t')
    .replace(/&newline;/gi, '\n')
    .replace(/&amp;/gi, '&')
    .trim();
  if (!text || /[\u0000-\u001F\u007F\s]/.test(text) || text.indexOf(String.fromCharCode(92)) !== -1 || text.startsWith('//')) return '';
  if (/^https?:/i.test(text)) {
    try {
      const parsed = new URL(text);
      if (!parsed.hostname || parsed.username || parsed.password) return '';
      if (parsed.protocol === 'https:') return text;
      if (parsed.protocol === 'http:') return allowHttp ? text : '';
      return '';
    } catch (_error) {
      return '';
    }
  }
  if (text.includes('://')) return '';
  if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(text)) return '';
  return allowRelative ? text : '';
}

function normalizeRows(sourceName) {
  const loaded = Editor.getLoadedData() || {};
  const source = loaded[sourceName] || loaded.rows || [];
  if (!Array.isArray(source)) return [];
  const metadata = source.find((item) => item && item.event === 'metadata');
  const names = metadata?.data?.names || [];
  const eventRows = source.filter((item) => item && item.event === 'row' && Array.isArray(item.data));
  if (names.length && eventRows.length) {
    return eventRows.map((item) => Object.fromEntries(item.data.map((value, index) => [names[index] || `column_${index + 1}`, value])));
  }
  return source;
}

function themeName() {
  const params = Editor.getParams ? Editor.getParams() : {};
  const requested = String(params.theme?.[0] || 'light').toLowerCase();
  return requested === 'dark' ? 'dark' : 'light';
}

module.exports = {escapeHtml, formatCompact, formatDateLabel, niceAxis, normalizeRows, safeUri, themeName};
