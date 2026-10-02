import { BLOOM_LEVELS } from '../constants/generationEnums.js';

const legacyLevels = { nhan_biet: 'nho', thong_hieu: 'hieu', van_dung_cao: 'phan_tich' };

export const EXAM_BLOOM_LEVELS = BLOOM_LEVELS.map((level) => ({
  ...level,
  value: level.backend.replace(/^\d+_/, ''),
}));

export function examBloomLevel(value) {
  return EXAM_BLOOM_LEVELS.find((level) => level.value === (legacyLevels[value] || value));
}

export function normalizeExamMatrix(cells = []) {
  return cells.map((cell) => ({
    chapter_id: cell.chapter_id || null,
    cognitive_level: examBloomLevel(cell.cognitive_level)?.value || cell.cognitive_level,
    difficulty: cell.difficulty || null,
    count: Number(cell.count),
  }));
}

export function examMatrixError(cells, targetCount) {
  const normalized = normalizeExamMatrix(cells);
  const invalid = normalized.findIndex((cell) => !Number.isInteger(cell.count) || cell.count < 1);
  if (invalid >= 0) return `Dòng ${invalid + 1}: số câu phải là số nguyên ≥ 1.`;
  if (normalized.some((cell) => !examBloomLevel(cell.cognitive_level))) return 'Mức nhận thức Bloom không hợp lệ.';
  if (normalized.reduce((sum, cell) => sum + cell.count, 0) > targetCount) return 'Tổng ma trận vượt quá số câu đã khai báo.';
  return '';
}
