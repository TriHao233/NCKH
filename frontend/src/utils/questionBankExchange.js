const OPTION_KEYS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
const DIFFICULTIES = new Set(['de', 'trung_binh', 'kho']);

const TYPE_ALIASES = {
  mcq: 'trac_nghiem',
  multiplechoice: 'trac_nghiem',
  multiple_choice: 'trac_nghiem',
  multichoice: 'trac_nghiem',
  trac_nghiem: 'trac_nghiem',
  multi: 'nhieu_lua_chon',
  multiple_response: 'nhieu_lua_chon',
  multipleanswer: 'nhieu_lua_chon',
  nhieu_lua_chon: 'nhieu_lua_chon',
  tf: 'dung_sai',
  truefalse: 'dung_sai',
  true_false: 'dung_sai',
  dung_sai: 'dung_sai',
  fill: 'dien_khuyet',
  blank: 'dien_khuyet',
  shortanswer: 'dien_khuyet',
  short_answer: 'dien_khuyet',
  dien_khuyet: 'dien_khuyet',
  match: 'ghep_cot',
  matching: 'ghep_cot',
  ghep_cot: 'ghep_cot',
  order: 'sap_xep',
  ordering: 'sap_xep',
  sap_xep: 'sap_xep',
  scenario: 'tinh_huong',
  case: 'tinh_huong',
  tinh_huong: 'tinh_huong',
};

const CSV_FIELD_ALIASES = {
  content: ['content', 'question', 'question_text', 'text', 'noi_dung'],
  questionType: ['question_type', 'type', 'assessment_type', 'loai_cau_hoi'],
  bloomLevel: ['bloom_level', 'bloom', 'bloom_level_number', 'muc_bloom'],
  difficulty: ['difficulty', 'do_kho'],
  subject: ['subject_id', 'subject', 'subject_code', 'ma_mon', 'hoc_phan'],
  chapter: ['chapter_id', 'chapter', 'chapter_code', 'ma_chuong'],
  clo: ['clo_ids', 'clos', 'clo', 'clo_codes'],
  optionsJson: ['options_json', 'options', 'choices_json', 'lua_chon'],
  questionData: ['question_data', 'question_data_json'],
  correctAnswer: ['correct_answer', 'answer', 'dap_an', 'dap_an_dung'],
  explanation: ['explanation', 'feedback', 'giai_thich'],
  sourceChunks: ['source_chunk_ids', 'chunk_ids', 'sources'],
};

function textValue(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  return String(value);
}

function normalizedKey(value) {
  return textValue(value)
    .trim()
    .toLowerCase()
    .replace(/^\uFEFF/, '')
    .replace(/[\s.-]+/g, '_')
    .replace(/[^\w]/g, '');
}

function compactKey(value) {
  return normalizedKey(value).replace(/_/g, '');
}

function refId(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  return value.id || value._id || '';
}

function getNestedId(value) {
  return refId(value?.id || value);
}

function classification(question) {
  return question?.classification || {};
}

export function normalizeQuestionBankType(value) {
  const key = normalizedKey(value);
  if (!key) return 'trac_nghiem';
  return TYPE_ALIASES[key] || TYPE_ALIASES[compactKey(key)] || key;
}

export function questionTypeForExport(question) {
  return normalizeQuestionBankType(classification(question).assessment_type || question?.question_type);
}

function questionSubjectId(question) {
  return getNestedId(classification(question).subject);
}

function questionChapterId(question) {
  return getNestedId(classification(question).chapter);
}

function questionBloomLevel(question) {
  const level = classification(question).bloom?.level;
  return level === null || level === undefined ? '' : String(level);
}

function questionDifficulty(question) {
  return classification(question).difficulty || '';
}

function questionCloIds(question) {
  return (question?.clos || [])
    .map((clo) => refId(clo.id || clo))
    .filter(Boolean);
}

function questionSourceChunkIds(question) {
  return (question?.sources || [])
    .map((source) => refId(source.chunk_id || source.chunk))
    .filter(Boolean);
}

