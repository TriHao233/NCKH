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
  if (normalizedType === 'sap_xep') {
    return ['1', '2', '3', '4'].map((key) => ({ key, value: '' }));
  }
  if (normalizedType === 'ghep_cot') {
    return ['1', '2', '3', 'a', 'b', 'c', 'd'].map((key) => ({ key, value: '' }));
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
    const keys = entries.map((entry) => entry.key);
    const answer = correctAnswerValues(correctAnswer);
    if (keys.length < 4 || answer.length !== keys.length || new Set(answer).size !== keys.length || answer.some((key) => !keys.includes(key))) {
      return 'Câu sắp xếp cần ít nhất 4 bước; đáp án phải liệt kê mỗi bước đúng một lần theo thứ tự, ví dụ: 2, 1, 4, 3.';
    }
  }
  if (normalizedType === 'ghep_cot') {
    const numbers = entries.map((entry) => entry.key).filter((key) => /^\d+$/.test(key));
    const letters = entries.map((entry) => entry.key).filter((key) => /^[a-z]+$/i.test(key));
    const pairs = correctAnswerValues(correctAnswer).map((part) => /^\s*(\d+)\s*-\s*([a-z]+)\s*$/i.exec(part));
    if (numbers.length < 3 || letters.length < numbers.length + 1 || pairs.length !== numbers.length || pairs.some((pair) => !pair)
      || new Set(pairs.map((pair) => pair[1])).size !== numbers.length
      || new Set(pairs.map((pair) => pair[2])).size !== numbers.length
      || pairs.some((pair) => !numbers.includes(pair[1]) || !letters.includes(pair[2]))) {
      return 'Câu ghép đôi cần ít nhất 3 mục số và thêm 1 mục chữ gây nhiễu; đáp án phải ghép mỗi mục số với một mục chữ khác nhau, ví dụ: 1-b, 2-a, 3-c.';
    }
  }
  return null;
}
