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
  if (normalizedType === 'ghep_cot') {
    return ['1', '2', '3', 'a', 'b', 'c', 'd'].map((key) => ({ key, value: '' }));
  }
  if (['trac_nghiem', 'tinh_huong', 'nhieu_lua_chon', 'sap_xep'].includes(normalizedType)) {
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
  if (normalizedType === 'sap_xep') {
    const answers = correctAnswerValues(correctAnswer);
    const keys = entries.map((entry) => entry.key);
    if (keys.length < 4 || answers.length !== keys.length || new Set(answers).size !== keys.length || answers.some((key) => !keys.includes(key))) {
      return 'Câu sắp xếp cần ít nhất 4 bước; đáp án phải liệt kê mỗi khóa đúng một lần, ví dụ: B, A, D, C.';
    }
  }
  if (normalizedType === 'ghep_cot') {
    const keys = entries.map((entry) => entry.key);
    const numbered = keys.filter((key) => /^\d+$/.test(key));
    const letters = keys.filter((key) => /^[a-z]+$/i.test(key));
    const pairs = correctAnswerValues(correctAnswer).map((value) => value.match(/^(\d+)\s*-\s*([a-z])$/i));
    if (numbered.length < 3 || letters.length < numbered.length + 1 || pairs.length !== numbered.length
      || pairs.some((pair) => !pair || !numbered.includes(pair[1]) || !letters.includes(pair[2]))
      || new Set(pairs.filter(Boolean).map((pair) => pair[1])).size !== numbered.length) {
      return 'Câu ghép đôi cần ít nhất 3 mục số, thêm 1 mục chữ gây nhiễu và đủ cặp đáp án, ví dụ: 1-b, 2-a, 3-c.';
    }
  }
  return null;
}
