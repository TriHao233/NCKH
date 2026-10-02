import { bloomLevelLabel, questionTypeLabel } from '../constants/generationEnums.js';

// Thứ tự nhóm theo đúng trình tự ghép prompt sinh câu hỏi, thẩm định để cuối.
const KIND_LABELS = {
  SYSTEM: 'Vai trò hệ thống',
  QUESTION_RULE: 'Quy tắc ra câu hỏi',
  BLOOM: 'Mức Bloom',
  DIFFICULTY_RULE: 'Quy định độ khó',
  QUESTION_TYPE: 'Hướng dẫn theo loại câu hỏi',
  QUESTION_STRUCTURE: 'Cấu trúc theo loại câu hỏi',
  OUTPUT_FORMAT: 'Định dạng đầu ra',
  EVALUATION: 'Thẩm định câu hỏi',
};
const KIND_ORDER = Object.keys(KIND_LABELS);

const FIXED_TITLES = {
  system: 'Vai trò hệ thống',
  question_rule: 'Các lỗi cần tránh',
  quy_dinh_do_kho: 'Quy định độ khó',
  output_format: 'Định dạng đầu ra',
  'evaluation:output_contract': 'Khuôn dạng kết quả chấm',
  'evaluation:question_quality': 'Tiêu chí chất lượng',
  'evaluation:scoring_policy': 'Cách tính điểm',
};

// Mã Bloom kiểu cũ không có số thứ tự, vẫn còn trong dữ liệu.
const LEGACY_BLOOM = {
  nho: 'Nhớ', hieu: 'Hiểu', van_dung: 'Vận dụng', phan_tich: 'Phân tích', danh_gia: 'Đánh giá', sang_tao: 'Sáng tạo',
};

export function promptKindLabel(kind) {
  return KIND_LABELS[kind] || kind || 'Khác';
}

export function promptTitle(template) {
  const key = template.template_key || '';
  if (FIXED_TITLES[key]) return FIXED_TITLES[key];
  const [prefix, ...rest] = key.split(':');
  const suffix = rest.join(':');
  if (prefix === 'bloom' && suffix) {
    return LEGACY_BLOOM[suffix] ? `${LEGACY_BLOOM[suffix]} (mã cũ)` : bloomLevelLabel(suffix);
  }
  if ((prefix === 'question_type' || prefix === 'question_structure') && suffix) return questionTypeLabel(suffix);
  if (key.startsWith('evaluation:question_type:')) {
    const type = key.slice('evaluation:question_type:'.length);
    return type === 'general' ? 'Mọi loại câu hỏi' : `Riêng loại ${questionTypeLabel(type)}`;
  }
  return template.name || key;
}

// Gom các phiên bản theo mã prompt rồi xếp vào nhóm; mỗi mục giữ bản đang dùng và bản mới nhất.
export function groupPrompts(templates = [], search = '') {
  const byKey = new Map();
  templates.forEach((template) => {
    const versions = byKey.get(template.template_key) || [];
    versions.push(template);
    byKey.set(template.template_key, versions);
  });
  const needle = search.trim().toLowerCase();
  const groups = new Map();
  byKey.forEach((versions, key) => {
    versions.sort((left, right) => right.version - left.version);
    const latest = versions[0];
    const item = {
      key,
      kind: latest.kind,
      title: promptTitle(latest),
      versions,
      latest,
      active: versions.find((version) => version.is_active) || null,
    };
    if (needle && ![item.title, key, latest.name].some((value) => String(value || '').toLowerCase().includes(needle))) return;
    const items = groups.get(item.kind) || [];
    items.push(item);
    groups.set(item.kind, items);
  });
  const rank = (kind) => (KIND_ORDER.includes(kind) ? KIND_ORDER.indexOf(kind) : KIND_ORDER.length);
  return [...groups.entries()]
    .sort(([left], [right]) => rank(left) - rank(right) || String(left).localeCompare(String(right)))
    .map(([kind, items]) => ({
      kind,
      label: promptKindLabel(kind),
      items: items.sort((left, right) => left.key.localeCompare(right.key)),
    }));
}
