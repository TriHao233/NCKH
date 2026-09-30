import test from 'node:test';
import assert from 'node:assert/strict';
import { parseJobFilters } from './adminJobFilters.js';
test('overview links parse exact supported job filters', () => {
  assert.deepEqual(parseJobFilters('?kind=document&status=retryable&stale_only=true&search=OCR%20fail'), { kind: 'document', status: 'retryable', staleOnly: true, search: 'OCR fail' });
  assert.equal(parseJobFilters('?status=FAILED').status, 'FAILED');
});
test('invalid URL filters are ignored', () => {
  assert.deepEqual(parseJobFilters('?kind=bad&status=bad&stale_only=1'), { kind: 'all', status: 'all', staleOnly: false, search: '' });
  assert.deepEqual(parseJobFilters(''), { kind: 'all', status: 'all', staleOnly: false, search: '' });
});
