import test from 'node:test';
import assert from 'node:assert/strict';

import { diffLines } from './textDiff.js';

test('diffLines marks added and removed lines', () => {
  const result = diffLines('a\nb\nc', 'a\nx\nc');
  assert.deepEqual(result, [
    { type: 'same', text: 'a' },
    { type: 'remove', text: 'b' },
    { type: 'add', text: 'x' },
    { type: 'same', text: 'c' },
  ]);
});

test('diffLines handles empty inputs and appended lines', () => {
  assert.deepEqual(diffLines('', 'a'), [{ type: 'remove', text: '' }, { type: 'add', text: 'a' }]);
  assert.deepEqual(diffLines('a', 'a\nb'), [{ type: 'same', text: 'a' }, { type: 'add', text: 'b' }]);
});
