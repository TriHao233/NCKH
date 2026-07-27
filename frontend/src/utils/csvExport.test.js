import test from 'node:test';
import assert from 'node:assert/strict';
import {
  csvCell,
  rowsToCsv,
  rowsToXlsxBlob,
  timestampedCsvFilename,
  timestampedXlsxFilename,
} from './csvExport.js';

test('csvCell escapes quotes and keeps empty values blank', () => {
  assert.equal(csvCell('A "quoted" value'), '"A ""quoted"" value"');
  assert.equal(csvCell(null), '');
});

test('rowsToCsv writes header and rows with CRLF', () => {
  const csv = rowsToCsv(
    [
      { header: 'ID', value: (row) => row.id },
      { header: 'Payload', value: (row) => row.payload },
    ],
    [
      { id: '1', payload: { status: 'OK' } },
      { id: '2', payload: 'plain' },
    ],
  );

  assert.equal(csv, '"ID","Payload"\r\n"1","{""status"":""OK""}"\r\n"2","plain"');
});

test('timestampedCsvFilename is stable for a provided clock', () => {
  const filename = timestampedCsvFilename('admin-jobs', new Date('2026-07-27T01:02:03.004Z'));

  assert.equal(filename, 'admin-jobs-2026-07-27T01-02-03-004Z.csv');
});

test('timestampedXlsxFilename is stable for a provided clock', () => {
  const filename = timestampedXlsxFilename('admin-audit', new Date('2026-07-27T01:02:03.004Z'));

  assert.equal(filename, 'admin-audit-2026-07-27T01-02-03-004Z.xlsx');
});

test('rowsToXlsxBlob creates a workbook zip with escaped worksheet values', async () => {
  const blob = rowsToXlsxBlob(
    [
      { header: 'Name', value: (row) => row.name },
      { header: 'Payload', value: (row) => row.payload },
    ],
    [
      { name: 'A & B', payload: { quote: '"ok"' } },
    ],
    'Audit:Report',
  );

  assert.equal(blob.type, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');

  const bytes = new Uint8Array(await blob.arrayBuffer());
  assert.deepEqual(Array.from(bytes.slice(0, 4)), [0x50, 0x4b, 0x03, 0x04]);

  const workbookText = new TextDecoder().decode(bytes);
  assert.match(workbookText, /xl\/worksheets\/sheet1\.xml/);
  assert.match(workbookText, /A &amp; B/);
  assert.match(workbookText, /Audit Report/);
});
