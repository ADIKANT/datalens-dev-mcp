function getPreparedLoadedData(loadedData, sourceName) {
  const sourceData = loadedData[sourceName];
  if (!sourceData) return [];
  const meta = sourceData.find(item => item.event === 'metadata');
  const names = meta?.data?.names || [];
  return sourceData
    .filter(item => item.event === 'row')
    .map(item => {
      const row = {};
      item.data.forEach((value, index) => {
        row[names[index]] = value;
      });
      return row;
    });
}

function toNumber(value) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : 0;
}

function dateKey(value) {
  return String(value || '').slice(0, 10);
}

function parseDateOnly(value) {
  const normalized = dateKey(value);
  if (!normalized) return null;
  const relativeMatch = String(value || '').match(/^__relative_([+-]?\d+)([dMy])$/);
  if (relativeMatch) {
    const amount = Number(relativeMatch[1]);
    const unit = relativeMatch[2];
    const now = new Date();
    const result = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    if (unit === 'd') {
      result.setDate(result.getDate() + amount);
    } else if (unit === 'M') {
      result.setMonth(result.getMonth() + amount);
    } else {
      result.setFullYear(result.getFullYear() + amount);
    }
    return result;
  }
  const result = new Date(`${normalized}T00:00:00`);
  return Number.isNaN(result.getTime()) ? null : result;
}

function toDateKey(dateValue) {
  return `${dateValue.getFullYear()}-${String(dateValue.getMonth() + 1).padStart(2, '0')}-${String(dateValue.getDate()).padStart(2, '0')}`;
}

function shiftDate(dateValue, deltaDays) {
  const result = new Date(dateValue.getTime());
  result.setDate(result.getDate() + deltaDays);
  return result;
}

function startOfQuarter(dateValue) {
  return new Date(dateValue.getFullYear(), Math.floor(dateValue.getMonth() / 3) * 3, 1);
}

function shiftMonth(dateValue, deltaMonths) {
  const target = new Date(dateValue.getFullYear(), dateValue.getMonth() + deltaMonths, 1);
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  target.setDate(Math.min(dateValue.getDate(), lastDay));
  return target;
}

function shiftYear(dateValue, deltaYears) {
  const targetYear = dateValue.getFullYear() + deltaYears;
  const targetMonth = dateValue.getMonth();
  const lastDay = new Date(targetYear, targetMonth + 1, 0).getDate();
  return new Date(targetYear, targetMonth, Math.min(dateValue.getDate(), lastDay));
}

function finiteOrNull(value) {
  if (value === null || value === undefined || value === '') return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function safeRatio(numerator, denominator, fallback = null, multiplier = 1) {
  const safeNumerator = finiteOrNull(numerator);
  const safeDenominator = finiteOrNull(denominator);
  if (safeNumerator === null || safeDenominator === null || safeDenominator === 0) return fallback;
  return safeNumerator * multiplier / safeDenominator;
}

function sumFinite(values) {
  return (values || []).reduce((total, value) => {
    const numeric = finiteOrNull(value);
    return numeric === null ? total : total + numeric;
  }, 0);
}

function averageFinite(values) {
  const finiteValues = (values || []).map(finiteOrNull).filter(value => value !== null);
  return finiteValues.length ? sumFinite(finiteValues) / finiteValues.length : null;
}

function maxEventDate(dataRows, fromDate = null, toDate = null) {
  let latest = null;
  (dataRows || []).forEach(row => {
    const parsed = parseDateOnly(
      row?.event_date || row?.report_date || row?.rating_date || row?.created_date || row?.date
    );
    if (parsed && fromDate && fromDate > parsed) return;
    if (parsed && toDate && parsed > toDate) return;
    if (parsed && (!latest || parsed > latest)) latest = parsed;
  });
  return latest;
}

function minEventDate(dataRows) {
  let earliest = null;
  (dataRows || []).forEach(row => {
    const parsed = parseDateOnly(
      row?.event_date || row?.report_date || row?.rating_date || row?.created_date || row?.date
    );
    if (parsed && (!earliest || parsed < earliest)) earliest = parsed;
  });
  return earliest;
}

function contextualComparisonMethods(fromDate, toDate) {
  if (!fromDate || !toDate) {
    return ['previous_period', 'previous_week', 'previous_month', 'previous_year'];
  }
  let selectedFrom = fromDate;
  let selectedTo = toDate;
  if (selectedFrom > selectedTo) {
    selectedFrom = toDate;
    selectedTo = fromDate;
  }
  const selectedDays = Math.max(
    1,
    Math.round((selectedTo.getTime() - selectedFrom.getTime()) / 86400000) + 1
  );
  if (selectedDays >= 330 && selectedDays <= 366) return ['previous_year'];
  if (selectedDays > 366) return ['previous_period'];
  const methods = ['previous_period'];
  if (selectedFrom.getTime() > shiftDate(selectedTo, -7).getTime()) methods.push('previous_week');
  if (selectedFrom.getTime() > shiftMonth(selectedTo, -1).getTime()) methods.push('previous_month');
  if (selectedFrom.getTime() > shiftYear(selectedTo, -1).getTime()) methods.push('previous_year');
  return methods;
}

function comparisonFallback(methods) {
  if (methods.length === 1) return methods[0];
  if (!methods.includes('previous_week') && methods.includes('previous_month')) {
    return 'previous_month';
  }
  return 'previous_period';
}

function normalizeComparisonMethod(requestedMethod, fromDate, toDate) {
  const methods = contextualComparisonMethods(fromDate, toDate);
  return methods.includes(requestedMethod) ? requestedMethod : comparisonFallback(methods);
}

function resolvePeriodWindow(dataRows = [], visibleStartRows = null) {
  const requestedComparisonMethod = String(
    Editor.getParam('comparisonMethod')?.[0] || 'previous_period'
  );
  const customFrom = parseDateOnly(Editor.getParam('dateFrom')?.[0]);
  const customTo = parseDateOnly(Editor.getParam('dateTo')?.[0]);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  let selectedFrom = customFrom || shiftDate(today, -6);
  let selectedTo = customTo || today;

  if (selectedFrom > selectedTo) {
    const swap = selectedFrom;
    selectedFrom = selectedTo;
    selectedTo = swap;
  }
  const comparisonMethod = normalizeComparisonMethod(
    requestedComparisonMethod,
    selectedFrom,
    selectedTo
  );

  let horizonTo = selectedTo >= today ? today : selectedTo;
  const observedMaxDate = maxEventDate(dataRows, selectedFrom, horizonTo);
  if (observedMaxDate) horizonTo = observedMaxDate;
  const observedMinDate = minEventDate(
    Array.isArray(visibleStartRows) ? visibleStartRows : dataRows
  );
  const hasCurrentData = Boolean(observedMaxDate);
  const currentFrom = selectedFrom;
  const currentTo = horizonTo >= selectedFrom ? horizonTo : selectedFrom;
  const currentDays = hasCurrentData
    ? Math.max(1, Math.round((currentTo.getTime() - currentFrom.getTime()) / 86400000) + 1)
    : 0;
  const comparisonDays = Math.max(1, currentDays || 1);
  let previousFrom;
  let previousTo;
  let previousLabel = 'PREVIOUS EQUAL PERIOD';
  if (comparisonMethod === 'previous_week') {
    previousFrom = shiftDate(currentFrom, -7);
    previousTo = shiftDate(currentTo, -7);
    previousLabel = 'SAME DAYS PREVIOUS WEEK';
  } else if (comparisonMethod === 'previous_month') {
    previousFrom = shiftMonth(currentFrom, -1);
    previousTo = shiftMonth(currentTo, -1);
    previousLabel = 'PREVIOUS MONTH';
  } else if (comparisonMethod === 'previous_year') {
    previousFrom = shiftYear(currentFrom, -1);
    previousTo = shiftYear(currentTo, -1);
    previousLabel = 'PREVIOUS YEAR';
  } else {
    previousTo = shiftDate(currentFrom, -1);
    previousFrom = shiftDate(previousTo, -(comparisonDays - 1));
  }
  return {
    selectedFrom,
    selectedTo,
    currentFrom,
    currentTo,
    previousFrom,
    previousTo,
    selectedFromKey: toDateKey(selectedFrom),
    selectedToKey: toDateKey(selectedTo),
    currentFromKey: toDateKey(currentFrom),
    currentToKey: toDateKey(currentTo),
    previousFromKey: toDateKey(previousFrom),
    previousToKey: toDateKey(previousTo),
    currentDays,
    requestedComparisonMethod,
    comparisonMethod,
    previousLabel,
    observedMinDate,
    observedMinDateKey: observedMinDate ? toDateKey(observedMinDate) : '',
    observedMaxDate,
    observedMaxDateKey: observedMaxDate ? toDateKey(observedMaxDate) : '',
    hasCurrentData
  };
}

function inDateRange(value, fromDate, toDate) {
  const parsed = parseDateOnly(value);
  return Boolean(parsed && parsed >= fromDate && parsed <= toDate);
}

function startOfWeek(dateValue) {
  const result = new Date(dateValue.getTime());
  const day = result.getDay();
  result.setDate(result.getDate() + (day === 0 ? -6 : 1 - day));
  return result;
}

function grainKey(value, grain) {
  const parsed = parseDateOnly(value);
  if (!parsed) return dateKey(value);
  if (grain === 'month') {
    return `${parsed.getFullYear()}-${String(parsed.getMonth() + 1).padStart(2, '0')}-01`;
  }
  if (grain === 'week') {
    return toDateKey(startOfWeek(parsed));
  }
  return toDateKey(parsed);
}

function buildGrainCategories(fromDate, toDate, grain) {
  const values = [];
  const seen = new Set();
  const cursor = new Date(fromDate.getTime());
  for (let guard = 0; cursor <= toDate && guard < 3700; guard += 1) {
    const key = grainKey(toDateKey(cursor), grain);
    if (key && !seen.has(key)) {
      seen.add(key);
      values.push(key);
    }
    cursor.setDate(cursor.getDate() + 1);
  }
  return values;
}

function wholeDayDiff(fromDate, toDate) {
  if (!(fromDate instanceof Date) || !(toDate instanceof Date)) return 0;
  const fromUtc = Date.UTC(fromDate.getFullYear(), fromDate.getMonth(), fromDate.getDate());
  const toUtc = Date.UTC(toDate.getFullYear(), toDate.getMonth(), toDate.getDate());
  return Math.round((toUtc - fromUtc) / 86400000);
}

function resolveGrain(windowConfig = null) {
  const requested = String(Editor.getParam('granularity')?.[0] || 'auto').toLowerCase();
  if (requested === 'day' || requested === 'week' || requested === 'month') return requested;
  const fromDate = windowConfig?.selectedFrom || parseDateOnly(Editor.getParam('dateFrom')?.[0]);
  const toDate = windowConfig?.selectedTo || parseDateOnly(Editor.getParam('dateTo')?.[0]);
  const selectedDays = fromDate && toDate
    ? Math.max(1, wholeDayDiff(fromDate, toDate) + 1)
    : 7;
  if (selectedDays > 60) return 'month';
  if (selectedDays > 14) return 'week';
  return 'day';
}

function buildVisibleCategories(windowConfig, grain) {
  if (!windowConfig?.hasCurrentData || !windowConfig.currentFrom || !windowConfig.currentTo) return [];
  const visibleFrom = windowConfig.observedMinDate && windowConfig.observedMinDate > windowConfig.currentFrom
    ? windowConfig.observedMinDate
    : windowConfig.currentFrom;
  if (visibleFrom > windowConfig.currentTo) return [];
  return buildGrainCategories(visibleFrom, windowConfig.currentTo, grain);
}

function grainBounds(category, grain) {
  const start = parseDateOnly(category);
  if (!start) return null;
  if (grain === 'week') {
    return {start, end: shiftDate(start, 6)};
  }
  if (grain === 'month') {
    return {
      start: new Date(start.getFullYear(), start.getMonth(), 1),
      end: new Date(start.getFullYear(), start.getMonth() + 1, 0)
    };
  }
  return {start, end: start};
}

function buildAlignedComparisonBuckets(windowConfig, categories, grain) {
  if (
    !windowConfig?.currentFrom
    || !windowConfig?.currentTo
    || !windowConfig?.previousFrom
    || !windowConfig?.previousTo
  ) {
    return [];
  }
  return (categories || []).map(category => {
    const bounds = grainBounds(category, grain);
    if (!bounds) return null;
    const currentFrom = bounds.start > windowConfig.currentFrom ? bounds.start : windowConfig.currentFrom;
    const currentTo = bounds.end >= windowConfig.currentTo ? windowConfig.currentTo : bounds.end;
    if (currentFrom > currentTo) return null;
    const fromOffset = wholeDayDiff(windowConfig.currentFrom, currentFrom);
    const toOffset = wholeDayDiff(windowConfig.currentFrom, currentTo);
    const comparisonFrom = shiftDate(windowConfig.previousFrom, fromOffset);
    let comparisonTo = shiftDate(windowConfig.previousFrom, toOffset);
    if (comparisonFrom > windowConfig.previousTo) return null;
    if (comparisonTo > windowConfig.previousTo) comparisonTo = windowConfig.previousTo;
    if (comparisonFrom > comparisonTo) return null;
    return {
      currentFrom,
      currentTo,
      comparisonFrom,
      comparisonTo,
      comparisonFromKey: toDateKey(comparisonFrom),
      comparisonToKey: toDateKey(comparisonTo)
    };
  });
}

function buildComparisonCategories(windowConfig, grain, categories = null) {
  if (!windowConfig?.previousFrom || !windowConfig?.previousTo) return [];
  const currentCategories = Array.isArray(categories)
    ? categories
    : buildVisibleCategories(windowConfig, grain);
  return buildAlignedComparisonBuckets(windowConfig, currentCategories, grain)
    .map(bucket => bucket?.comparisonFromKey || '');
}

function buildComparisonRanges(windowConfig, grain, categories = null) {
  if (!windowConfig?.previousFrom || !windowConfig?.previousTo) return [];
  const currentCategories = Array.isArray(categories)
    ? categories
    : buildVisibleCategories(windowConfig, grain);
  return buildAlignedComparisonBuckets(windowConfig, currentCategories, grain)
    .map(bucket => {
      if (!bucket) return '';
      return bucket.comparisonFromKey === bucket.comparisonToKey
        ? bucket.comparisonFromKey
        : `${bucket.comparisonFromKey} — ${bucket.comparisonToKey}`;
    });
}

function buildCurrentRanges(windowConfig, grain, categories = null) {
  if (!windowConfig?.currentFrom || !windowConfig?.currentTo) return [];
  const currentCategories = Array.isArray(categories)
    ? categories
    : buildVisibleCategories(windowConfig, grain);
  return buildAlignedComparisonBuckets(windowConfig, currentCategories, grain)
    .map(bucket => {
      if (!bucket) return '';
      const currentFromKey = toDateKey(bucket.currentFrom);
      const currentToKey = toDateKey(bucket.currentTo);
      return currentFromKey === currentToKey
        ? currentFromKey
        : `${currentFromKey} — ${currentToKey}`;
    });
}

function alignComparisonRows(
  rows,
  categories,
  windowConfig,
  grain,
  reducer,
  emptyValue = 0,
  dateField = 'event_date'
) {
  const buckets = buildAlignedComparisonBuckets(windowConfig, categories, grain);
  return buckets.map(bucket => {
    if (!bucket) return null;
    const scopedRows = (rows || []).filter(row =>
      inDateRange(row?.[dateField], bucket.comparisonFrom, bucket.comparisonTo)
    );
    const reduced = reducer(scopedRows, bucket);
    if (reduced === null || reduced === undefined || reduced === '') {
      return emptyValue === undefined ? null : finiteOrNull(emptyValue);
    }
    return finiteOrNull(reduced);
  });
}

function completeSeries(categories, grouped, windowConfig, grain, defaultValue = 0) {
  const currentHorizon = windowConfig?.hasCurrentData
    ? grainKey(windowConfig.currentToKey || windowConfig.currentTo, grain)
    : '';
  return (categories || []).map((category, index) => {
    const categoryKey = grainKey(category, grain);
    if (!currentHorizon || categoryKey > currentHorizon) return null;
    let rawValue;
    if (Array.isArray(grouped)) rawValue = grouped[index];
    else if (typeof grouped === 'function') rawValue = grouped(category, index);
    else rawValue = grouped?.[category] ?? grouped?.[categoryKey];
    if (rawValue === null) return null;
    if (rawValue === undefined || rawValue === '') return defaultValue;
    return finiteOrNull(rawValue);
  });
}

function isCategoryAfterObserved(category, windowConfig, grain) {
  if (!windowConfig?.hasCurrentData) return true;
  return grainKey(category, grain) > grainKey(windowConfig.currentToKey || windowConfig.currentTo, grain);
}

function periodCaption(windowConfig) {
  function shortDate(value) {
    const parsed = value instanceof Date ? value : parseDateOnly(value);
    if (!parsed) return '—';
    return `${String(parsed.getDate()).padStart(2, '0')}.${String(parsed.getMonth() + 1).padStart(2, '0')}.${String(parsed.getFullYear()).slice(-2)}`;
  }
  if (!windowConfig) return '';
  if (!windowConfig.hasCurrentData) {
    const previousRange = `${shortDate(windowConfig.previousFrom)}–${shortDate(windowConfig.previousTo)}`;
    return `DATA NO OBSERVED DATA · COMPARE ${windowConfig.previousLabel}: ${previousRange}`;
  }
  const currentRange = `${shortDate(windowConfig.currentFrom)}–${shortDate(windowConfig.currentTo)}`;
  const previousRange = `${shortDate(windowConfig.previousFrom)}–${shortDate(windowConfig.previousTo)}`;
  return `DATA ${currentRange} · COMPARE ${windowConfig.previousLabel}: ${previousRange}`;
}

function observedDateExtent(rows, windowConfig, dateField = 'event_date') {
  const dates = (rows || [])
    .map(row => parseDateOnly(row?.[dateField]))
    .filter(value =>
      value
      && windowConfig?.selectedFrom
      && windowConfig?.selectedTo
      && value >= windowConfig.selectedFrom
      && value <= windowConfig.selectedTo
    )
    .sort((left, right) => left - right);
  if (!dates.length) return null;
  return {from: dates[0], to: dates[dates.length - 1]};
}

function periodCaptionForRows(windowConfig, rows, dateField = 'event_date') {
  function shortDate(value) {
    const parsed = value instanceof Date ? value : parseDateOnly(value);
    if (!parsed) return '—';
    return `${String(parsed.getDate()).padStart(2, '0')}.${String(parsed.getMonth() + 1).padStart(2, '0')}.${String(parsed.getFullYear()).slice(-2)}`;
  }
  if (!windowConfig) return '';
  const extent = observedDateExtent(rows, windowConfig, dateField);
  if (!extent) {
    const previousRange = `${shortDate(windowConfig.previousFrom)}–${shortDate(windowConfig.previousTo)}`;
    return `DATA NO OBSERVED DATA · COMPARE ${windowConfig.previousLabel}: ${previousRange}`;
  }
  const observedRange = extent.from.getTime() === extent.to.getTime()
    ? shortDate(extent.from)
    : `${shortDate(extent.from)}–${shortDate(extent.to)}`;
  const previousRange = `${shortDate(windowConfig.previousFrom)}–${shortDate(windowConfig.previousTo)}`;
  return `DATA ${observedRange} · COMPARE ${windowConfig.previousLabel}: ${previousRange}`;
}

function sortedUnique(values) {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) => a.localeCompare(b));
}

