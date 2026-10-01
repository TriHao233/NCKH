export function scoreToPercent(score) { return score == null ? '' : String(Number((score * 100).toFixed(6))); }
export function percentToScore(percent) {
  if (String(percent).trim() === '') return null;
  const value = Number(percent);
  if (!Number.isFinite(value) || value < 0 || value > 100) throw new Error('Điểm AI phải từ 0 đến 100%.');
  return value / 100;
}
