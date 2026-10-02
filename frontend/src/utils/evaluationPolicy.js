// Biểu mẫu bộ tiêu chí đánh giá: trọng số nhập theo %, ngưỡng nhập theo thang 0–1.

export const WEIGHT_FIELDS = [
  { key: 'faithfulness', label: 'Bám sát nguồn' },
  { key: 'contextual_relevancy', label: 'Phù hợp ngữ cảnh' },
  { key: 'answer_relevancy', label: 'Đáp án phù hợp' },
  { key: 'bloom_alignment', label: 'Đúng Bloom' },
  { key: 'clo_alignment', label: 'Đúng CLO' },
];

export const THRESHOLD_FIELDS = [
  { key: 'yellow_min', label: 'Cần xem lại từ', hint: 'Thấp hơn mức này xếp "Rủi ro cao".' },
  { key: 'pass_min', label: 'Điểm đạt', hint: 'Từ mức này AI kết luận "Đạt".' },
  { key: 'green_min', label: 'Đạt tốt từ', hint: 'Từ mức này xếp "Đạt tốt".' },
];

const WEIGHT_LABEL = Object.fromEntries(WEIGHT_FIELDS.map((field) => [field.key, field.label]));
const THRESHOLD_LABEL = Object.fromEntries(THRESHOLD_FIELDS.map((field) => [field.key, field.label]));

export function weightLabel(key) {
  return WEIGHT_LABEL[key] || key;
}

export function weightKeys(weights = {}) {
  const known = WEIGHT_FIELDS.map((field) => field.key);
  return [...known, ...Object.keys(weights).filter((key) => !known.includes(key))];
}

export function weightToPercent(value) {
  return Number(((Number(value) || 0) * 100).toFixed(2));
}

export function formatThreshold(value) {
  return typeof value === 'number' ? value.toFixed(2) : '--';
}

export function policyToForm(policy = {}) {
  const weights = policy.weights || {};
  const thresholds = policy.thresholds || {};
  return {
    policy_name: policy.policy_name || '',
    weights: Object.fromEntries(weightKeys(weights).map((key) => [key, String(weightToPercent(weights[key]))])),
    thresholds: Object.fromEntries(THRESHOLD_FIELDS.map((field) => [field.key, String(thresholds[field.key] ?? '')])),
  };
}

export function weightTotal(form) {
  const total = Object.values(form.weights).reduce((sum, value) => sum + (Number(value) || 0), 0);
  return Number(total.toFixed(2));
}

function isBlank(value) {
  return String(value ?? '').trim() === '';
}

export function validatePolicyForm(form) {
  if (!form.policy_name.trim()) return 'Hãy nhập tên bộ tiêu chí.';
  for (const [key, value] of Object.entries(form.weights)) {
    const number = Number(value);
    if (isBlank(value) || !Number.isFinite(number) || number < 0 || number > 100) {
      return `Trọng số "${weightLabel(key)}" phải là số từ 0 đến 100.`;
    }
  }
  if (Math.abs(weightTotal(form) - 100) > 0.01) {
    return `Tổng trọng số phải bằng 100% (hiện là ${weightTotal(form)}%).`;
  }
  const thresholds = THRESHOLD_FIELDS.map((field) => form.thresholds[field.key]);
  if (thresholds.some((value) => isBlank(value) || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 1)) {
    return 'Ba ngưỡng phải là số từ 0 đến 1.';
  }
  const [yellow, pass, green] = thresholds.map(Number);
  if (!(yellow <= pass && pass <= green)) {
    return 'Ngưỡng phải theo thứ tự: Cần xem lại ≤ Điểm đạt ≤ Đạt tốt.';
  }
  return '';
}

export function formToPayload(form) {
  return {
    policy_name: form.policy_name.trim(),
    weights: Object.fromEntries(
      Object.entries(form.weights).map(([key, value]) => [key, Number((Number(value) / 100).toFixed(4))]),
    ),
    thresholds: Object.fromEntries(THRESHOLD_FIELDS.map((field) => [field.key, Number(form.thresholds[field.key])])),
  };
}

// Liệt kê những gì khác đi giữa hai phiên bản để người đọc không phải tự so.
export function describePolicyChanges(previous, current) {
  if (!previous) return [];
  const changes = [];
  const before = previous.weights || {};
  const after = current.weights || {};
  for (const key of weightKeys({ ...before, ...after })) {
    if (weightToPercent(before[key]) !== weightToPercent(after[key])) {
      changes.push(`${weightLabel(key)}: ${weightToPercent(before[key])}% → ${weightToPercent(after[key])}%`);
    }
  }
  for (const field of THRESHOLD_FIELDS) {
    const from = previous.thresholds?.[field.key];
    const to = current.thresholds?.[field.key];
    if (from !== to) changes.push(`${THRESHOLD_LABEL[field.key]}: ${formatThreshold(from)} → ${formatThreshold(to)}`);
  }
  return changes;
}