function mapSeries(rows, metricKey, windowConfig, grain, valueField = 'metric_value') {
  const totals = {};
  rows
    .filter(row => String(row.metric_key || '') === metricKey)
    .filter(row => inDateRange(row.event_date, windowConfig.currentFrom, windowConfig.currentTo))
    .forEach(row => {
      const key = grainKey(row.event_date, grain);
      totals[key] = (totals[key] || 0) + toNumber(row[valueField]);
    });
  return totals;
}

function totalMetric(rows, metricKey, fromDate, toDate, valueField = 'metric_value') {
  return rows
    .filter(row => String(row.metric_key || '') === metricKey)
    .filter(row => inDateRange(row.event_date, fromDate, toDate))
    .reduce((sum, row) => sum + toNumber(row[valueField]), 0);
}

function deltaInfo(currentValue, previousValue, invert = false) {
  const safeCurrent = finiteOrNull(currentValue);
  const safePrevious = finiteOrNull(previousValue);
  if (safeCurrent === null || safePrevious === null) {
    return {percent: null, tone: 'neutral'};
  }
  const difference = safeCurrent - safePrevious;
  const rawPercent = safePrevious === 0 ? null : (difference / Math.abs(safePrevious)) * 100;
  const positive = invert ? difference < 0 : difference > 0;
  const negative = invert ? difference > 0 : difference < 0;
  return {
    percent: rawPercent,
    tone: positive ? 'positive' : negative ? 'negative' : 'neutral'
  };
}

function metricCard(config) {
  return {
    label: config.label,
    value: finiteOrNull(config.value),
    previous: finiteOrNull(config.previous),
    delta: deltaInfo(config.value, config.previous, Boolean(config.invert)),
    format: config.format || 'integer',
    unit: config.unit || '',
    accent: config.accent || '#2B75E2',
    status: config.status || '',
    note: config.note || '',
    sparkline: (config.sparkline || []).map(finiteOrNull),
    comparisonSparkline: (config.comparisonSparkline || []).map(finiteOrNull),
    sparklineCategories: Array.isArray(config.sparklineCategories) && config.sparklineCategories.length
      ? config.sparklineCategories
      : null,
    comparisonCategories: Array.isArray(config.comparisonCategories) && config.comparisonCategories.length
      ? config.comparisonCategories
      : null,
    currentRanges: Array.isArray(config.currentRanges) && config.currentRanges.length
      ? config.currentRanges
      : null,
    comparisonRanges: Array.isArray(config.comparisonRanges) && config.comparisonRanges.length
      ? config.comparisonRanges
      : null,
    comparisonLabel: config.comparisonLabel || ''
  };
}

