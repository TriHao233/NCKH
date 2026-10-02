import test from 'node:test';
import assert from 'node:assert/strict';
import { suggestVariantCodes } from './examVariantCodes.js';

test('growing a batch skips existing and retained draft codes', () => {
  const defaults = ['132', '209', '357', '485'];
  assert.deepEqual(suggestVariantCodes(['209'], ['132'], defaults, 3), ['209', '357', '485']);
  assert.deepEqual(suggestVariantCodes(['QA1', 'QA1'], ['132'], defaults, 3), ['QA1', '209', '357']);
  assert.deepEqual(suggestVariantCodes([' 209 '], ['209'], defaults, 1), ['132']);
});
