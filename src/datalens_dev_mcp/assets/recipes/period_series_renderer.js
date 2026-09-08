/* Period-aligned line/bar composition. Prepared input owns period and aggregation semantics. */
module.exports = function renderPeriodSeries(prepared, presentation) {
  const chartData = {...prepared, title: presentation.visible_title.text || prepared.title || '',
    subtitle: presentation.hint.enabled ? (presentation.hint.text || prepared.subtitle || '') : '', kind: 'combo'};
  return {
    render: Editor.wrapFn({args: [chartData, presentation], fn: function(options, data, presentation) {
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

      function header() {
        if (!presentation.visible_title.visible || presentation.visible_title.owner !== "body") return "";
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

        let primaryMax = 0;
        let secondaryMax = 0;
        let primaryMin = 0;
        let secondaryMin = 0;
        if (data.stacked) {
          categories.forEach((_category, index) => {
            let positive = 0, negative = 0;
            bars.forEach(item => {
              const numeric = finiteValue(item.values?.[index]);
              if (numeric !== null) {
                if (numeric >= 0) positive += numeric;
                else negative += numeric;
              }
            });
            primaryMax = Math.max(primaryMax, positive);
            primaryMin = Math.min(primaryMin, negative);
          });
        } else {
          bars.forEach(item => {
            (item.values || []).forEach(value => {
              const numeric = finiteValue(value);
              if (numeric !== null) {
                primaryMax = Math.max(primaryMax, numeric);
                primaryMin = Math.min(primaryMin, numeric);
              }
            });
          });
        }
        lines.forEach(item => {
          (item.values || []).concat(item.comparisonValues || []).forEach(value => {
            const numericValue = finiteValue(value);
            if (numericValue === null) return;
            if (item.axis === 'right') {
              secondaryMax = Math.max(secondaryMax, numericValue);
              secondaryMin = Math.min(secondaryMin, numericValue);
            } else {
              primaryMax = Math.max(primaryMax, numericValue);
              primaryMin = Math.min(primaryMin, numericValue);
            }
          });
        });

        function niceScale(maxValue, requestedMax, minValue = 0) {
          if (minValue < 0) {
            // Reuse the accepted tick spacing, extending the domain on both sides of zero.
            const positiveLimit = finiteValue(requestedMax);
            const upper = positiveLimit !== null && positiveLimit > 0 ? positiveLimit : maxValue;
            const span = niceScale(upper - minValue, null);
            const step = span.ticks[1] - span.ticks[0];
            const min = Math.floor(minValue / step) * step;
            const max = Math.ceil(upper / step) * step;
            return {min, max, ticks: Array.from(
              {length: Math.round((max - min) / step) + 1},
              (_unused, index) => min + index * step
            )};
          }
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
        const primaryScale = niceScale(primaryMin < 0 ? primaryMax : Math.max(1, primaryMax), data.primaryScaleMax, primaryMin);
        const secondaryScale = niceScale(secondaryMin < 0 ? secondaryMax : Math.max(1, secondaryMax), data.secondaryScaleMax, secondaryMin);
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
        function scaleY(value, scale = primaryScale) {
          const min = scale.min || 0;
          return plot.top + plotHeight - ((value - min) / (scale.max - min)) * plotHeight;
        }
        const zeroY = scaleY(0);
        const times = data.time_mode === 'temporal' && Array.isArray(data.timestamps) ? data.timestamps : [];
        const temporal = times.length === categories.length && times.length > 1 && times.every(Number.isFinite);
        const duration = temporal ? times[times.length - 1] - times[0] : 0;
        const step = temporal ? Math.min(...times.slice(1).map((time, i) => time - times[i])) : 0;
        const spacing = temporal && duration > 0 ? plotWidth * step / (duration + step)
          : plotWidth / Math.max(1, categories.length);
        const centerAt = index => temporal && duration > 0
          ? plot.left + spacing / 2 + (times[index] - times[0]) / duration * (plotWidth - spacing)
          : plot.left + spacing * index + spacing / 2;
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
        const barLabelMagnitudes = categories.map((_category, index) =>
          bars.reduce((total, item) => {
            const numeric = finiteValue(item.values?.[index]);
            return numeric === null ? total : total + Math.abs(numeric);
          }, 0)
        );
        const barLabelIndices = valueLabelIndexSet(barLabelMagnitudes, dataLabelCapacity);

        categories.forEach((_category, categoryIndex) => {
          const centerX = centerAt(categoryIndex);
          if (data.stacked) {
            let positiveTotal = 0;
            let negativeTotal = 0;
            const renderedBarWidth = Math.max(8, Math.min(38, spacing * 0.38));
            bars.forEach(item => {
              const itemColor = themedColor(item.color);
              const numeric = finiteValue(item.values?.[categoryIndex]);
              if (numeric === null) return;
              const value = numeric;
              const start = value >= 0 ? positiveTotal : negativeTotal;
              const end = start + value;
              const barHeight = Math.abs(scaleY(end) - scaleY(start));
              const y = Math.min(scaleY(start), scaleY(end));
              marks += `<rect x="${(centerX - renderedBarWidth / 2).toFixed(1)}" y="${y.toFixed(1)}" width="${renderedBarWidth.toFixed(1)}" height="${Math.max(0, barHeight).toFixed(1)}" rx="3" fill="${itemColor}" opacity="0.90" />`;
              if (item.showBarLabels !== false && value !== 0 && barHeight >= 17 && barLabelIndices[categoryIndex]) {
                const segmentTextColor = item.color === '#D0D5DD' ? theme.textSecondary : '#FFFFFF';
                valueLabels += `<text x="${centerX.toFixed(1)}" y="${(y + barHeight / 2 + 4).toFixed(1)}" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-size="12" font-weight="600" letter-spacing="0" fill="${segmentTextColor}">${esc(numberText(value, item.format || data.primaryFormat || 'integer', item.labelUnit !== undefined ? item.labelUnit : ''))}</text>`;
              }
              if (value >= 0) positiveTotal = end;
              else negativeTotal = end;
            });
            [positiveTotal, negativeTotal].forEach(stackedTotal => {
              if (stackedTotal === 0 || bars.length <= 1 || !barLabelIndices[categoryIndex]) return;
              const labelY = stackedTotal > 0 ? Math.max(13, scaleY(stackedTotal) - 7)
                : Math.min(height - plot.bottom + 16, scaleY(stackedTotal) + 15);
              valueLabels += `<text x="${centerX.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-size="12" font-weight="600" letter-spacing="0" fill="${theme.textSecondary}" style="paint-order:stroke;stroke:${theme.halo};stroke-width:3px;stroke-linejoin:round;">${esc(numberText(stackedTotal, data.primaryFormat || 'integer', ''))}</text>`;
            });
          } else {
            const barWidth = Math.max(7, Math.min(34, spacing * 0.46 / Math.max(1, bars.length)));
            bars.forEach((item, barIndex) => {
              const itemColor = themedColor(item.color);
              const numeric = finiteValue(item.values?.[categoryIndex]);
              if (numeric === null) return;
              const value = numeric;
              const barHeight = Math.abs(scaleY(value) - zeroY);
              const x = centerX - (barWidth * bars.length) / 2 + barWidth * barIndex;
              const y = Math.min(zeroY, scaleY(value));
              marks += `<rect x="${(x + 2).toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(3, barWidth - 4).toFixed(1)}" height="${Math.max(0, barHeight).toFixed(1)}" rx="3" fill="${itemColor}" opacity="0.90" />`;
              if (item.showBarLabels !== false && value !== 0 && barLabelIndices[categoryIndex]) {
                valueLabels += `<text x="${(x + barWidth / 2).toFixed(1)}" y="${(value >= 0 ? Math.max(13, y - 7) : Math.min(height - plot.bottom + 16, y + barHeight + 15)).toFixed(1)}" text-anchor="middle" font-family="Inter,Arial,sans-serif" font-size="12" font-weight="600" letter-spacing="0" fill="${theme.textSecondary}" style="paint-order:stroke;stroke:${theme.halo};stroke-width:3px;stroke-linejoin:round;">${esc(numberText(value, item.format || data.primaryFormat || 'integer', item.labelUnit !== undefined ? item.labelUnit : item.unit || ''))}</text>`;
              }
            });
          }
        });

        function pointSegments(values, scale) {
          const segments = [];
          let currentSegment = [];
          (values || []).forEach((value, index) => {
            const numeric = finiteValue(value);
            if (numeric === null) {
              if (currentSegment.length) segments.push(currentSegment);
              currentSegment = [];
              return;
            }
            const x = centerAt(index);
            const y = scaleY(numeric, scale);
            currentSegment.push({x, y, value: numeric, index});
          });
          if (currentSegment.length) segments.push(currentSegment);
          return segments;
        }

        lines.forEach((item, lineIndex) => {
          const itemColor = themedColor(item.color);
          const comparisonColor = themedColor(item.comparisonColor || item.color);
          const scale = item.axis === 'right' ? secondaryScale : primaryScale;
          const segments = pointSegments(item.values || [], scale);
          const comparisonSegments = item.showComparisonLine === false
            ? []
            : pointSegments(item.comparisonValues || [], scale);
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
                let nearestBarTop = zeroY;
                const belowZero = point.y > zeroY;
                if (data.stacked) {
                  const stackedValue = bars.reduce((total, bar) => {
                    const numeric = finiteValue(bar.values?.[point.index]);
                    if (numeric === null || (belowZero ? numeric >= 0 : numeric < 0)) return total;
                    return total + numeric;
                  }, 0);
                  nearestBarTop = scaleY(stackedValue);
                } else {
                  bars.forEach(bar => {
                    const numeric = finiteValue(bar.values?.[point.index]);
                    if (numeric === null) return;
                    nearestBarTop = belowZero
                      ? Math.max(nearestBarTop, scaleY(numeric))
                      : Math.min(nearestBarTop, scaleY(numeric));
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
          const y = scaleY(value);
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
          const x = centerAt(index);
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
        const xAxisY = plot.top + plotHeight;
        const xAxis = `
          <line x1="${plot.left}" y1="${xAxisY}" x2="${width - plot.right}" y2="${xAxisY}" stroke="${theme.border}" stroke-width="1" />
          ${categories.map((_category, index) => {
            if (!xLabelIndices[index]) return '';
            const x = centerAt(index);
            return `<line x1="${x}" y1="${xAxisY}" x2="${x}" y2="${xAxisY + 4}" stroke="${theme.border}" stroke-width="1" />`;
          }).join('')}
        `;
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
          const x = index === 0 ? plot.left : (centerAt(index - 1) + centerAt(index)) / 2;
          const right = index === categories.length - 1 ? plot.left + plotWidth : (centerAt(index) + centerAt(index + 1)) / 2;
          return `<rect x="${x.toFixed(2)}" y="${plot.top}" width="${(right - x).toFixed(2)}" height="${(plotHeight + plot.bottom).toFixed(2)}" fill="#FFFFFF" opacity="0.001" pointer-events="all" data-id="combo-bucket-${index}" />`;
        }).join('');

        return `
          ${header()}
          ${data.banner ? `<div style="padding:7px 9px;border-radius:10px;background:var(--g-color-base-warning-light,#FFF4E5);color:var(--g-color-text-warning,#9A6700);font-size:12px;line-height:16px;font-weight:700;">${esc(data.banner)}</div>` : ''}
          <div style="display:flex;flex-wrap:wrap;gap:8px 18px;flex:0 0 auto;">${legend}</div>
          <div style="width:100%;flex:1 1 auto;min-height:0;overflow:hidden;">
            <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" style="display:block;width:100%;height:100%;min-width:0;background:${theme.background};overflow:hidden;">
              ${grid}
              ${xAxis}
              ${marks}
              ${valueLabels}
              ${xLabels}
              ${hoverZones}
            </svg>
          </div>
        `;
      }

      const body = data.state === 'error' ? '<div role="status">Data unavailable</div>'
        : data.state === 'loading' ? '<div role="status">Loading…</div>'
        : data.state === 'no_data' || !data.categories.length ? '<div role="status">No data</div>' : renderCombo();
      return Editor.generateHtml(`
        <div style="box-sizing:border-box;width:100%;height:100%;min-width:0;min-height:0;padding:${compactMode ? 9 : 11}px ${compactMode ? 10 : 13}px;background:${theme.background};color:${theme.text};font-family:Inter,Arial,sans-serif;display:flex;flex-direction:column;gap:${compactMode ? 7 : 9}px;overflow:hidden;">
          ${body}
        </div>
      `);
    }}),
    tooltip: {renderer: Editor.wrapFn({args: [chartData], fn: function(event, data) {
      const id = event.target?.getAttribute('data-id') || '';
      let title = '', body = '', content = '';
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
            title = data.title; body = data.subtitle;
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
          }
          if (!body && !content) return null;
          return Editor.generateHtml(`
            <div style="min-width:220px;max-width:340px;padding:10px 12px;border:0;border-radius:0;background:var(--g-color-base-float,#FFFFFF);color:var(--g-color-text-primary,#111827);font-family:Inter,Arial,sans-serif;">
              ${title ? `<div style="font-size:12px;line-height:16px;font-weight:800;color:var(--g-color-text-primary,#111827);">${escapeHtml(title)}</div>` : ''}
              ${body ? `<div style="margin-top:${title ? 5 : 0}px;font-size:12px;line-height:17px;color:var(--g-color-text-secondary,#667085);white-space:pre-line;">${escapeHtml(body)}</div>` : ''}
              ${content}
            </div>
          `);
    }})}
  };
};