function createRender(chartData) {
  return Editor.wrapFn({
    args: [chartData],
    fn: function(options, data) {
      const viewportWidth = Math.max(280, Number(options?.width) || 900);
      const viewportHeight = Math.max(160, Number(options?.height) || 420);
      const compactMode = viewportWidth < 720;
      const theme = {
        background: 'var(--g-color-base-background,#FFFFFF)',
        surface: 'var(--g-color-base-float,#FFFFFF)',
        neutral: 'var(--g-color-base-generic,#F2F4F7)',
        neutralAlt: 'var(--g-color-base-generic-medium,#EEF2F6)',
        text: 'var(--g-color-text-primary,#111827)',
        textSecondary: 'var(--g-color-text-secondary,#667085)',
        textHint: 'var(--g-color-text-hint,#98A2B3)',
        border: 'var(--g-color-line-generic,#EAECF0)',
        grid: 'var(--g-color-line-generic,#E5E7EB)',
        halo: 'var(--g-color-base-background,#FFFFFF)'
      };

      function esc(value) {
        return String(value ?? '')
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;');
      }

      function themedColor(value) {
        const raw = String(value || '');
        const normalized = raw.toUpperCase();
        if (normalized === '#111827') return theme.text;
        if (normalized === '#5F6368' || normalized === '#667085') return theme.textSecondary;
        if (normalized === '#D0D5DD') return theme.border;
        return raw || '#2B75E2';
      }

      function numberOrNull(value) {
        if (value === null || value === undefined || value === '') return null;
        const numeric = Number(value);
        return Number.isFinite(numeric) ? numeric : null;
      }

      function safeHref(value) {
        const text = String(value || '').trim();
        return /^https:\/\/confluence\.e-kama\.com\/[^\s]+$/.test(text) ? text : '';
      }

      function numberText(value, format, unit) {
        if (value === null || value === undefined || value === '') return 'N/A';
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) return 'N/A';
        function groupedFixed(source, decimalPlaces) {
          const rounded = Math.abs(source).toFixed(decimalPlaces);
          const parts = rounded.split('.');
          const groupedInteger = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '\u00A0');
          return `${source < 0 ? '-' : ''}${groupedInteger}${decimalPlaces ? `,${parts[1]}` : ''}`;
        }
        let rendered = '';
        if (format === 'percent') {
          rendered = `${groupedFixed(numeric, 1)}%`;
        } else if (format === 'decimal1') {
          rendered = groupedFixed(numeric, 1);
        } else if (format === 'decimal2') {
          rendered = groupedFixed(numeric, 2);
        } else {
          rendered = groupedFixed(numeric, 0);
        }
        return unit ? `${rendered} ${unit}` : rendered;
      }

      function deltaText(delta) {
        if (delta?.percent === null || delta?.percent === undefined || delta?.percent === '') return 'n/a';
        const value = Number(delta?.percent);
        if (!Number.isFinite(value)) return 'n/a';
        const sign = value > 0 ? '+' : '';
        return `${sign}${value.toFixed(1).replace('.', ',')}%`;
      }

      function sparkline(values, comparisonValues, color, width, height, cardIndex) {
        if (!values.length && !comparisonValues.length) return '';
        const renderColor = themedColor(color);
        const allFinite = values.concat(comparisonValues || [])
          .map(value => {
            if (value === null || value === undefined || value === '') return null;
            const numeric = Number(value);
            return Number.isFinite(numeric) ? numeric : null;
          })
          .filter(value => value !== null);
        if (!allFinite.length) return '';
        let maximum = Math.max(...allFinite);
        let minimum = Math.min(...allFinite);
        if (maximum === minimum) {
          const padding = Math.max(0.05, Math.abs(maximum) * 0.08);
          maximum += padding;
          minimum -= padding;
        } else {
          const padding = Math.max(
            0.02,
            (maximum - minimum) * 0.12,
            Math.max(Math.abs(maximum), Math.abs(minimum)) * 0.015
          );
          maximum += padding;
          minimum -= padding;
        }
        const span = Math.max(0.0001, maximum - minimum);
        function geometry(sourceValues) {
          const segments = [];
          let currentSegment = [];
          (sourceValues || []).forEach((value, index) => {
            const numeric = value === null || value === undefined || value === '' ? null : Number(value);
            if (!Number.isFinite(numeric)) {
              if (currentSegment.length) segments.push(currentSegment);
              currentSegment = [];
              return;
            }
            const x = sourceValues.length === 1 ? width / 2 : (index / (sourceValues.length - 1)) * width;
            const y = height - ((numeric - minimum) / span) * (height - 4) - 2;
            currentSegment.push({x, y});
          });
          if (currentSegment.length) segments.push(currentSegment);
          return segments;
        }
        const segments = geometry(values);
        const comparisonSegments = geometry(comparisonValues || []);
        const comparisonMarkup = comparisonSegments.map(segment => {
          if (segment.length === 1) {
            return `<circle cx="${segment[0].x.toFixed(1)}" cy="${segment[0].y.toFixed(1)}" r="1.6" fill="${renderColor}" opacity="0.28" />`;
          }
          return `<polyline fill="none" stroke="${renderColor}" opacity="0.28" stroke-width="1.5" stroke-dasharray="5 4" stroke-linecap="round" stroke-linejoin="round" points="${segment.map(point => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')}" />`;
        }).join('');
        const lineMarkup = segments.map(segment => {
          if (segment.length === 1) {
            return `<circle cx="${segment[0].x.toFixed(1)}" cy="${segment[0].y.toFixed(1)}" r="2" fill="${renderColor}" />`;
          }
          return `<polyline fill="none" stroke="${renderColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="${segment.map(point => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')}" />`;
        }).join('');
        const bucketCount = Math.max(values.length, (comparisonValues || []).length);
        const bucketWidth = width / Math.max(1, bucketCount);
        const hoverMarkup = Array.from({length: bucketCount}, (_value, index) => {
          const x = bucketWidth * index;
          return `<rect x="${x.toFixed(2)}" y="0" width="${bucketWidth.toFixed(2)}" height="${height}" fill="#FFFFFF" opacity="0.001" pointer-events="all" data-id="card-bucket-${cardIndex}-${index}" />`;
        }).join('');
        return `
          <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="display:block;width:100%;height:${height}px;overflow:hidden;">
            ${comparisonMarkup}
            ${lineMarkup}
            ${hoverMarkup}
          </svg>
        `;
      }

      function header() {
        const statusBackground = data.statusTone === 'error'
          ? 'var(--g-color-base-danger-light,#FDECEC)'
          : data.statusTone === 'warning'
          ? 'var(--g-color-base-warning-light,#FFF4E5)'
          : 'var(--g-color-base-positive-light,#E6F4EA)';
        const statusColor = data.statusTone === 'error'
          ? 'var(--g-color-text-danger,#B3261E)'
          : data.statusTone === 'warning'
          ? 'var(--g-color-text-warning,#9A6700)'
          : 'var(--g-color-text-positive,#0B8043)';
        const status = data.status
          ? `<div style="padding:4px 8px;border-radius:999px;background:${statusBackground};color:${statusColor};font-size:12px;line-height:15px;font-weight:800;white-space:nowrap;">${esc(data.status)}</div>`
          : '';
        const hint = data.subtitle
          ? `<div data-id="chart-hint" style="display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;background:${theme.neutral};color:${theme.textSecondary};font-size:12px;line-height:1;font-weight:800;cursor:help;flex:0 0 auto;">?</div>`
          : '';
        return `
          <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex:0 0 auto;min-width:0;">
            <div style="display:flex;flex-direction:column;gap:2px;min-width:0;">
              <div style="display:flex;align-items:center;gap:8px;min-width:0;">
                <div style="font-size:${compactMode ? 16 : 17}px;line-height:${compactMode ? 20 : 21}px;color:${theme.text};font-weight:800;letter-spacing:-0.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(data.title || '')}</div>
                ${hint}
              </div>
            </div>
            ${status}
          </div>
        `;
      }

      function kpiCardMarkup(card, cardIndex, sparkWidth, sparkHeight, cardHeight, fillHeight) {
        const visibleValue = data.hasCurrentData === false ? null : card.value;
        const visiblePrevious = data.hasCurrentData === false ? null : card.previous;
        const visibleDelta = data.hasCurrentData === false
          ? {percent: null, tone: 'neutral'}
          : card.delta;
        const deltaBg = visibleDelta?.tone === 'positive'
          ? 'var(--g-color-base-positive-light,#E6F4EA)'
          : visibleDelta?.tone === 'negative'
            ? 'var(--g-color-base-danger-light,#FDECEC)'
            : theme.neutral;
        const deltaFg = visibleDelta?.tone === 'positive'
          ? 'var(--g-color-text-positive,#0B8043)'
          : visibleDelta?.tone === 'negative'
            ? 'var(--g-color-text-danger,#B3261E)'
            : theme.textSecondary;
        const heightStyle = fillHeight ? 'height:100%;' : `height:${cardHeight}px;`;
        return `
          <div style="${heightStyle}box-sizing:border-box;min-height:0;padding:11px 11px 7px;border:0;border-radius:0;background:transparent;display:flex;flex-direction:column;gap:5px;overflow:hidden;">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
              <div style="display:flex;align-items:center;gap:6px;min-width:0;">
                <div style="font-size:12px;line-height:15px;text-transform:uppercase;letter-spacing:0.07em;color:${theme.textSecondary};font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(card.label)}</div>
                ${card.note ? `<div data-id="card-hint-${cardIndex}" style="display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:50%;background:${theme.neutral};color:${theme.textSecondary};font-size:11px;line-height:1;font-weight:800;cursor:help;flex:0 0 auto;">?</div>` : ''}
              </div>
              ${card.status ? `<div style="font-size:10px;line-height:13px;color:${theme.textHint};font-weight:700;">${esc(card.status)}</div>` : ''}
            </div>
            <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;">
              <div style="font-size:${compactMode ? 31 : 34}px;line-height:${compactMode ? 34 : 38}px;color:${theme.text};font-weight:750;letter-spacing:-0.04em;white-space:nowrap;">${esc(numberText(visibleValue, card.format, card.unit))}</div>
              <div style="padding:4px 7px;border-radius:999px;background:${deltaBg};color:${deltaFg};font-size:12px;line-height:16px;font-weight:800;white-space:nowrap;">${esc(deltaText(visibleDelta))}</div>
            </div>
            <div style="font-size:12px;line-height:15px;color:${theme.textHint};text-transform:uppercase;letter-spacing:0.055em;font-weight:700;">VS ${esc(numberText(visiblePrevious, card.format, card.unit))}</div>
            <div style="width:100%;height:${sparkHeight}px;margin-top:auto;min-width:0;">${sparkline(card.sparkline || [], card.comparisonSparkline || [], card.accent || '#2B75E2', sparkWidth, sparkHeight, cardIndex)}</div>
          </div>
        `;
      }

      function renderKpiStrip() {
        const cards = data.cards || [];
        const columns = viewportWidth >= 540 ? 3 : 1;
        const rowCount = Math.max(1, Math.ceil(cards.length / columns));
        const rowGap = 10;
        const availableCardHeight = Math.floor(
          (Math.max(180, viewportHeight - 38) - rowGap * Math.max(0, rowCount - 1)) / rowCount
        );
        const cardHeight = Math.min(158, Math.max(compactMode ? 132 : 140, availableCardHeight));
        const sparkHeight = Math.max(40, Math.min(52, Math.floor(cardHeight * 0.34)));
        const estimatedCardWidth = Math.max(
          150,
          (viewportWidth - 26 - rowGap * Math.max(0, columns - 1)) / columns
        );
        const sparkWidth = Math.max(120, Math.floor(estimatedCardWidth - 26));
        return `
          ${header()}
          <div style="display:grid;grid-template-columns:repeat(${columns},minmax(0,1fr));grid-auto-rows:${cardHeight}px;gap:${rowGap}px;min-height:0;overflow:hidden;align-content:start;">
            ${cards.map((card, cardIndex) =>
              kpiCardMarkup(card, cardIndex, sparkWidth, sparkHeight, cardHeight, false)
            ).join('')}
          </div>
        `;
      }

      function renderKpiCard() {
        const card = (data.cards || [])[0] || {};
        const cardHeight = Math.max(146, viewportHeight - 8);
        const sparkHeight = Math.max(54, Math.min(76, Math.floor(cardHeight * 0.39)));
        const sparkWidth = Math.max(120, Math.floor(viewportWidth - 26));
        return kpiCardMarkup(card, 0, sparkWidth, sparkHeight, cardHeight, true);
      }

      function renderKpiSectionHeader() {
        return `<div style="font-size:${compactMode ? 16 : 17}px;line-height:${compactMode ? 20 : 21}px;color:${theme.text};font-weight:800;letter-spacing:-0.01em;">${esc(data.title || '')}</div>`;
      }

      function renderSectionHeader() {
        return `
          <div style="display:flex;flex-direction:column;justify-content:center;height:100%;min-height:0;">
            <div style="font-size:${compactMode ? 17 : 19}px;line-height:${compactMode ? 21 : 24}px;color:${theme.text};font-weight:800;letter-spacing:-0.01em;">${esc(data.title || '')}</div>
            ${data.description ? `<div style="margin-top:3px;font-size:12px;line-height:17px;color:${theme.textSecondary};">${esc(data.description)}</div>` : ''}
          </div>
        `;
      }

      function renderTableHeader() {
        return `
          <div style="display:flex;align-items:center;height:100%;min-height:0;">
            ${header()}
          </div>
        `;
      }

      function renderComparisonContext() {
        function shortDate(value) {
          const raw = String(value || '').slice(0, 10);
          if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return '—';
          return `${raw.slice(8, 10)}.${raw.slice(5, 7)}.${raw.slice(2, 4)}`;
        }
        const from = shortDate(data.comparisonFrom);
        const to = shortDate(data.comparisonTo);
        const range = from === to ? from : `${from}–${to}`;
        return `
          <div style="display:flex;align-items:center;gap:7px;height:100%;min-height:0;color:${theme.textSecondary};font-size:12px;line-height:16px;">
            <span style="font-weight:800;color:${theme.text};">Comparison</span>
            <span>${esc(data.comparisonLabel || '')}</span>
            <span style="color:${theme.textHint};">·</span>
            <span style="font-variant-numeric:tabular-nums;">${esc(range)}</span>
          </div>
        `;
      }

      function renderCombo() {
        const width = Math.max(280, viewportWidth - 28);
        const height = Math.max(160, viewportHeight - (data.banner ? 132 : 102));
        const categories = data.categories || [];
        const series = data.series || [];
        const bars = series.filter(item => item.type === 'bar');
        const lines = series.filter(item => item.type === 'line');

        function finiteValue(value) {
          if (value === null || value === undefined || value === '') return null;
          const numeric = Number(value);
          return Number.isFinite(numeric) ? numeric : null;
        }

        let primaryMax = 1;
        let secondaryMax = 1;
        if (data.stacked) {
          categories.forEach((_category, index) => {
            let stackedValue = 0;
            bars.forEach(item => {
              const numeric = finiteValue(item.values?.[index]);
              if (numeric !== null) stackedValue += Math.max(0, numeric);
            });
            primaryMax = Math.max(primaryMax, stackedValue);
          });
        } else {
          bars.forEach(item => {
            (item.values || []).forEach(value => {
              const numeric = finiteValue(value);
              if (numeric !== null) primaryMax = Math.max(primaryMax, numeric);
            });
          });
        }
        lines.forEach(item => {
          (item.values || []).concat(item.comparisonValues || []).forEach(value => {
            const numericValue = finiteValue(value);
            if (numericValue === null) return;
            if (item.axis === 'right') secondaryMax = Math.max(secondaryMax, numericValue);
            else primaryMax = Math.max(primaryMax, numericValue);
          });
        });

        function niceScale(maxValue, requestedMax) {
          const explicitMax = finiteValue(requestedMax);
          if (explicitMax !== null && explicitMax > 0) {
            const explicitStep = explicitMax / 4;
            return {
              max: explicitMax,
              ticks: [0, explicitStep, explicitStep * 2, explicitStep * 3, explicitMax]
            };
          }
          const safeMax = Math.max(0, finiteValue(maxValue) || 0);
          if ((data.primaryFormat || 'integer') === 'integer' && safeMax <= 4) {
            const integerMax = Math.max(1, Math.ceil(safeMax));
            return {
              max: integerMax,
              ticks: Array.from({length: integerMax + 1}, (_unused, index) => index)
            };
          }
          const rawStep = Math.max(0.000001, safeMax / 4);
          const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
          const fraction = rawStep / magnitude;
          const preferred = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 7.5, 8, 10];
          const factor = preferred.find(candidate => candidate >= fraction) || 10;
          const step = factor * magnitude;
          const scaleMax = Math.max(step, Math.ceil(safeMax / step) * step);
          const tickCount = Math.max(1, Math.round(scaleMax / step));
          return {
            max: scaleMax,
            ticks: Array.from({length: tickCount + 1}, (_unused, index) => index * step)
          };
        }
        const primaryScale = niceScale(primaryMax, data.primaryScaleMax);
        const secondaryScale = niceScale(secondaryMax, data.secondaryScaleMax);
        const primaryScaleMax = primaryScale.max;
        const secondaryScaleMax = secondaryScale.max;
        function primaryTickValues() {
          return primaryScale.ticks;
        }
        const primaryTicks = primaryTickValues();
        const yLabelSamples = primaryTicks.map(value =>
          numberText(value, data.primaryFormat || 'integer', '')
        );
        const longestYLabel = yLabelSamples.reduce(
          (longest, label) => Math.max(longest, String(label).length),
          1
        );
        const plot = {
          left: Math.min(compactMode ? 82 : 104, Math.max(compactMode ? 48 : 58, longestYLabel * 7.2 + 20)),
          right: compactMode ? 20 : 28,
          top: 34,
          bottom: 46
        };
        const plotWidth = Math.max(120, width - plot.left - plot.right);
        const plotHeight = Math.max(80, height - plot.top - plot.bottom);
        const spacing = plotWidth / Math.max(1, categories.length);
        let marks = '';
        let valueLabels = '';

        function labelIndexSet(pointCount, desiredCount) {
          const selected = {};
          if (pointCount <= 0) return selected;
          if (pointCount <= desiredCount) {
            for (let index = 0; index !== pointCount; index += 1) selected[index] = true;
            return selected;
          }
          const count = Math.max(2, desiredCount);
          const stride = Math.max(1, Math.ceil(pointCount / count));
          Array.from(
            {length: Math.ceil(pointCount / stride)},
            (_unused, slot) => slot * stride
          ).forEach(index => {
            selected[index] = true;
          });
          const lastIndex = pointCount - 1;
          if (!selected[lastIndex]) {
            const selectedIndices = Object.keys(selected).map(Number).sort((left, right) => left - right);
            const previousIndex = selectedIndices[selectedIndices.length - 1];
            if (previousIndex > 0 && stride > lastIndex - previousIndex) {
              delete selected[previousIndex];
            }
            selected[lastIndex] = true;
          }
          return selected;
        }

        function valueLabelIndexSet(values, desiredCount) {
          const numericValues = (values || []).map(finiteValue);
          const finiteIndices = numericValues
            .map((value, index) => value === null ? null : index)
            .filter(index => index !== null);
          const selected = {};
          if (!finiteIndices.length) return selected;
          if (finiteIndices.length <= desiredCount) {
            finiteIndices.forEach(index => { selected[index] = true; });
            return selected;
          }
          const capacity = Math.max(2, desiredCount);
          function add(index) {
            if (index === null || index === undefined || selected[index]) return;
            if (Object.keys(selected).length < capacity) selected[index] = true;
          }
          add(finiteIndices[0]);
          add(finiteIndices[finiteIndices.length - 1]);
          const sortedByValue = finiteIndices.slice().sort((left, right) =>
            numericValues[right] - numericValues[left]
          );
          add(sortedByValue[0]);
          add(sortedByValue[sortedByValue.length - 1]);
          const extrema = [];
          for (let index = 1; index < numericValues.length - 1; index += 1) {
            const previous = numericValues[index - 1];
            const current = numericValues[index];
            const next = numericValues[index + 1];
            if (previous === null || current === null || next === null) continue;
            const isPeak = current > previous && current >= next;
            const isTrough = current < previous && current <= next;
            if (!isPeak && !isTrough) continue;
            extrema.push({
              index,
              score: Math.abs(current - (previous + next) / 2)
            });
          }
          extrema.sort((left, right) => right.score - left.score).forEach(item => add(item.index));
          const even = labelIndexSet(numericValues.length, capacity);
          Object.keys(even).map(Number).forEach(index => {
            if (numericValues[index] !== null) add(index);
          });
          if (Object.keys(selected).length < capacity) finiteIndices.forEach(index => add(index));
          return selected;
        }

        const dataLabelCapacity = categories.length <= 14 || spacing >= 48
          ? categories.length
          : Math.max(4, Math.floor(plotWidth / 58));
        const stackedTotals = categories.map((_category, index) =>
          bars.reduce((total, item) => {
            const numeric = finiteValue(item.values?.[index]);
            return numeric === null ? total : total + Math.max(0, numeric);
          }, 0)
        );
        const barLabelIndices = valueLabelIndexSet(stackedTotals, dataLabelCapacity);

        categories.forEach((_category, categoryIndex) => {
          const centerX = plot.left + spacing * categoryIndex + spacing / 2;
          if (data.stacked) {
            let stackedHeight = 0;
            let stackedTotal = 0;
            const renderedBarWidth = Math.max(8, Math.min(38, spacing * 0.38));
            bars.forEach(item => {
              const itemColor = themedColor(item.color);
              const numeric = finiteValue(item.values?.[categoryIndex]);
              if (numeric === null) return;
              const value = Math.max(0, numeric);
              const barHeight = (value / primaryScaleMax) * plotHeight;
              const y = plot.top + plotHeight - stackedHeight - barHeight;
              marks += `<rect x="${(centerX - renderedBarWidth / 2).toFixed(1)}" y="${y.toFixed(1)}" width="${renderedBarWidth.toFixed(1)}" height="${Math.max(0, barHeight).toFixed(1)}" rx="3" fill="${itemColor}" opacity="0.90" />`;
              if (item.showBarLabels !== false && value > 0 && barHeight >= 17 && barLabelIndices[categoryIndex]) {
                const segmentTextColor = item.color === '#D0D5DD' ? theme.textSecondary : '#FFFFFF';
                valueLabels += `<text x="${centerX.toFixed(1)}" y="${(y + barHeight / 2 + 4).toFixed(1)}" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-size="12" font-weight="600" letter-spacing="0" fill="${segmentTextColor}">${esc(numberText(value, item.format || data.primaryFormat || 'integer', item.labelUnit !== undefined ? item.labelUnit : ''))}</text>`;
              }
              stackedHeight += barHeight;
              stackedTotal += value;
            });
            if (stackedTotal > 0 && bars.length > 1 && barLabelIndices[categoryIndex]) {
              valueLabels += `<text x="${centerX.toFixed(1)}" y="${Math.max(13, plot.top + plotHeight - stackedHeight - 7).toFixed(1)}" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-size="12" font-weight="600" letter-spacing="0" fill="${theme.textSecondary}" style="paint-order:stroke;stroke:${theme.halo};stroke-width:3px;stroke-linejoin:round;">${esc(numberText(stackedTotal, data.primaryFormat || 'integer', ''))}</text>`;
            }
          } else {
            const barWidth = Math.max(7, Math.min(34, spacing * 0.46 / Math.max(1, bars.length)));
            bars.forEach((item, barIndex) => {
              const itemColor = themedColor(item.color);
              const numeric = finiteValue(item.values?.[categoryIndex]);
              if (numeric === null) return;
              const value = Math.max(0, numeric);
              const barHeight = (value / primaryScaleMax) * plotHeight;
              const x = centerX - (barWidth * bars.length) / 2 + barWidth * barIndex;
              const y = plot.top + plotHeight - barHeight;
              marks += `<rect x="${(x + 2).toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(3, barWidth - 4).toFixed(1)}" height="${Math.max(0, barHeight).toFixed(1)}" rx="3" fill="${itemColor}" opacity="0.90" />`;
              if (item.showBarLabels !== false && value > 0 && barLabelIndices[categoryIndex]) {
                valueLabels += `<text x="${(x + barWidth / 2).toFixed(1)}" y="${Math.max(13, y - 7).toFixed(1)}" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-size="12" font-weight="600" letter-spacing="0" fill="${theme.textSecondary}" style="paint-order:stroke;stroke:${theme.halo};stroke-width:3px;stroke-linejoin:round;">${esc(numberText(value, item.format || data.primaryFormat || 'integer', item.labelUnit !== undefined ? item.labelUnit : item.unit || ''))}</text>`;
              }
            });
          }
        });

        function pointSegments(values, maxValue) {
          const segments = [];
          let currentSegment = [];
          (values || []).forEach((value, index) => {
            const numeric = finiteValue(value);
            if (numeric === null) {
              if (currentSegment.length) segments.push(currentSegment);
              currentSegment = [];
              return;
            }
            const x = plot.left + spacing * index + spacing / 2;
            const y = plot.top + plotHeight - (numeric / maxValue) * plotHeight;
            currentSegment.push({x, y, value: numeric, index});
          });
          if (currentSegment.length) segments.push(currentSegment);
          return segments;
        }

        lines.forEach((item, lineIndex) => {
          const itemColor = themedColor(item.color);
          const comparisonColor = themedColor(item.comparisonColor || item.color);
          const maxValue = item.axis === 'right' ? secondaryScaleMax : primaryScaleMax;
          const segments = pointSegments(item.values || [], maxValue);
          const comparisonSegments = item.showComparisonLine === false
            ? []
            : pointSegments(item.comparisonValues || [], maxValue);
          comparisonSegments.forEach(segment => {
            if (segment.length < 2) return;
            marks += `<polyline fill="none" stroke="${comparisonColor}" opacity="0.50" stroke-width="2.2" stroke-dasharray="6 5" stroke-linecap="round" stroke-linejoin="round" points="${segment.map(point => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')}" />`;
          });
          segments.forEach(segment => {
            if (segment.length === 1) {
              const point = segment[0];
              marks += `<circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="3.2" fill="${theme.surface}" stroke="${itemColor}" stroke-width="2.2" />`;
            } else {
              marks += `<polyline fill="none" stroke="${itemColor}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" points="${segment.map(point => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')}" />`;
            }
          });
          const points = segments.reduce((all, segment) => all.concat(segment), []);
          const pointLabelIndices = valueLabelIndexSet(item.values || [], dataLabelCapacity);
          const defaultLabelOffset = lines.length > 1 ? (lineIndex % 2 === 0 ? -10 : 17) : -9;
          const labelOffset = Number.isFinite(Number(item.labelOffsetY)) ? Number(item.labelOffsetY) : defaultLabelOffset;
          points.forEach(point => {
            if (item.showMarkers !== false && (categories.length <= 60 || pointLabelIndices[point.index])) {
              marks += `<circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="3.2" fill="${theme.surface}" stroke="${itemColor}" stroke-width="2.2" />`;
            }
            if (item.showPointLabels !== false && pointLabelIndices[point.index]) {
              let adjustedLabelOffset = labelOffset;
              const previousValue = finiteValue(item.values?.[point.index - 1]);
              const nextValue = finiteValue(item.values?.[point.index + 1]);
              const isLocalMinimum = previousValue !== null
                && nextValue !== null
                && point.value < previousValue
                && point.value <= nextValue;
              const isLocalMaximum = previousValue !== null
                && nextValue !== null
                && point.value > previousValue
                && point.value >= nextValue;
              if (isLocalMinimum) adjustedLabelOffset = 18 + lineIndex * 10;
              else if (isLocalMaximum) adjustedLabelOffset = -10 - lineIndex * 10;
              if (bars.length) {
                let nearestBarTop = plot.top + plotHeight;
                if (data.stacked) {
                  const stackedValue = bars.reduce((total, bar) => {
                    const numeric = finiteValue(bar.values?.[point.index]);
                    return numeric === null ? total : total + Math.max(0, numeric);
                  }, 0);
                  nearestBarTop = plot.top + plotHeight - (stackedValue / primaryScaleMax) * plotHeight;
                } else {
                  bars.forEach(bar => {
                    const numeric = finiteValue(bar.values?.[point.index]);
                    if (numeric === null) return;
                    nearestBarTop = Math.min(
                      nearestBarTop,
                      plot.top + plotHeight - (Math.max(0, numeric) / primaryScaleMax) * plotHeight
                    );
                  });
                }
                if (Math.abs(point.y - nearestBarTop) < 24) {
                  adjustedLabelOffset = point.y > plot.top + 32 ? -27 - lineIndex * 10 : 20 + lineIndex * 10;
                }
              }
              const labelY = Math.max(13, Math.min(plot.top + plotHeight - 4, point.y + adjustedLabelOffset));
              valueLabels += `<text x="${point.x.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-size="12" font-weight="600" letter-spacing="0" fill="${itemColor}" style="paint-order:stroke;stroke:${theme.halo};stroke-width:3px;stroke-linejoin:round;">${esc(numberText(point.value, item.format || data.primaryFormat || 'integer', item.labelUnit !== undefined ? item.labelUnit : item.unit || ''))}</text>`;
            }
          });
        });

        const grid = primaryTicks.map(value => {
          const y = plot.top + plotHeight - (value / primaryScaleMax) * plotHeight;
          return `
            <line x1="${plot.left}" y1="${y}" x2="${width - plot.right}" y2="${y}" stroke="${theme.grid}" stroke-width="1" />
            <text x="${plot.left - 9}" y="${y + 4}" text-anchor="end" font-family="Inter,Arial,sans-serif" font-size="12" font-weight="500" letter-spacing="0" fill="${theme.textSecondary}">${esc(numberText(value, data.primaryFormat || 'integer', ''))}</text>
          `;
        }).join('');
        const grain = String(data.grain || '');
        const estimatedLabelWidth = grain === 'month' ? 48 : 64;
        const maxXAxisLabels = Math.max(2, Math.floor(plotWidth / estimatedLabelWidth));
        const xLabelIndices = labelIndexSet(categories.length, maxXAxisLabels);
        const xLabels = categories.map((category, index) => {
          if (!xLabelIndices[index]) return '';
          const x = plot.left + spacing * index + spacing / 2;
          const rawLabel = String(category);
          let label = rawLabel;
          if (/^\d{4}-\d{2}-\d{2}/.test(rawLabel)) {
            const yy = rawLabel.slice(2, 4);
            const mm = rawLabel.slice(5, 7);
            const dd = rawLabel.slice(8, 10);
            label = grain === 'month' ? `${mm}.${yy}` : `${dd}.${mm}.${yy}`;
          }
          const xFontSize = grain === 'month' && categories.length > 16 ? 10 : 12;
          return `<text x="${x}" y="${height - 15}" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-size="${xFontSize}" font-weight="500" letter-spacing="0" fill="${theme.textSecondary}">${esc(label)}</text>`;
        }).join('');
        const legend = series.map(item => {
          const availableValues = (item.values || []).filter(value => finiteValue(value) !== null);
          const last = availableValues.length ? availableValues[availableValues.length - 1] : null;
          const summary = finiteValue(item.summaryValue);
          const legendValue = data.hasCurrentData === false ? null : summary !== null ? summary : last;
          const renderedValue = legendValue === null ? 'N/A' : numberText(legendValue, item.format || 'integer', item.unit || '');
          const primary = `<div style="display:flex;align-items:center;gap:7px;font-size:14px;line-height:18px;color:${theme.textSecondary};"><div style="width:10px;height:10px;border-radius:${item.type === 'line' ? '999px' : '3px'};background:${themedColor(item.color)};"></div><span>${esc(item.name)}</span><span style="color:${theme.text};font-weight:750;">${esc(renderedValue)}</span></div>`;
          const comparison = item.comparisonLegendName
            ? `<div style="display:flex;align-items:center;gap:7px;font-size:14px;line-height:18px;color:${theme.textSecondary};"><div style="width:18px;border-top:2px dashed ${themedColor(item.color)};opacity:0.5;"></div><span>${esc(item.comparisonLegendName)}</span></div>`
            : '';
          return primary + comparison;
        }).join('');
        const hoverZones = categories.map((_category, index) => {
          const x = plot.left + spacing * index;
          return `<rect x="${x.toFixed(2)}" y="${plot.top}" width="${spacing.toFixed(2)}" height="${(plotHeight + plot.bottom).toFixed(2)}" fill="#FFFFFF" opacity="0.001" pointer-events="all" data-id="combo-bucket-${index}" />`;
        }).join('');

        return `
          ${header()}
          ${data.banner ? `<div style="padding:7px 9px;border-radius:10px;background:var(--g-color-base-warning-light,#FFF4E5);color:var(--g-color-text-warning,#9A6700);font-size:12px;line-height:16px;font-weight:700;">${esc(data.banner)}</div>` : ''}
          <div style="display:flex;flex-wrap:wrap;gap:8px 18px;flex:0 0 auto;">${legend}</div>
          <div style="width:100%;flex:1 1 auto;min-height:0;overflow:hidden;">
            <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:100%;min-width:0;background:${theme.background};overflow:hidden;">
              ${grid}
              ${marks}
              ${valueLabels}
              ${xLabels}
              ${hoverZones}
            </svg>
          </div>
        `;
      }

      function renderStatusCards() {
        const cards = data.cards || [];
        const columns = cards.length === 3 && viewportWidth >= 470
          ? 3
          : viewportWidth < 470
            ? 1
            : Math.min(4, Math.max(1, cards.length));
        function ratingColor(value) {
          const rating = Math.max(0, Math.min(5, Number(value) || 0));
          if (rating < 2.5) return '#D85C68';
          if (rating < 3.5) return '#E5A900';
          if (rating < 4.2) return '#62A875';
          return '#218C66';
        }
        return `
          ${header()}
          <div style="display:grid;grid-template-columns:repeat(${columns},minmax(0,1fr));grid-auto-rows:minmax(0,1fr);gap:12px;overflow:hidden;min-height:0;align-items:stretch;flex:1 1 auto;">
            ${cards.map((card, cardIndex) => {
              const available = card.available !== false;
              const tone = !available
                ? theme.textHint
                : data.ratingScale
                  ? ratingColor(card.value)
                  : card.tone === 'positive'
                    ? 'var(--g-color-text-positive,#2F9E73)'
                    : card.tone === 'warning'
                      ? '#E3A900'
                      : card.tone === 'negative'
                        ? 'var(--g-color-text-danger,#D65A5A)'
                        : '#2B75E2';
              const cardBackground = theme.surface;
              const cardBorder = theme.border;
              const starCount = Math.max(0, Math.min(5, Math.round(Number(card.value) || 0)));
              const starMarkup = `<div style="margin-top:3px;color:#F0B400;font-size:16px;letter-spacing:2px;">${'★★★★★'.slice(0, starCount)}<span style="color:${theme.border};">${'★★★★★'.slice(0, 5 - starCount)}</span></div>`;
              return `
                <div style="position:relative;padding:${compactMode ? 14 : 18}px ${compactMode ? 14 : 18}px;border:1px solid ${cardBorder};border-radius:14px;background:${cardBackground};min-height:0;display:flex;flex-direction:column;justify-content:center;">
                  <div style="display:flex;align-items:center;gap:6px;min-width:0;">
                    <div style="font-size:12px;line-height:15px;text-transform:uppercase;letter-spacing:0.07em;color:${theme.textSecondary};font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(card.label)}</div>
                    ${card.note ? `<div data-id="card-hint-${cardIndex}" style="position:relative;z-index:2;display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:50%;background:${theme.neutral};color:${theme.textSecondary};font-size:11px;line-height:1;font-weight:800;cursor:help;flex:0 0 auto;">?</div>` : ''}
                  </div>
                  <div style="margin-top:7px;font-size:${compactMode ? 34 : 40}px;line-height:${compactMode ? 38 : 44}px;color:${tone};font-weight:800;letter-spacing:-0.04em;">${available ? esc(numberText(card.value, card.format || 'decimal2', card.unit || '')) : 'N/A'}</div>
                  ${card.stars ? starMarkup : ''}
                  <div data-id="status-card-${cardIndex}" style="position:absolute;left:0;right:0;top:0;bottom:0;z-index:1;cursor:default;"></div>
                </div>
              `;
            }).join('')}
          </div>
        `;
      }

      function renderHorizontal() {
        const rows = data.rows || [];
        const seriesList = data.series || [];
        const narrowHorizontal = viewportWidth < 420;
        const rowTemplate = narrowHorizontal
          ? 'minmax(64px,78px) minmax(54px,1fr) 38px'
          : 'minmax(76px,96px) minmax(0,1fr) 94px';
        const rowGap = narrowHorizontal ? 6 : 10;
        let maxValue = 1;
        rows.forEach(row => {
          (row.values || []).forEach(value => {
            maxValue = Math.max(maxValue, Number(value) || 0);
          });
        });
        return `
          ${header()}
          <div style="display:flex;gap:${narrowHorizontal ? 8 : 14}px;flex-wrap:wrap;">
            ${seriesList.map((series, seriesIndex) => `<div style="display:flex;align-items:center;gap:6px;font-size:${narrowHorizontal ? 12 : 13}px;line-height:17px;color:${theme.textSecondary};"><div style="width:10px;height:${seriesIndex === 0 ? 10 : 7}px;border-radius:2px;background:${themedColor(series.color)};opacity:${seriesIndex === 0 ? 1 : 0.55};"></div>${esc(series.name)}</div>`).join('')}
          </div>
          <div style="display:flex;flex-direction:column;gap:8px;overflow:hidden;min-height:0;justify-content:center;flex:1 1 auto;">
            ${rows.map((row, rowIndex) => {
              const values = row.values || [];
              const currentValue = data.hasCurrentData === false ? null : numberOrNull(values[0]);
              const comparisonValue = data.hasCurrentData === false ? null : numberOrNull(values[1]);
              return `
                <div style="position:relative;display:grid;grid-template-columns:${rowTemplate};gap:${rowGap}px;align-items:center;min-width:0;padding:3px 0;">
                  <div style="font-size:${narrowHorizontal ? 12 : 13}px;line-height:17px;color:${theme.textSecondary};font-weight:750;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(row.label)}</div>
                  <div data-id="horizontal-bars-${rowIndex}" style="display:flex;flex-direction:column;gap:3px;min-width:54px;width:100%;">
                    ${(seriesList.length ? seriesList : [{color: '#2B75E2'}]).map((series, seriesIndex) => {
                      const value = data.hasCurrentData === false ? null : numberOrNull(values[seriesIndex]);
                      const share = value === null || maxValue <= 0
                        ? 0
                        : Math.max(0, Math.min(100, value * 100 / maxValue));
                      return `
                        <svg viewBox="0 0 100 7" preserveAspectRatio="none" style="display:block;width:100%;height:7px;overflow:hidden;">
                          <rect x="0" y="0" width="100" height="7" rx="2" fill="${theme.neutralAlt}"></rect>
                          <rect x="0" y="0" width="${share.toFixed(2)}" height="7" rx="2" fill="${themedColor(series.color || '#2B75E2')}" opacity="${seriesIndex === 0 ? 0.95 : 0.50}"></rect>
                        </svg>
                      `;
                    }).join('')}
                  </div>
                  <div style="text-align:right;font-variant-numeric:tabular-nums;">
                    <div style="font-size:${narrowHorizontal ? 14 : 15}px;line-height:18px;color:${theme.text};font-weight:750;">${esc(numberText(currentValue, data.valueFormat || 'integer', data.unit || ''))}</div>
                    ${seriesList.length > 1 ? `<div style="font-size:11px;line-height:14px;color:${theme.textHint};font-weight:650;">VS ${esc(numberText(comparisonValue, data.valueFormat || 'integer', data.unit || ''))}</div>` : ''}
                  </div>
                  <div data-id="horizontal-row-${rowIndex}" style="position:absolute;left:0;right:0;top:0;bottom:0;cursor:default;"></div>
                </div>
              `;
            }).join('')}
          </div>
        `;
      }

      function renderDistribution() {
        const rows = data.rows || [];
        const summaries = data.summaries || [];
        const maxValue = Math.max(1, ...rows.map(row => Number(row.value) || 0));
        const chartHeight = Math.max(104, Math.min(132, viewportHeight - 104));
        const labelBand = 22;
        const plotHeight = Math.max(72, chartHeight - labelBand);
        const barWidth = compactMode ? 28 : 34;
        return `
          ${header()}
          <div style="display:grid;grid-template-columns:${viewportWidth < 480 ? '1fr' : 'minmax(170px,38%) minmax(0,1fr)'};gap:14px;flex:1 1 auto;min-height:0;overflow:hidden;">
            <div style="display:flex;flex-direction:column;gap:7px;min-width:0;justify-content:center;">
              ${summaries.map((item, summaryIndex) => `
                <div style="position:relative;padding:8px 10px;border:1px solid ${theme.border};border-radius:8px;background:${theme.neutral};min-width:0;">
                  <div style="font-size:11px;line-height:14px;color:${theme.textSecondary};font-weight:750;text-transform:uppercase;letter-spacing:0.05em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(item.label)}</div>
                  <div style="margin-top:2px;display:flex;align-items:baseline;gap:8px;">
                    <span style="font-size:22px;line-height:26px;color:${theme.text};font-weight:750;">${esc(numberText(item.value, 'integer', ''))}</span>
                    ${Number.isFinite(Number(item.share)) ? `<span style="font-size:12px;line-height:16px;color:${theme.textSecondary};font-weight:700;">${esc(numberText(item.share, 'percent', ''))}</span>` : ''}
                  </div>
                  <div data-id="distribution-summary-${summaryIndex}" style="position:absolute;left:0;right:0;top:0;bottom:0;cursor:default;"></div>
                </div>
              `).join('')}
            </div>
            <div data-id="distribution-plot" style="display:grid;grid-template-columns:26px minmax(0,1fr);grid-template-rows:${chartHeight}px auto;column-gap:7px;row-gap:7px;min-width:0;overflow:hidden;padding:4px 4px 0 0;align-self:center;">
              <div style="grid-column:1;grid-row:1;display:flex;flex-direction:column;justify-content:space-between;align-items:flex-end;height:${chartHeight}px;padding-top:${labelBand}px;box-sizing:border-box;color:${theme.textHint};font-size:11px;line-height:14px;font-weight:650;font-variant-numeric:tabular-nums;">
                <span>${esc(numberText(maxValue, 'integer', ''))}</span>
                <span>0</span>
              </div>
              <div style="grid-column:2;grid-row:1;position:relative;height:${chartHeight}px;min-width:0;border-bottom:1px solid ${theme.border};">
                <div style="position:absolute;left:0;right:0;top:${labelBand}px;border-top:1px solid ${theme.border};"></div>
                <div style="position:absolute;left:0;right:0;top:${(labelBand + plotHeight / 2).toFixed(1)}px;border-top:1px solid ${theme.border};opacity:0.55;"></div>
                <div style="position:absolute;left:0;right:0;top:${labelBand}px;height:${plotHeight}px;display:grid;grid-template-columns:repeat(4,minmax(42px,1fr));column-gap:${compactMode ? 7 : 12}px;align-items:end;">
                  ${rows.map((row, rowIndex) => {
                    const value = Number(row.value) || 0;
                    const share = maxValue > 0 ? Math.max(0, Math.min(100, value * 100 / maxValue)) : 0;
                    const fillHeight = value > 0
                      ? Math.max(5, Math.min(plotHeight, plotHeight * share / 100))
                      : 0;
                    const valueBottom = value > 0 ? fillHeight + 4 : 2;
                    return `
                      <div style="position:relative;height:${plotHeight}px;min-width:0;">
                        <div data-id="distribution-value-${rowIndex}" style="position:absolute;left:50%;bottom:${valueBottom.toFixed(1)}px;transform:translateX(-50%);font-size:14px;line-height:18px;color:${theme.text};font-weight:800;font-variant-numeric:tabular-nums;">${esc(numberText(value, 'integer', ''))}</div>
                        ${value > 0 ? `<div data-id="distribution-bar-${rowIndex}" style="position:absolute;left:50%;bottom:0;transform:translateX(-50%);width:${barWidth}px;height:${fillHeight.toFixed(1)}px;border-radius:3px 3px 0 0;background:${themedColor(row.color || '#2B75E2')};"></div>` : ''}
                        <div data-id="distribution-row-${rowIndex}" style="position:absolute;left:0;right:0;top:0;bottom:0;cursor:default;"></div>
                      </div>
                    `;
                  }).join('')}
                </div>
              </div>
              <div style="grid-column:2;grid-row:2;display:grid;grid-template-columns:repeat(4,minmax(42px,1fr));column-gap:${compactMode ? 7 : 12}px;min-width:0;">
                ${rows.map(row => `<div style="font-size:11px;line-height:14px;color:${theme.textSecondary};font-weight:750;text-align:center;white-space:normal;">${esc(row.label)}</div>`).join('')}
              </div>
            </div>
          </div>
        `;
      }

      function renderReadiness() {
        const rows = data.rows || [];
        const readinessHeader = `
          <div style="padding:8px 10px;background:${theme.neutral};color:${theme.textSecondary};font-size:10px;line-height:13px;font-weight:800;letter-spacing:0.08em;">SOURCE</div>
          <div style="padding:8px 10px;background:${theme.neutral};color:${theme.textSecondary};font-size:10px;line-height:13px;font-weight:800;letter-spacing:0.08em;">DESCRIPTION</div>
          <div style="padding:8px 10px;background:${theme.neutral};color:${theme.textSecondary};font-size:10px;line-height:13px;font-weight:800;letter-spacing:0.08em;">STATUS</div>
          <div style="padding:8px 10px;background:${theme.neutral};color:${theme.textSecondary};font-size:10px;line-height:13px;font-weight:800;letter-spacing:0.08em;">ROWS</div>
          <div style="padding:8px 10px;background:${theme.neutral};color:${theme.textSecondary};font-size:10px;line-height:13px;font-weight:800;letter-spacing:0.08em;">MIN — MAX DATE</div>
          <div style="padding:8px 10px;background:${theme.neutral};color:${theme.textSecondary};font-size:10px;line-height:13px;font-weight:800;letter-spacing:0.08em;">FRESHNESS</div>
        `;
        let readinessRows = '';
        rows.forEach(row => {
          const statusColor = row.tone === 'positive' ? 'var(--g-color-text-positive,#0B8043)' : row.tone === 'warning' ? 'var(--g-color-text-warning,#9A6700)' : 'var(--g-color-text-danger,#B3261E)';
          const statusBg = row.tone === 'positive' ? 'var(--g-color-base-positive-light,#E6F4EA)' : row.tone === 'warning' ? 'var(--g-color-base-warning-light,#FFF4E5)' : 'var(--g-color-base-danger-light,#FDECEC)';
          readinessRows += `
            <div style="padding:8px 10px;border-top:1px solid ${theme.border};color:${theme.text};font-size:11px;line-height:15px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${safeHref(row.link) ? `<a href="${esc(safeHref(row.link))}" target="_blank" style="color:var(--g-color-text-link,#1A73E8);text-decoration:none;">${esc(row.label)}</a>` : esc(row.label)}</div>
            <div style="padding:8px 10px;border-top:1px solid ${theme.border};color:${theme.textSecondary};font-size:11px;line-height:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(row.description || '')}</div>
            <div style="padding:8px 10px;border-top:1px solid ${theme.border};"><span style="padding:3px 6px;border-radius:999px;background:${statusBg};color:${statusColor};font-size:10px;font-weight:800;">${esc(row.status)}</span></div>
            <div style="padding:8px 10px;border-top:1px solid ${theme.border};color:${theme.textSecondary};font-size:11px;line-height:15px;">${esc(numberText(row.rows, 'integer', ''))}</div>
            <div style="padding:8px 10px;border-top:1px solid ${theme.border};color:${theme.textSecondary};font-size:11px;line-height:15px;white-space:nowrap;">${esc(row.period || '—')}</div>
            <div style="padding:8px 10px;border-top:1px solid ${theme.border};color:${theme.textSecondary};font-size:11px;line-height:15px;">${esc(row.freshness || '')}</div>
          `;
        });
        return `
          ${header()}
          <div style="display:grid;grid-template-columns:minmax(125px,1.1fr) minmax(155px,1.5fr) 78px 78px 132px minmax(145px,1.2fr);gap:0;border:1px solid ${theme.border};border-radius:12px;overflow:hidden;min-height:0;">
            ${readinessHeader}
            ${readinessRows}
          </div>
        `;
      }

      function renderDetails() {
        const columns = data.columns || [];
        const rows = data.rows || [];
        const templateParts = [];
        let detailsHeader = '';
        columns.forEach(column => {
          templateParts.push(`${column.width || 120}px`);
          detailsHeader += `<div style="padding:9px 10px;background:${theme.neutral};border-right:1px solid ${theme.border};color:${theme.textSecondary};font-size:10px;line-height:13px;font-weight:800;letter-spacing:0.06em;">${esc(column.label)}</div>`;
        });
        const template = templateParts.join(' ');
        let detailsRows = '';
        rows.forEach((row, rowIndex) => {
          let detailsCells = '';
          columns.forEach(column => {
            detailsCells += `<div style="padding:8px 10px;border-top:1px solid ${theme.border};border-right:1px solid ${theme.border};color:${column.key === 'status' ? theme.text : theme.textSecondary};font-size:11px;line-height:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(row[column.key] ?? '—')}</div>`;
          });
          detailsRows += `
            <div style="display:grid;grid-template-columns:${template};min-width:max-content;background:${rowIndex % 2 ? theme.neutral : theme.surface};">
              ${detailsCells}
            </div>
          `;
        });
        return `
          ${header()}
          <div style="overflow:auto;min-height:0;border:1px solid ${theme.border};border-radius:14px;background:${theme.surface};">
            <div style="display:grid;grid-template-columns:${template};min-width:max-content;position:sticky;top:0;z-index:2;">
              ${detailsHeader}
            </div>
            ${detailsRows}
          </div>
        `;
      }

      function renderEmpty() {
        return `
          ${header()}
          <div style="flex:1;display:flex;align-items:center;justify-content:center;min-height:120px;border:1px dashed ${theme.border};border-radius:16px;background:${theme.neutral};padding:20px;">
            <div style="max-width:520px;text-align:center;">
              <div style="font-size:28px;line-height:32px;font-weight:800;color:${theme.textHint};">N/A</div>
              <div style="margin-top:8px;font-size:12px;line-height:18px;color:${theme.textSecondary};">${esc(data.message || '')}</div>
              ${data.expectedSource ? `<div style="margin-top:10px;font-size:10px;line-height:14px;color:${theme.textHint};">Expected source: ${esc(data.expectedSource)}</div>` : ''}
            </div>
          </div>
        `;
      }

      let body = '';
      if (data.kind === 'kpi-strip') body = renderKpiStrip();
      else if (data.kind === 'metric-tile') body = renderKpiCard();
      else if (data.kind === 'kpi-section-header') body = renderKpiSectionHeader();
      else if (data.kind === 'section-header') body = renderSectionHeader();
      else if (data.kind === 'table-header') body = renderTableHeader();
      else if (data.kind === 'comparison-context') body = renderComparisonContext();
      else if (data.kind === 'combo') body = renderCombo();
      else if (data.kind === 'status-cards') body = renderStatusCards();
      else if (data.kind === 'horizontal') body = renderHorizontal();
      else if (data.kind === 'distribution') body = renderDistribution();
      else if (data.kind === 'readiness') body = renderReadiness();
      else if (data.kind === 'details') body = renderDetails();
      else body = renderEmpty();

      return Editor.generateHtml(`
        <div style="box-sizing:border-box;width:100%;height:100%;min-width:0;min-height:0;padding:${compactMode ? 9 : 11}px ${compactMode ? 10 : 13}px;background:${theme.background};color:${theme.text};font-family:Inter,Arial,sans-serif;display:flex;flex-direction:column;gap:${compactMode ? 7 : 9}px;overflow:hidden;">
          ${body}
        </div>
      `);
    }
  });
}

