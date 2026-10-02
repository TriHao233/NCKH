export function suggestVariantCodes(previous, existing, defaults, count) {
  const used = new Set(existing.map((code) => String(code || '').trim()));
  return Array.from({ length: count }, (_, index) => {
    const previousCode = String(previous[index] || '').trim();
    const code = previousCode && !used.has(previousCode)
      ? previous[index]
      : defaults.find((candidate) => !used.has(candidate)) || '';
    if (code) used.add(code.trim());
    return code;
  });
}
