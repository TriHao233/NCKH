export const QUESTION_TYPES = [
  { id: 'mcq', label: 'Trắc nghiệm (MCQ)', backend: 'trac_nghiem' },
  { id: 'multi', label: 'Nhiều lựa chọn', backend: 'nhieu_lua_chon' },
  { id: 'tf', label: 'Đúng / Sai', backend: 'dung_sai' },
  { id: 'fill', label: 'Điền khuyết', backend: 'dien_khuyet' },
  { id: 'match', label: 'Ghép đôi', backend: 'ghep_cot' },
  { id: 'order', label: 'Sắp xếp', backend: 'sap_xep' },
  { id: 'scenario', label: 'Tình huống', backend: 'tinh_huong' },
];

export const BLOOM_LEVELS = [
  { id: 'remember', level: 1, label: '1. Nhớ', caption: 'Thuật ngữ, định nghĩa', backend: '1_nho' },
  { id: 'understand', level: 2, label: '2. Hiểu', caption: 'Diễn giải nguyên lý', backend: '2_hieu' },
  { id: 'apply', level: 3, label: '3. Vận dụng', caption: 'Áp dụng vào bài toán', backend: '3_van_dung' },
  { id: 'analyze', level: 4, label: '4. Phân tích', caption: 'Tách ý, so sánh', backend: '4_phan_tich' },
  { id: 'evaluate', level: 5, label: '5. Đánh giá', caption: 'Nhận xét, lựa chọn', backend: '5_danh_gia' },
  { id: 'create', level: 6, label: '6. Sáng tạo', caption: 'Thiết kế giải pháp', backend: '6_sang_tao' },
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
