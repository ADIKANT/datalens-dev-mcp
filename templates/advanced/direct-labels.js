function truncateLabel(value, maxLength = 18) {
  const text = String(value == null ? '' : value);
  return text.length > maxLength ? `${text.slice(0, Math.max(1, maxLength - 1))}...` : text;
}

module.exports = {truncateLabel};
