export const QUESTION_TYPES = [
  { id: 'mcq', label: 'Trắc nghiệm (MCQ)', backend: 'trac_nghiem' },
  { id: 'tf', label: 'Đúng / Sai', backend: 'dung_sai' },
  { id: 'fill', label: 'Điền khuyết', backend: 'dien_khuyet' },
  { id: 'match', label: 'Ghép đôi', backend: 'ghep_cot' },
  { id: 'scenario', label: 'Tình huống', backend: 'tinh_huong' },
];

export const BLOOM_LEVELS = [
  { id: 'remember', label: 'Nhớ', backend: 'nho' },
  { id: 'understand', label: 'Hiểu', backend: 'hieu' },
  { id: 'apply', label: 'Áp dụng', backend: 'van_dung' },
  { id: 'analyze', label: 'Phân tích', backend: 'phan_tich' },
  { id: 'evaluate', label: 'Đánh giá', backend: 'danh_gia' },
  { id: 'create', label: 'Sáng tạo', backend: 'sang_tao' },
];

const questionTypeByUi = Object.fromEntries(QUESTION_TYPES.map((item) => [item.id, item]));
const bloomByUi = Object.fromEntries(BLOOM_LEVELS.map((item) => [item.id, item]));
const questionTypeByBackend = Object.fromEntries(QUESTION_TYPES.map((item) => [item.backend, item]));
const bloomByBackend = Object.fromEntries(BLOOM_LEVELS.map((item) => [item.backend, item]));

export function toBackendQuestionType(uiId) {
  return questionTypeByUi[uiId]?.backend;
}

export function toBackendBloomLevel(uiId) {
  return bloomByUi[uiId]?.backend;
}

export function questionTypeLabel(backendValue) {
  return questionTypeByBackend[backendValue]?.label || backendValue;
}

export function bloomLevelLabel(backendValue) {
  return bloomByBackend[backendValue]?.label || backendValue;
}
