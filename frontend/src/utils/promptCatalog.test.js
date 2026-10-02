import test from 'node:test';
import assert from 'node:assert/strict';
import { groupPrompts, promptTitle } from './promptCatalog.js';

const prompt = (template_key, kind, version = 1, is_active = true, name = template_key) => (
  { template_key, kind, version, is_active, name, prompt_body: `${template_key} v${version}` }
);

test('prompt titles are readable instead of raw keys', () => {
  assert.equal(promptTitle(prompt('bloom:1_nho', 'BLOOM')), '1. Nhớ');
  assert.equal(promptTitle(prompt('bloom:nho', 'BLOOM')), 'Nhớ (mã cũ)');
  assert.equal(promptTitle(prompt('question_type:dung_sai', 'QUESTION_TYPE')), 'Đúng / Sai');
  assert.equal(promptTitle(prompt('evaluation:question_type:general', 'EVALUATION')), 'Mọi loại câu hỏi');
  assert.equal(promptTitle(prompt('evaluation:question_type:sap_xep', 'EVALUATION')), 'Riêng loại Sắp xếp');
  assert.equal(promptTitle(prompt('system', 'SYSTEM')), 'Vai trò hệ thống');
  assert.equal(promptTitle(prompt('custom:key', 'OTHER', 1, true, 'Tên riêng')), 'Tên riêng');
});

test('prompts group by kind in build order with versions newest first', () => {
  const groups = groupPrompts([
    prompt('evaluation:scoring_policy', 'EVALUATION'),
    prompt('system', 'SYSTEM', 1, false),
    prompt('system', 'SYSTEM', 2, true),
    prompt('bloom:2_hieu', 'BLOOM'),
    prompt('custom', 'ZZZ', 1, false),
  ]);
  assert.deepEqual(groups.map((group) => group.kind), ['SYSTEM', 'BLOOM', 'EVALUATION', 'ZZZ']);
  const system = groups[0].items[0];
  assert.deepEqual(system.versions.map((version) => version.version), [2, 1]);
  assert.equal(system.active.version, 2);
  assert.equal(groups[3].items[0].active, null);
});

test('prompt search matches the readable title and the key', () => {
  const templates = [prompt('bloom:2_hieu', 'BLOOM'), prompt('question_type:dung_sai', 'QUESTION_TYPE')];
  assert.deepEqual(groupPrompts(templates, 'đúng').map((group) => group.kind), ['QUESTION_TYPE']);
  assert.deepEqual(groupPrompts(templates, 'bloom:').map((group) => group.kind), ['BLOOM']);
  assert.deepEqual(groupPrompts(templates, 'không có'), []);
});