function questionOptions(question) {
  const options = question?.question_data?.options;
  if (!options) return {};
  if (Array.isArray(options)) {
    return Object.fromEntries(options.map((value, index) => [OPTION_KEYS[index] || String(index + 1), textValue(value)]));
  }
  if (typeof options === 'object') return options;
  return {};
}

function sortedOptionEntries(options = {}) {
  return Object.entries(options)
    .map(([key, value]) => [textValue(key).trim(), textValue(value).trim()])
    .filter(([key, value]) => key && value)
    .sort(([left], [right]) => left.localeCompare(right, 'en', { numeric: true }));
}

function answerValues(value) {
  return textValue(value)
    .split(/[;,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export const QUESTION_BANK_EXPORT_COLUMNS = [
  { header: 'question_code', value: (question) => question.question_code || '' },
  { header: 'content', value: (question) => question.content || '' },
  { header: 'question_type', value: questionTypeForExport },
  { header: 'bloom_level', value: questionBloomLevel },
  { header: 'difficulty', value: questionDifficulty },
  { header: 'subject_id', value: questionSubjectId },
  { header: 'chapter_id', value: questionChapterId },
  { header: 'clo_ids', value: (question) => questionCloIds(question).join('; ') },
  { header: 'options_json', value: (question) => questionOptions(question) },
  { header: 'correct_answer', value: (question) => question.question_data?.correct_answer || '' },
  { header: 'explanation', value: (question) => question.question_data?.explanation || '' },
  { header: 'source_chunk_ids', value: (question) => questionSourceChunkIds(question).join('; ') },
  { header: 'review_status', value: (question) => question.review_status || '' },
  { header: 'publication_status', value: (question) => question.publication_status || '' },
];

function escapeGift(value) {
  return textValue(value)
    .replace(/\\/g, '\\\\')
    .replace(/\r?\n/g, '<br>')
    .replace(/([{}~=#:])/g, '\\$1');
}

function unescapeGift(value) {
  return textValue(value)
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/\\([\\{}~=#:])/g, '$1');
}

function giftOptionLine(entry, correctKeys, multipleCorrect) {
  const [key, value] = entry;
  const isCorrect = correctKeys.has(key);
  if (!multipleCorrect) {
    return `${isCorrect ? '=' : '~'}${escapeGift(value)}`;
  }
  if (isCorrect) {
    const percent = Math.max(1, Math.floor(100 / Math.max(correctKeys.size, 1)));
    return `~%${percent}%${escapeGift(value)}`;
  }
  return `~%-100%${escapeGift(value)}`;
}

export function questionsToGift(questions = []) {
  return questions.map((question, index) => {
    const code = question.question_code || `QUESTION_${index + 1}`;
    const type = questionTypeForExport(question);
    const content = escapeGift(question.content || '');
    const explanation = question.question_data?.explanation
      ? `#${escapeGift(question.question_data.explanation)}`
      : '';
    const correct = answerValues(question.question_data?.correct_answer);

    if (type === 'dung_sai') {
      const correctText = correct[0]?.toUpperCase();
      const giftAnswer = ['A', 'TRUE', 'T', 'DUNG', 'ĐÚNG'].includes(correctText) ? 'TRUE' : 'FALSE';
      return `::${escapeGift(code)}::${content}{${giftAnswer}${explanation}}`;
    }

    const entries = sortedOptionEntries(questionOptions(question));
    if (entries.length > 0) {
      const correctKeys = new Set(correct);
      const multipleCorrect = correctKeys.size > 1 || type === 'nhieu_lua_chon';
      const answers = entries.map((entry) => giftOptionLine(entry, correctKeys, multipleCorrect)).join(' ');
      return `::${escapeGift(code)}::${content}{${answers}${explanation}}`;
    }

    const shortAnswer = correct.length > 0 ? correct.join(' | ') : '';
    return `::${escapeGift(code)}::${content}{=${escapeGift(shortAnswer)}${explanation}}`;
  }).join('\n\n');
}

function xmlEscape(value) {
  return textValue(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function xmlUnescape(value) {
  return textValue(value)
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/<[^>]+>/g, '')
    .replace(/&apos;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&gt;/g, '>')
    .replace(/&lt;/g, '<')
    .replace(/&amp;/g, '&')
    .trim();
}

function xmlTextTag(tag, value) {
  return `<${tag}><text>${xmlEscape(value)}</text></${tag}>`;
}

function moodleAnswerXml(answerText, fraction, feedback = '') {
  return [
    `<answer fraction="${fraction}">`,
    `<text>${xmlEscape(answerText)}</text>`,
    xmlTextTag('feedback', feedback),
    '</answer>',
  ].join('');
}

function questionToMoodleXml(question, index) {
  const type = questionTypeForExport(question);
  const name = question.question_code || `QUESTION_${index + 1}`;
  const content = question.content || '';
  const explanation = question.question_data?.explanation || '';
  const correct = answerValues(question.question_data?.correct_answer);

  if (type === 'dung_sai') {
    const correctText = correct[0]?.toUpperCase();
    const trueCorrect = ['A', 'TRUE', 'T', 'DUNG', 'ĐÚNG'].includes(correctText);
    return [
      '<question type="truefalse">',
      xmlTextTag('name', name),
      `<questiontext format="html"><text>${xmlEscape(content)}</text></questiontext>`,
      moodleAnswerXml('true', trueCorrect ? 100 : 0, explanation),
      moodleAnswerXml('false', trueCorrect ? 0 : 100, explanation),
      '</question>',
    ].join('');
  }

  if (type === 'dien_khuyet') {
    return [
      '<question type="shortanswer">',
      xmlTextTag('name', name),
      `<questiontext format="html"><text>${xmlEscape(content)}</text></questiontext>`,
      correct.map((answer) => moodleAnswerXml(answer, 100, explanation)).join(''),
      '</question>',
    ].join('');
  }

  const entries = sortedOptionEntries(questionOptions(question));
  const correctKeys = new Set(correct);
  const multipleCorrect = correctKeys.size > 1 || type === 'nhieu_lua_chon';
  const correctFraction = multipleCorrect ? Math.max(1, Math.floor(100 / Math.max(correctKeys.size, 1))) : 100;
  return [
    '<question type="multichoice">',
    xmlTextTag('name', name),
    `<questiontext format="html"><text>${xmlEscape(content)}</text></questiontext>`,
    `<single>${multipleCorrect ? 'false' : 'true'}</single>`,
    entries.map(([key, value]) => (
      moodleAnswerXml(value, correctKeys.has(key) ? correctFraction : 0, explanation)
    )).join(''),
    '</question>',
  ].join('');
}

export function questionsToMoodleXml(questions = []) {
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<quiz>',
    ...questions.map(questionToMoodleXml),
    '</quiz>',
  ].join('\n');
}

export function timestampedQuestionBankFilename(prefix, extension, now = new Date()) {
  const stamp = now.toISOString().replace(/[:.]/g, '-');
  return `${prefix}-${stamp}.${extension}`;
}

export function downloadTextFile(filename, content, mimeType = 'text/plain;charset=utf-8') {
  const url = window.URL.createObjectURL(new Blob([content], { type: mimeType }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

function splitList(value) {
  return textValue(value)
    .split(/[;,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function readCsvCell(row, field) {
  for (const key of CSV_FIELD_ALIASES[field] || []) {
    const value = row[key];
    if (value !== undefined && value !== '') return value;
  }
  return '';
}

export function parseCsvRows(text) {
  const rows = [];
  let row = [];
  let cell = '';
  let inQuotes = false;
  const input = textValue(text).replace(/^\uFEFF/, '');

  for (let index = 0; index < input.length; index += 1) {
    const char = input[index];
    const nextChar = input[index + 1];

    if (inQuotes) {
      if (char === '"' && nextChar === '"') {
        cell += '"';
        index += 1;
      } else if (char === '"') {
        inQuotes = false;
      } else {
        cell += char;
      }
      continue;
    }

    if (char === '"' && cell === '') {
      inQuotes = true;
    } else if (char === ',') {
      row.push(cell);
      cell = '';
    } else if (char === '\n') {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
    } else if (char !== '\r') {
      cell += char;
    }
  }

  if (cell || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }

  return rows.filter((item) => item.some((value) => textValue(value).trim()));
}

function parseJsonObject(value, fieldName, rowNumber) {
  const text = textValue(value).trim();
  if (!text) return null;
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed;
  } catch (error) {
    throw new Error(`Row ${rowNumber}: ${fieldName} is not valid JSON`);
  }
  throw new Error(`Row ${rowNumber}: ${fieldName} must be a JSON object`);
}

function parseOptionsText(value, rowNumber) {
  const text = textValue(value).trim();
  if (!text) return {};
  if (text.startsWith('{')) return parseJsonObject(text, 'options_json', rowNumber) || {};
  const options = {};
  text.split(/[;\n]/).forEach((part) => {
    const match = part.trim().match(/^([A-Za-z0-9]+)\s*[:=]\s*(.+)$/);
    if (match) options[match[1].trim()] = match[2].trim();
  });
  return options;
}

function parseTableRecords(rows, sourceLabel = 'CSV') {
  if (rows.length < 2) return { records: [], errors: [`${sourceLabel} must include a header row and at least one item row`] };
  const headers = rows[0].map(normalizedKey);
  const records = [];
  const errors = [];

  rows.slice(1).forEach((values, index) => {
    const rowNumber = index + 2;
    const row = {};
    headers.forEach((header, headerIndex) => {
      row[header] = values[headerIndex] || '';
    });

    try {
      const questionData = parseJsonObject(readCsvCell(row, 'questionData'), 'question_data', rowNumber) || {};
      const optionsFromColumns = {};
      OPTION_KEYS.forEach((key) => {
        const value = row[`option_${key.toLowerCase()}`] || row[key.toLowerCase()];
        if (value) optionsFromColumns[key] = value;
      });
      const options = Object.keys(optionsFromColumns).length > 0
        ? optionsFromColumns
        : parseOptionsText(readCsvCell(row, 'optionsJson'), rowNumber);

      records.push({
        rowNumber,
        content: readCsvCell(row, 'content'),
        questionType: readCsvCell(row, 'questionType'),
        bloomLevel: readCsvCell(row, 'bloomLevel'),
        difficulty: readCsvCell(row, 'difficulty'),
        subjectRef: readCsvCell(row, 'subject'),
        chapterRef: readCsvCell(row, 'chapter'),
        cloRefs: splitList(readCsvCell(row, 'clo')),
        options: Object.keys(options).length > 0 ? options : questionData.options,
        correctAnswer: readCsvCell(row, 'correctAnswer') || questionData.correct_answer,
        explanation: readCsvCell(row, 'explanation') || questionData.explanation,
        sourceChunkIds: splitList(readCsvCell(row, 'sourceChunks')),
      });
    } catch (error) {
      errors.push(error.message);
    }
  });

  return { records, errors };
}

function parseCsvRecords(text) {
  return parseTableRecords(parseCsvRows(text), 'CSV');
}

function readUint32(view, offset) {
  return view.getUint32(offset, true);
}

function readUint16(view, offset) {
  return view.getUint16(offset, true);
}

function findEndOfCentralDirectory(view) {
  for (let offset = view.byteLength - 22; offset >= 0; offset -= 1) {
    if (readUint32(view, offset) === 0x06054b50) return offset;
  }
  return -1;
}

async function inflateRaw(bytes) {
  if (typeof DecompressionStream === 'undefined') {
    throw new Error('XLSX file uses compressed ZIP entries; this browser cannot decompress it');
  }
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

async function unzipXlsxEntries(arrayBuffer) {
  const view = new DataView(arrayBuffer);
  const bytes = new Uint8Array(arrayBuffer);
  const endOffset = findEndOfCentralDirectory(view);
  if (endOffset < 0) throw new Error('XLSX ZIP directory not found');
  const entryCount = readUint16(view, endOffset + 10);
  let centralOffset = readUint32(view, endOffset + 16);
  const decoder = new TextDecoder();
  const entries = new Map();

  for (let entryIndex = 0; entryIndex < entryCount; entryIndex += 1) {
    if (readUint32(view, centralOffset) !== 0x02014b50) {
      throw new Error('XLSX central directory is invalid');
    }
    const method = readUint16(view, centralOffset + 10);
    const compressedSize = readUint32(view, centralOffset + 20);
    const nameLength = readUint16(view, centralOffset + 28);
    const extraLength = readUint16(view, centralOffset + 30);
    const commentLength = readUint16(view, centralOffset + 32);
    const localOffset = readUint32(view, centralOffset + 42);
    const name = decoder.decode(bytes.slice(centralOffset + 46, centralOffset + 46 + nameLength));
    const localNameLength = readUint16(view, localOffset + 26);
    const localExtraLength = readUint16(view, localOffset + 28);
    const dataStart = localOffset + 30 + localNameLength + localExtraLength;
    const compressedData = bytes.slice(dataStart, dataStart + compressedSize);
    let data;
    if (method === 0) {
      data = compressedData;
    } else if (method === 8) {
      data = await inflateRaw(compressedData);
    } else {
      throw new Error(`Unsupported XLSX ZIP compression method: ${method}`);
    }
    entries.set(name, decoder.decode(data));
    centralOffset += 46 + nameLength + extraLength + commentLength;
  }

  return entries;
}

function parseSharedStrings(sharedStringsXml = '') {
  return Array.from(sharedStringsXml.matchAll(/<si\b[^>]*>([\s\S]*?)<\/si>/gi)).map((match) => (
    Array.from(match[1].matchAll(/<t\b[^>]*>([\s\S]*?)<\/t>/gi))
      .map((textMatch) => xmlUnescape(textMatch[1]))
      .join('')
  ));
}

function columnIndexFromCellRef(ref) {
  const letters = textValue(ref).match(/^[A-Z]+/i)?.[0]?.toUpperCase() || '';
  let index = 0;
  for (const letter of letters) {
    index = index * 26 + (letter.charCodeAt(0) - 64);
  }
  return Math.max(index - 1, 0);
}

function xlsxCellText(attrs, body, sharedStrings) {
  const type = attrs.match(/\bt=["']([^"']+)["']/i)?.[1] || '';
  if (type === 'inlineStr') {
    return Array.from(body.matchAll(/<t\b[^>]*>([\s\S]*?)<\/t>/gi))
      .map((match) => xmlUnescape(match[1]))
      .join('');
  }
  const value = xmlUnescape(body.match(/<v\b[^>]*>([\s\S]*?)<\/v>/i)?.[1] || '');
  if (type === 's') return sharedStrings[Number(value)] || '';
  if (type === 'b') return value === '1' ? 'TRUE' : 'FALSE';
  return value;
}

function parseWorksheetRows(sheetXml = '', sharedStrings = []) {
  return Array.from(sheetXml.matchAll(/<row\b[^>]*>([\s\S]*?)<\/row>/gi))
    .map((rowMatch) => {
      const row = [];
      Array.from(rowMatch[1].matchAll(/<c\b([^>]*)>([\s\S]*?)<\/c>/gi)).forEach((cellMatch) => {
        const attrs = cellMatch[1] || '';
        const ref = attrs.match(/\br=["']([^"']+)["']/i)?.[1] || '';
        const columnIndex = columnIndexFromCellRef(ref);
        row[columnIndex] = xlsxCellText(attrs, cellMatch[2] || '', sharedStrings);
      });
      return row.map((value) => value || '');
    })
    .filter((row) => row.some((value) => textValue(value).trim()));
}

async function parseXlsxRecords(arrayBuffer) {
  const entries = await unzipXlsxEntries(arrayBuffer);
  const sheetName = entries.has('xl/worksheets/sheet1.xml')
    ? 'xl/worksheets/sheet1.xml'
    : Array.from(entries.keys()).find((name) => /^xl\/worksheets\/sheet\d+\.xml$/i.test(name));
  if (!sheetName) return { records: [], errors: ['XLSX must include at least one worksheet'] };
  const sharedStrings = parseSharedStrings(entries.get('xl/sharedStrings.xml') || '');
  return parseTableRecords(parseWorksheetRows(entries.get(sheetName), sharedStrings), 'XLSX');
}

function findUnescaped(text, target) {
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] === '\\') {
      index += 1;
    } else if (text[index] === target) {
      return index;
    }
  }
  return -1;
}

function stripGiftFeedback(segment) {
  const feedbackIndex = findUnescaped(segment, '#');
  return feedbackIndex >= 0 ? segment.slice(0, feedbackIndex) : segment;
}

function splitGiftSegments(answerText) {
  const segments = [];
  let marker = '';
  let start = -1;
  for (let index = 0; index < answerText.length; index += 1) {
    const char = answerText[index];
    if (char === '\\') {
      index += 1;
      continue;
    }
    if (char === '=' || char === '~') {
      if (start >= 0) {
        segments.push({ marker, text: answerText.slice(start, index).trim() });
      }
      marker = char;
      start = index + 1;
    }
  }
  if (start >= 0) {
    segments.push({ marker, text: answerText.slice(start).trim() });
  }
  return segments;
}

function parseGiftPercent(segment) {
  const match = segment.text.match(/^%(-?\d+(?:\.\d+)?)%([\s\S]*)$/);
  if (!match) return { percent: segment.marker === '=' ? 100 : 0, text: segment.text };
  return { percent: Number(match[1]), text: match[2] };
}

function parseGiftRecords(text) {
  const blocks = textValue(text)
    .replace(/\r\n/g, '\n')
    .split(/\n\s*\n/)
    .map((block) => block.split('\n').filter((line) => !line.trim().startsWith('//')).join('\n').trim())
    .filter(Boolean);
  const records = [];
  const errors = [];

  blocks.forEach((block, index) => {
    const rowNumber = index + 1;
    const openIndex = findUnescaped(block, '{');
    const closeIndex = block.lastIndexOf('}');
    if (openIndex < 0 || closeIndex <= openIndex) {
      errors.push(`GIFT item ${rowNumber}: missing answer braces`);
      return;
    }
    let content = block.slice(0, openIndex).trim();
    const titleMatch = content.match(/^::([^:]+)::([\s\S]*)$/);
    if (titleMatch) content = titleMatch[2].trim();
    const answerText = block.slice(openIndex + 1, closeIndex).trim();

    if (/^(TRUE|FALSE|T|F)$/i.test(answerText)) {
      const isTrue = /^T(RUE)?$/i.test(answerText);
      records.push({
        rowNumber,
        content: unescapeGift(content),
        questionType: 'dung_sai',
        options: { A: 'True', B: 'False' },
        correctAnswer: isTrue ? 'A' : 'B',
      });
      return;
    }

    const segments = splitGiftSegments(answerText);
    if (segments.length === 0) {
      records.push({
        rowNumber,
        content: unescapeGift(content),
        questionType: 'dien_khuyet',
        correctAnswer: unescapeGift(stripGiftFeedback(answerText)),
      });
      return;
    }

    const options = {};
    const correctKeys = [];
    const answers = segments.map((segment, segmentIndex) => {
      const parsed = parseGiftPercent(segment);
      const key = OPTION_KEYS[segmentIndex] || String(segmentIndex + 1);
      const answer = unescapeGift(stripGiftFeedback(parsed.text).trim());
      options[key] = answer;
      if (segment.marker === '=' || parsed.percent > 0) correctKeys.push(key);
      return answer;
    });

    const hasChoices = answers.length > 1;
    records.push({
      rowNumber,
      content: unescapeGift(content),
      questionType: hasChoices && correctKeys.length > 1 ? 'nhieu_lua_chon' : (hasChoices ? 'trac_nghiem' : 'dien_khuyet'),
      options: hasChoices ? options : undefined,
      correctAnswer: hasChoices ? correctKeys.join(', ') : answers[0],
    });
  });

  return { records, errors };
}

function firstXmlText(block, tagName) {
  const match = block.match(new RegExp(`<${tagName}\\b[^>]*>[\\s\\S]*?<text\\b[^>]*>([\\s\\S]*?)</text>[\\s\\S]*?</${tagName}>`, 'i'));
  return match ? xmlUnescape(match[1]) : '';
}

function parseXmlRecords(text) {
  const records = [];
  const errors = [];
  const questionMatches = Array.from(textValue(text).matchAll(/<question\b([^>]*)>([\s\S]*?)<\/question>/gi));

  questionMatches.forEach((match, index) => {
    const attrs = match[1] || '';
    const block = match[2] || '';
    const type = attrs.match(/type=["']([^"']+)["']/i)?.[1] || '';
    if (type.toLowerCase() === 'category') return;
    const rowNumber = index + 1;
    const content = firstXmlText(block, 'questiontext');
    const explanation = firstXmlText(block, 'generalfeedback');
    const answerBlocks = Array.from(block.matchAll(/<answer\b([^>]*)>([\s\S]*?)<\/answer>/gi));
    const answers = answerBlocks.map((answerMatch) => ({
      fraction: Number(answerMatch[1].match(/fraction=["']([^"']+)["']/i)?.[1] || 0),
      text: xmlUnescape(answerMatch[2].match(/<text\b[^>]*>([\s\S]*?)<\/text>/i)?.[1] || ''),
    }));
    const correctAnswers = answers.filter((answer) => answer.fraction > 0);

    if (!content) {
      errors.push(`XML question ${rowNumber}: missing question text`);
      return;
    }

    if (type === 'truefalse') {
      const correct = correctAnswers[0]?.text.toLowerCase() === 'true' ? 'A' : 'B';
      records.push({
        rowNumber,
        content,
        questionType: 'dung_sai',
        options: { A: 'True', B: 'False' },
        correctAnswer: correct,
        explanation,
      });
      return;
    }

    if (type === 'shortanswer') {
      records.push({
        rowNumber,
        content,
        questionType: 'dien_khuyet',
        correctAnswer: correctAnswers.map((answer) => answer.text).join(', '),
        explanation,
      });
      return;
    }

    const options = {};
    const correctKeys = [];
    answers.forEach((answer, answerIndex) => {
      const key = OPTION_KEYS[answerIndex] || String(answerIndex + 1);
      options[key] = answer.text;
      if (answer.fraction > 0) correctKeys.push(key);
    });
    records.push({
      rowNumber,
      content,
      questionType: correctKeys.length > 1 ? 'nhieu_lua_chon' : 'trac_nghiem',
      options,
      correctAnswer: correctKeys.join(', '),
      explanation,
    });
  });

  if (questionMatches.length === 0) {
    errors.push('XML must include at least one <question> element');
  }
  return { records, errors };
}

function findByReference(items, reference, fields) {
  const wanted = compactKey(reference);
  if (!wanted) return null;
  return items.find((item) => fields.some((field) => compactKey(item?.[field]) === wanted)) || null;
}

function resolveSubject(subjectRef, subjects) {
  if (!subjectRef) return { subject: null, id: '' };
  const subject = findByReference(subjects, subjectRef, ['id', '_id', 'subject_code', 'code', 'name', 'title', 'subject_name']);
  if (!subject) return { subject: null, id: '', error: `subject not found: ${subjectRef}` };
  return { subject, id: refId(subject) };
}

function resolveChapter(chapterRef, subject) {
  if (!chapterRef) return { id: '' };
  if (!subject) return { id: '', error: 'chapter requires a valid subject' };
  const chapter = findByReference(subject.chapters || [], chapterRef, ['id', '_id', 'chapter_code', 'code', 'name', 'title', 'chapter_name']);
  if (!chapter) return { id: '', error: `chapter not found: ${chapterRef}` };
  return { id: refId(chapter) };
}

function resolveCloIds(cloRefs, subject) {
  if (!cloRefs.length) return { ids: [] };
  if (!subject) return { ids: [], error: 'CLO requires a valid subject' };
  const ids = [];
  const missing = [];
  cloRefs.forEach((cloRef) => {
    const clo = findByReference(subject.learning_outcomes || [], cloRef, ['id', '_id', 'clo_code', 'code', 'name', 'title']);
    if (clo) {
      ids.push(refId(clo));
    } else {
      missing.push(cloRef);
    }
  });
  if (missing.length > 0) return { ids, error: `CLO not found: ${missing.join(', ')}` };
  return { ids };
}

function parseBloomLevel(value) {
  const text = textValue(value).trim();
  if (!text) return undefined;
  const number = Number(text);
  if (Number.isInteger(number) && number >= 1 && number <= 6) return number;
  return null;
}

function normalizeOptions(options) {
  if (!options || typeof options !== 'object' || Array.isArray(options)) return undefined;
  const entries = sortedOptionEntries(options);
  if (entries.length === 0) return undefined;
  return Object.fromEntries(entries);
}

function buildPayloads(records, subjects) {
  const items = [];
  const errors = [];

  records.forEach((record, index) => {
    const rowNumber = record.rowNumber || index + 1;
    const content = textValue(record.content).trim();
    if (!content) {
      errors.push(`Row ${rowNumber}: content is required`);
      return;
    }

    const subjectResult = resolveSubject(textValue(record.subjectRef).trim(), subjects);
    const chapterResult = resolveChapter(textValue(record.chapterRef).trim(), subjectResult.subject);
    const cloResult = resolveCloIds(record.cloRefs || [], subjectResult.subject);
    const bloomLevel = parseBloomLevel(record.bloomLevel);
    if (bloomLevel === null) errors.push(`Row ${rowNumber}: bloom_level must be from 1 to 6`);
    if (subjectResult.error) errors.push(`Row ${rowNumber}: ${subjectResult.error}`);
    if (chapterResult.error) errors.push(`Row ${rowNumber}: ${chapterResult.error}`);
    if (cloResult.error) errors.push(`Row ${rowNumber}: ${cloResult.error}`);

    const difficulty = normalizedKey(record.difficulty);
    if (difficulty && !DIFFICULTIES.has(difficulty)) {
      errors.push(`Row ${rowNumber}: difficulty must be de, trung_binh, or kho`);
    }

    const payload = {
      content,
      question_type: normalizeQuestionBankType(record.questionType),
      question_data: {
        correct_answer: textValue(record.correctAnswer).trim(),
        explanation: textValue(record.explanation).trim(),
      },
      clo_ids: cloResult.ids,
      source_chunk_ids: record.sourceChunkIds || [],
    };
    const options = normalizeOptions(record.options);
    if (options) payload.question_data.options = options;
    if (bloomLevel) payload.bloom_level = bloomLevel;
    if (difficulty && DIFFICULTIES.has(difficulty)) payload.difficulty = difficulty;
    if (subjectResult.id) payload.subject_id = subjectResult.id;
    if (chapterResult.id) payload.chapter_id = chapterResult.id;

    items.push({ rowNumber, payload });
  });

  return { items, errors };
}

function detectImportFormat(filename, explicitFormat) {
  if (explicitFormat) return explicitFormat;
  const extension = textValue(filename).split('.').pop()?.toLowerCase();
  if (extension === 'csv') return 'csv';
  if (extension === 'xlsx') return 'xlsx';
  if (extension === 'xml') return 'xml';
  if (extension === 'gift' || extension === 'txt') return 'gift';
  return '';
}

export function parseQuestionBankImport(text, { filename = '', format = '', subjects = [] } = {}) {
  const detectedFormat = detectImportFormat(filename, format);
  let parsed;
  if (detectedFormat === 'csv') parsed = parseCsvRecords(text);
  else if (detectedFormat === 'gift') parsed = parseGiftRecords(text);
  else if (detectedFormat === 'xml') parsed = parseXmlRecords(text);
  else {
    return { items: [], errors: [`Unsupported import format: ${filename || format || 'unknown'}`] };
  }

  const built = buildPayloads(parsed.records, subjects);
  return {
    items: built.items,
    errors: [...parsed.errors, ...built.errors],
    format: detectedFormat,
  };
}

export async function parseQuestionBankImportFile(file, { subjects = [] } = {}) {
  const detectedFormat = detectImportFormat(file?.name || '', '');
  if (detectedFormat === 'xlsx') {
    try {
      const parsed = await parseXlsxRecords(await file.arrayBuffer());
      const built = buildPayloads(parsed.records, subjects);
      return {
        items: built.items,
        errors: [...parsed.errors, ...built.errors],
        format: detectedFormat,
      };
    } catch (error) {
      return { items: [], errors: [error.message || 'Cannot parse XLSX file'], format: detectedFormat };
    }
  }
  return parseQuestionBankImport(await file.text(), { filename: file?.name || '', subjects });
}
