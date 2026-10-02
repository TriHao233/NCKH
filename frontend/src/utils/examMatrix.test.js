import assert from 'node:assert/strict';
import { test } from 'node:test';
import { EXAM_BLOOM_LEVELS, examBloomLevel, examMatrixError, normalizeExamMatrix } from './examMatrix.js';

test('legacy exam groups retain their original Bloom levels and expose all six levels', () => {
  assert.equal(examBloomLevel('nhan_biet').level, 1);
  assert.equal(examBloomLevel('thong_hieu').level, 2);
  assert.equal(examBloomLevel('van_dung_cao').label, '4. Phân tích');
  assert.equal(examBloomLevel('danh_gia').label, '5. Đánh giá');
  assert.equal(examBloomLevel('sang_tao').level, 6);
  assert.equal(EXAM_BLOOM_LEVELS.length, 6);
});

test('saving an existing matrix retains difficulty and normalizes legacy values', () => {
  assert.deepEqual(normalizeExamMatrix([{ cognitive_level: 'van_dung_cao', count: '2', difficulty: 'kho' }]), [
    { chapter_id: null, cognitive_level: 'phan_tich', difficulty: 'kho', count: 2 },
  ]);
});

test('matrix validation rejects fractional, empty and excessive counts before saving', () => {
  for (const count of [0, '', 1.5, 'bad']) {
    assert.match(examMatrixError([{ cognitive_level: 'nho', count }], 10), /Dòng 1/);
  }
  assert.match(examMatrixError([{ cognitive_level: 'nho', count: 11 }], 10), /vượt/);
  assert.equal(examMatrixError([{ cognitive_level: 'sang_tao', count: 2 }], 10), '');
});
