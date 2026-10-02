// So sánh hai đoạn văn bản theo dòng (LCS), đủ dùng cho prompt dài vài trăm dòng.
export function diffLines(before = '', after = '') {
  const a = before.split('\n');
  const b = after.split('\n');
  const lengths = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      lengths[i][j] = a[i] === b[j] ? lengths[i + 1][j + 1] + 1 : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
    }
  }
  const rows = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      rows.push({ type: 'same', text: a[i] });
      i += 1;
      j += 1;
    } else if (lengths[i + 1][j] >= lengths[i][j + 1]) {
      rows.push({ type: 'removed', text: a[i] });
      i += 1;
    } else {
      rows.push({ type: 'added', text: b[j] });
      j += 1;
    }
  }
  while (i < a.length) { rows.push({ type: 'removed', text: a[i] }); i += 1; }
  while (j < b.length) { rows.push({ type: 'added', text: b[j] }); j += 1; }
  return rows;
}

export function diffSummary(rows) {
  return {
    added: rows.filter((row) => row.type === 'added').length,
    removed: rows.filter((row) => row.type === 'removed').length,
  };
}
