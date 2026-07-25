export const DEFAULT_OPTION_KEYS = ['A', 'B', 'C', 'D'];

export const SINGLE_CHOICE_TYPES = new Set(['trac_nghiem', 'tinh_huong', 'dung_sai']);
export const MULTI_CHOICE_TYPES = new Set(['nhieu_lua_chon']);
export const STRUCTURED_OPTION_TYPES = new Set([
  'trac_nghiem',
  'tinh_huong',
  'dung_sai',
  'nhieu_lua_chon',
  'ghep_cot',
  'sap_xep',
]);

export function normalizeQuestionType(questionType) {
  return String(questionType || '').toLowerCase();
}

export function correctAnswerValues(correctAnswer) {
  return String(correctAnswer || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

export function optionEntriesForQuestion({ questionType, rawOptions }) {
  const normalizedType = normalizeQuestionType(questionType);
  if (!STRUCTURED_OPTION_TYPES.has(normalizedType)) return [];
  if (rawOptions && typeof rawOptions === 'object' && !Array.isArray(rawOptions)) {
    return Object.entries(rawOptions).map(([key, value]) => ({ key, value: String(value ?? '') }));
  }
  if (Array.isArray(rawOptions)) {
    return rawOptions.map((value, index) => ({
      key: DEFAULT_OPTION_KEYS[index] || String(index + 1),
      value: String(value ?? ''),
    }));
  }
  if (normalizedType === 'dung_sai') {
    return [
      { key: 'A', value: 'Đúng' },
      { key: 'B', value: 'Sai' },
    ];
  }
  if (['trac_nghiem', 'tinh_huong', 'nhieu_lua_chon'].includes(normalizedType)) {
    return DEFAULT_OPTION_KEYS.map((key) => ({ key, value: '' }));
  }
  return [];
}

export function entriesToOptions(entries) {
  return Object.fromEntries(entries.map((entry) => [entry.key, entry.value]));
}

export function joinCorrectValues(values, entries) {
  const selected = new Set(values);
  const ordered = entries
    .map((entry) => entry.key)
    .filter((key) => selected.has(key));
  return ordered.join(', ');
}

export function validateQuestionAnswer({ questionType, rawOptions, correctAnswer }) {
  const normalizedType = normalizeQuestionType(questionType);
  if (!String(correctAnswer || '').trim()) {
    return 'Đáp án đúng không được để trống.';
  }
  if (MULTI_CHOICE_TYPES.has(normalizedType) && correctAnswerValues(correctAnswer).length < 2) {
    return 'Câu nhiều lựa chọn cần ít nhất 2 đáp án đúng.';
  }
  const entries = optionEntriesForQuestion({ questionType: normalizedType, rawOptions });
  if (entries.some((entry) => !entry.value.trim())) {
    return 'Các lựa chọn không được để trống.';
  }
  return null;
}
