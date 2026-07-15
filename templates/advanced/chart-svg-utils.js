function linearScale(domainMin, domainMax, rangeMin, rangeMax) {
  return function scale(value) {
    if (domainMax === domainMin) return (rangeMin + rangeMax) / 2;
    return rangeMin + ((Number(value) - domainMin) / (domainMax - domainMin)) * (rangeMax - rangeMin);
  };
}

function buildBandLayout(keys, left, right, gap = 8) {
  const count = Math.max(1, keys.length);
  const total = Math.max(1, right - left);
  const bandwidth = Math.max(1, (total - gap * Math.max(0, count - 1)) / count);
  return {
    bandwidth,
    position(key) {
      const index = Math.max(0, keys.indexOf(key));
      return left + index * (bandwidth + gap);
    },
  };
}

function maxOr(values, fallback = 1) {
  const finite = values.map(Number).filter(Number.isFinite);
  return finite.length ? Math.max(...finite) : fallback;
}

function linePath(points) {
  return points.map((point, index) => `${index ? 'L' : 'M'}${point.x},${point.y}`).join(' ');
}

module.exports = {buildBandLayout, linePath, linearScale, maxOr};