function createChart(chartData) {
  return {
    render: createRender(chartData),
    tooltip: {
      renderer: Editor.wrapFn({
        args: [chartData],
        fn: function(event, data) {
          const id = event.target?.getAttribute('data-id') || '';
          let title = '';
          let body = '';
          let content = '';

          function escapeHtml(value) {
            return String(value ?? '')
              .replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;');
          }

          function finiteValue(value) {
            if (value === null || value === undefined || value === '') return null;
            const numeric = Number(value);
            return Number.isFinite(numeric) ? numeric : null;
          }

          function formatValue(value, format, unit) {
            const numeric = finiteValue(value);
            if (numeric === null) return 'N/A';
            function groupedFixed(source, decimalPlaces) {
              const rounded = Math.abs(source).toFixed(decimalPlaces);
              const parts = rounded.split('.');
              const groupedInteger = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '\u00A0');
              return `${source < 0 ? '-' : ''}${groupedInteger}${decimalPlaces ? `,${parts[1]}` : ''}`;
            }
            let rendered = '';
            if (format === 'percent') {
              rendered = `${groupedFixed(numeric, 1)}%`;
            } else if (format === 'decimal1') {
              rendered = groupedFixed(numeric, 1);
            } else if (format === 'decimal2') {
              rendered = groupedFixed(numeric, 2);
            } else {
              rendered = groupedFixed(numeric, 0);
            }
            return unit ? `${rendered} ${unit}` : rendered;
          }

          function formatDate(value) {
            const raw = String(value || '').slice(0, 10);
            if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw || '—';
            return `${raw.slice(8, 10)}.${raw.slice(5, 7)}.${raw.slice(2, 4)}`;
          }

          function formatDateRange(value) {
            const parts = String(value || '').split(' — ').filter(Boolean);
            if (!parts.length) return '—';
            if (parts.length === 1) return formatDate(parts[0]);
            return `${formatDate(parts[0])}–${formatDate(parts[1])}`;
          }

          function grainScope(value, source = data) {
            const grain = String(source?.grain || data.grain || 'period').toUpperCase();
            const label = grain === 'DAY' || grain === 'WEEK' || grain === 'MONTH'
              ? grain
              : 'PERIOD';
            return `${label} · ${formatDateRange(value)}`;
          }

          function comparisonLabelText(source = data) {
            return String(
              source?.comparisonLabel
              || source?.previousLabel
              || data.comparisonLabel
              || data.previousLabel
              || 'COMPARISON'
            ).trim();
          }

          function rangePair(currentRange, comparisonRange, source = data) {
            return `
              <div style="margin-top:5px;display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:11px;line-height:15px;color:var(--g-color-text-secondary,#667085);">
                <div style="font-weight:800;color:var(--g-color-text-primary,#111827);">${escapeHtml(grainScope(currentRange, source))}</div>
                <div style="font-weight:800;color:var(--g-color-text-primary,#111827);">VS ${escapeHtml(grainScope(comparisonRange, source))}</div>
              </div>
            `;
          }

          function tooltipColor(value) {
            const raw = String(value || '');
            const normalized = raw.toUpperCase();
            if (normalized === '#111827') return 'var(--g-color-text-primary,#111827)';
            if (normalized === '#5F6368' || normalized === '#667085') {
              return 'var(--g-color-text-secondary,#667085)';
            }
            if (normalized === '#D0D5DD') return 'var(--g-color-line-generic,#D0D5DD)';
            return raw || '#2B75E2';
          }

          function deltaMeta(currentValue, comparisonValue) {
            const current = finiteValue(currentValue);
            const comparison = finiteValue(comparisonValue);
            if (current === null || comparison === null || comparison === 0) {
              return {
                text: 'n/a',
                color: 'var(--g-color-text-hint,#98A2B3)'
              };
            }
            const difference = current - comparison;
            const percent = difference * 100 / Math.abs(comparison);
            const percentText = `${percent > 0 ? '+' : ''}${percent.toFixed(1).replace('.', ',')}%`;
            return {
              text: percentText,
              color: difference > 0 ? 'var(--g-color-text-positive,#12B76A)' : difference < 0 ? 'var(--g-color-text-danger,#F04438)' : 'var(--g-color-text-hint,#98A2B3)'
            };
          }

          function metricRows(items, currentIndex, hasComparison) {
            return (items || []).map(item => {
              const currentValue = data.hasCurrentData === false ? null : (item.values || [])[currentIndex];
              const comparisonValue = data.hasCurrentData === false ? null : (item.comparisonValues || [])[currentIndex];
              const delta = deltaMeta(currentValue, comparisonValue);
              return `
                <div style="padding-top:8px;margin-top:8px;border-top:1px solid var(--g-color-line-generic,#EAECF0);">
                  <div style="display:flex;align-items:center;gap:7px;color:var(--g-color-text-secondary,#667085);font-size:11px;line-height:15px;">
                    <span style="display:inline-block;width:8px;height:8px;border-radius:${item.type === 'line' ? '999px' : '2px'};background:${tooltipColor(item.color)};"></span>
                    <span style="font-weight:750;">${escapeHtml(item.name || '')}</span>
                  </div>
                  <div style="margin-top:4px;display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                    <div>
                      <div style="font-size:10px;line-height:13px;color:var(--g-color-text-hint,#98A2B3);font-weight:750;">CURRENT</div>
                      <div style="font-size:14px;line-height:18px;font-weight:800;color:var(--g-color-text-primary,#111827);">${escapeHtml(formatValue(currentValue, item.format || 'integer', item.unit || ''))}</div>
                    </div>
                    ${hasComparison ? `<div><div style="font-size:10px;line-height:13px;color:var(--g-color-text-hint,#98A2B3);font-weight:750;">VS</div><div style="font-size:14px;line-height:18px;font-weight:800;color:var(--g-color-text-primary,#111827);">${escapeHtml(formatValue(comparisonValue, item.format || 'integer', item.unit || ''))}</div></div>` : ''}
                  </div>
                  ${hasComparison ? `<div style="margin-top:3px;font-size:11px;line-height:15px;color:${delta.color};font-weight:700;">Change: ${escapeHtml(delta.text)}</div>` : ''}
                </div>
              `;
            }).join('');
          }

          if (id === 'chart-hint') {
            title = String(data.title || '');
            body = String(data.subtitle || '');
          } else if (id.startsWith('card-hint-')) {
            const cardIndex = Number(id.slice('card-hint-'.length));
            const card = (data.cards || [])[cardIndex] || {};
            title = String(card.label || '');
            body = String(card.note || '');
          } else if (id.startsWith('status-card-')) {
            const cardIndex = Number(id.slice('status-card-'.length));
            const card = (data.cards || [])[cardIndex] || {};
            title = String(card.label || '');
            const available = card.available !== false && data.hasCurrentData !== false;
            content = `
              <div style="margin-top:6px;font-size:14px;line-height:18px;font-weight:800;color:var(--g-color-text-primary,#111827);">${available ? escapeHtml(formatValue(card.value, card.format || 'decimal2', card.unit || '')) : 'N/A'}</div>
              ${card.note ? `<div style="margin-top:4px;font-size:11px;line-height:15px;color:var(--g-color-text-secondary,#667085);">${escapeHtml(card.note)}</div>` : ''}
            `;
          } else if (id.startsWith('horizontal-row-')) {
            const rowIndex = Number(id.slice('horizontal-row-'.length));
            const row = (data.rows || [])[rowIndex] || {};
            const currentValue = data.hasCurrentData === false ? null : (row.values || [])[0];
            const comparisonValue = data.hasCurrentData === false ? null : (row.values || [])[1];
            const comparison = finiteValue(comparisonValue);
            const delta = deltaMeta(currentValue, comparisonValue);
            title = String(row.label || '');
            content = (data.series || []).map((seriesItem, seriesIndex) => `
              <div style="${seriesIndex ? 'margin-top:6px;' : 'margin-top:4px;'}display:flex;align-items:center;justify-content:space-between;gap:14px;">
                <div style="display:flex;align-items:center;gap:7px;font-size:11px;line-height:15px;color:var(--g-color-text-secondary,#667085);"><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${tooltipColor(seriesItem.color)};opacity:${seriesIndex ? 0.6 : 1};"></span>${escapeHtml(seriesItem.name || '')}</div>
                <div style="font-size:13px;line-height:17px;font-weight:800;color:var(--g-color-text-primary,#111827);">${escapeHtml(formatValue(data.hasCurrentData === false ? null : (row.values || [])[seriesIndex], data.valueFormat || 'integer', data.unit || ''))}</div>
              </div>
            `).join('');
            if (comparison !== null) {
              content += `<div style="margin-top:6px;padding-top:6px;border-top:1px solid var(--g-color-line-generic,#EAECF0);font-size:11px;line-height:15px;color:${delta.color};font-weight:700;">Δ ${escapeHtml(delta.text)}</div>`;
            }
          } else if (id.startsWith('distribution-summary-')) {
            const summaryIndex = Number(id.slice('distribution-summary-'.length));
            const summary = (data.summaries || [])[summaryIndex] || {};
            title = String(summary.label || '');
            content = `
              <div style="margin-top:5px;font-size:14px;line-height:18px;font-weight:800;color:var(--g-color-text-primary,#111827);">${escapeHtml(formatValue(summary.value, 'integer', ''))}</div>
              ${finiteValue(summary.share) !== null ? `<div style="font-size:11px;line-height:15px;color:var(--g-color-text-secondary,#667085);">Share: ${escapeHtml(formatValue(summary.share, 'percent', ''))}</div>` : ''}
            `;
          } else if (id.startsWith('distribution-row-')) {
            const rowIndex = Number(id.slice('distribution-row-'.length));
            const row = (data.rows || [])[rowIndex] || {};
            title = String(row.label || '');
            content = `<div style="margin-top:5px;font-size:14px;line-height:18px;font-weight:800;color:var(--g-color-text-primary,#111827);">${escapeHtml(formatValue(row.value, 'integer', ''))}</div>`;
          } else if (id.startsWith('combo-bucket-')) {
            const bucketIndex = Number(id.slice('combo-bucket-'.length));
            if (!Number.isFinite(bucketIndex)) return null;
            const currentRange = (data.currentRanges || [])[bucketIndex]
              || (data.categories || [])[bucketIndex];
            const comparisonRange = (data.comparisonRanges || [])[bucketIndex]
              || (data.comparisonCategories || [])[bucketIndex];
            title = String(data.title || '');
            content = `
              ${rangePair(currentRange, comparisonRange)}
              ${metricRows(data.series || [], bucketIndex, Boolean(comparisonRange))}
            `;
          } else if (id.startsWith('card-bucket-')) {
            const match = id.match(/^card-bucket-(\d+)-(\d+)$/);
            if (!match) return null;
            const cardIndex = Number(match[1]);
            const bucketIndex = Number(match[2]);
            const card = (data.cards || [])[cardIndex] || {};
            const cardCategories = Array.isArray(card.sparklineCategories) && card.sparklineCategories.length
              ? card.sparklineCategories
              : (data.categories || []);
            const cardComparisonRanges = Array.isArray(card.comparisonRanges) && card.comparisonRanges.length
              ? card.comparisonRanges
              : (data.comparisonRanges || []);
            const cardComparisonCategories = Array.isArray(card.comparisonCategories) && card.comparisonCategories.length
              ? card.comparisonCategories
              : (data.comparisonCategories || []);
            const cardCurrentRanges = Array.isArray(card.currentRanges) && card.currentRanges.length
              ? card.currentRanges
              : (data.currentRanges || []);
            const currentRange = cardCurrentRanges[bucketIndex]
              || cardCategories[bucketIndex];
            const comparisonRange = cardComparisonRanges[bucketIndex]
              || cardComparisonCategories[bucketIndex];
            const currentValue = data.hasCurrentData === false ? null : (card.sparkline || [])[bucketIndex];
            const comparisonValue = data.hasCurrentData === false ? null : (card.comparisonSparkline || [])[bucketIndex];
            const delta = deltaMeta(currentValue, comparisonValue);
            title = '';
            content = `
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
                <div>
                  <div style="font-size:10px;line-height:13px;color:var(--g-color-text-hint,#98A2B3);font-weight:800;">${escapeHtml(grainScope(currentRange, card))}</div>
                  <div style="margin-top:3px;font-size:15px;line-height:19px;font-weight:800;color:var(--g-color-text-primary,#111827);">${escapeHtml(formatValue(currentValue, card.format || 'integer', card.unit || ''))}</div>
                </div>
                <div>
                  <div style="font-size:10px;line-height:13px;color:var(--g-color-text-hint,#98A2B3);font-weight:800;">VS ${escapeHtml(grainScope(comparisonRange, card))}</div>
                  <div style="margin-top:3px;font-size:15px;line-height:19px;font-weight:800;color:var(--g-color-text-primary,#111827);">${escapeHtml(formatValue(comparisonValue, card.format || 'integer', card.unit || ''))}</div>
                </div>
              </div>
              <div style="margin-top:6px;font-size:11px;line-height:15px;color:${delta.color};font-weight:750;">Change: ${escapeHtml(delta.text)}</div>
            `;
          }
          if (!body && !content) return null;
          return Editor.generateHtml(`
            <div style="min-width:220px;max-width:340px;padding:10px 12px;border:0;border-radius:0;background:var(--g-color-base-float,#FFFFFF);color:var(--g-color-text-primary,#111827);font-family:Inter,Arial,sans-serif;">
              ${title ? `<div style="font-size:12px;line-height:16px;font-weight:800;color:var(--g-color-text-primary,#111827);">${escapeHtml(title)}</div>` : ''}
              ${body ? `<div style="margin-top:${title ? 5 : 0}px;font-size:12px;line-height:17px;color:var(--g-color-text-secondary,#667085);white-space:pre-line;">${escapeHtml(body)}</div>` : ''}
              ${content}
            </div>
          `);
        }
      })
    }
  };
}
