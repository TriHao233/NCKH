/**
 * So sánh hai văn bản theo dòng (LCS). Trả về danh sách { type: 'same' | 'add' | 'remove', text }.
 * Đủ nhanh cho prompt vài trăm dòng.
 */
export function diffLines(before = '', after = '') {
  const a = String(before).split('\n');
  const b = String(after).split('\n');
  const rows = a.length;
  const cols = b.length;
  const table = Array.from({ length: rows + 1 }, () => new Uint32Array(cols + 1));
  for (let i = rows - 1; i >= 0; i -= 1) {
    for (let j = cols - 1; j >= 0; j -= 1) {
      table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const result = [];
  let i = 0;
  let j = 0;
  while (i < rows && j < cols) {
    if (a[i] === b[j]) {
      result.push({ type: 'same', text: a[i] });
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      result.push({ type: 'remove', text: a[i] });
      i += 1;
    } else {
      result.push({ type: 'add', text: b[j] });
      j += 1;
    }
  }
  while (i < rows) result.push({ type: 'remove', text: a[i++] });
  while (j < cols) result.push({ type: 'add', text: b[j++] });
  return result;
}
