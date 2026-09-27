import { difficultyLabel, questionTypeLabel } from '../../constants/generationEnums.js';

// LCS is O(n*m); above this many token pairs the change is shown as whole blocks.
const WORD_DIFF_MAX_CELLS = 250000;

function tokenize(text) {
  return String(text ?? '').match(/\s+|[^\s]+/g) || [];
}

function pushSegment(segments, text, type) {
  const last = segments[segments.length - 1];
  if (last && last.type === type) last.text += text;
  else segments.push({ text, type });
}

/**
 * So khớp theo từ giữa hai đoạn văn. Trả về hai dãy đoạn: `before` đánh dấu phần bị xoá,
 * `after` đánh dấu phần thêm mới. Trả về null khi văn bản quá dài để so từng từ.
 */
export function wordDiff(beforeText, afterText) {
  const a = tokenize(beforeText);
  const b = tokenize(afterText);
  if (a.length * b.length > WORD_DIFF_MAX_CELLS) return null;
  const table = Array.from({ length: a.length + 1 }, () => new Uint32Array(b.length + 1));
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const before = [];
  const after = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      pushSegment(before, a[i], 'same');
      pushSegment(after, b[j], 'same');
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      pushSegment(before, a[i], 'removed');
      i += 1;
    } else {
      pushSegment(after, b[j], 'added');
      j += 1;
    }
  }
  for (; i < a.length; i += 1) pushSegment(before, a[i], 'removed');
  for (; j < b.length; j += 1) pushSegment(after, b[j], 'added');
  return { before, after };
}

function idOf(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  return String(value.id || value._id || value.$oid || '');
}

function textChange(key, label, before, after) {
  const oldValue = String(before ?? '');
  const newValue = String(after ?? '');
  if (oldValue === newValue) return null;
  return { key, label, kind: 'text', before: oldValue, after: newValue, words: wordDiff(oldValue, newValue) };
}

function valueChange(key, label, before, after) {
  const oldValue = before || '';
  const newValue = after || '';
  if (oldValue === newValue) return null;
  return { key, label, kind: 'value', before: oldValue, after: newValue };
}

function typeText(classification) {
  const value = String(classification?.assessment_type || '');
  return value ? questionTypeLabel(value.toLowerCase()) : '';
}

function bloomText(classification) {
  const bloom = classification?.bloom || {};
  if (!bloom.level) return '';
  return `Bloom ${bloom.level}${bloom.name ? ` - ${bloom.name}` : ''}`;
}

function subjectText(classification) {
  const subject = classification?.subject || {};
  return [subject.code, subject.name].filter(Boolean).join(' - ') || idOf(subject);
}

function cloCodes(version) {
  return (version?.clos || [])
    .map((clo) => clo?.code || clo?.clo_code || idOf(clo))
    .filter(Boolean)
    .sort();
}

function sourceKey(source) {
  return idOf(source?.chunk_id) || idOf(source?.document_id) || String(source?.context_excerpt || '').slice(0, 80);
}

function sourcePreview(source) {
  const excerpt = String(source?.context_excerpt || '').replace(/\s+/g, ' ').trim();
  const page = source?.page_number || source?.page_start;
  const prefix = page ? `Trang ${page}: ` : '';
  return `${prefix}${excerpt.length > 140 ? `${excerpt.slice(0, 140)}…` : excerpt || '(không có trích đoạn)'}`;
}

/**
 * Liệt kê các thay đổi giữa hai phiên bản câu hỏi: nội dung, phương án, đáp án, giải thích,
 * phân loại (dạng câu, Bloom, độ khó, học phần, chương), CLO và nguồn trích dẫn.
 */
export function diffVersions(previous, current, { chapterLabel } = {}) {
  if (!previous || !current) return [];
  const changes = [];
  const add = (change) => { if (change) changes.push(change); };

  add(textChange('content', 'Nội dung câu hỏi', previous.content, current.content));
  const before = previous.question_data || {};
  const after = current.question_data || {};
  const optionKeys = new Set([...Object.keys(before.options || {}), ...Object.keys(after.options || {})]);
  [...optionKeys].sort().forEach((key) => {
    add(textChange(`opt-${key}`, `Phương án ${key}`, before.options?.[key], after.options?.[key]));
  });
  add(valueChange('answer', 'Đáp án đúng', String(before.correct_answer ?? ''), String(after.correct_answer ?? '')));
  add(textChange('explanation', 'Giải thích', before.explanation, after.explanation));

  const oldClass = previous.classification || {};
  const newClass = current.classification || {};
  add(valueChange('type', 'Dạng câu hỏi', typeText(oldClass), typeText(newClass)));
  add(valueChange('bloom', 'Mức Bloom', bloomText(oldClass), bloomText(newClass)));
  add(valueChange('difficulty', 'Độ khó', difficultyLabel(oldClass.difficulty) || oldClass.difficulty, difficultyLabel(newClass.difficulty) || newClass.difficulty));
  add(valueChange('subject', 'Học phần', subjectText(oldClass), subjectText(newClass)));
  const oldChapter = idOf(oldClass.chapter);
  const newChapter = idOf(newClass.chapter);
  if (oldChapter !== newChapter) {
    const label = (id) => (id ? (chapterLabel?.(id) || 'Chương khác') : '');
    changes.push({ key: 'chapter', label: 'Chương', kind: 'value', before: label(oldChapter), after: label(newChapter) });
  }

  const oldClos = cloCodes(previous);
  const newClos = cloCodes(current);
  add(valueChange('clos', 'Chuẩn đầu ra (CLO)', oldClos.join(', '), newClos.join(', ')));

  const oldSources = new Map((previous.sources || []).map((source) => [sourceKey(source), source]));
  const newSources = new Map((current.sources || []).map((source) => [sourceKey(source), source]));
  const removed = [...oldSources.keys()].filter((key) => !newSources.has(key)).map((key) => oldSources.get(key));
  const added = [...newSources.keys()].filter((key) => !oldSources.has(key)).map((key) => newSources.get(key));
  if (removed.length || added.length) {
    changes.push({
      key: 'sources',
      label: 'Nguồn trích dẫn',
      kind: 'sources',
      removed: removed.map(sourcePreview),
      added: added.map(sourcePreview),
    });
  }
  return changes;
}

/** Phiên bản làm mốc so sánh: phiên bản gần nhất đã có phiếu kiểm duyệt, cũ hơn phiên bản hiện tại. */
export function baselineReview(question, reviews) {
  const current = Number(question?.current_version);
  if (!Number.isFinite(current)) return null;
  return (reviews || [])
    .filter((review) => Number(review.question_version) < current)
    .sort((a, b) => Number(b.question_version) - Number(a.question_version)
      || String(b.reviewed_at || '').localeCompare(String(a.reviewed_at || '')))[0] || null;
}
