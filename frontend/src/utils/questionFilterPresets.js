export const QUESTION_FILTER_STORAGE_VERSION = 1;

export const QUESTION_FILTER_DEFAULTS = Object.freeze({
  statusFilter: 'all',
  typeFilter: 'all-type',
  documentFilter: 'all-documents',
  subjectFilter: 'all-subjects',
  chapterFilter: 'all-chapters',
  cloFilter: 'all-clos',
  bloomFilter: 'all-bloom',
  difficultyFilter: 'all-difficulties',
  evaluationFilter: 'all-evaluations',
  publicationFilter: 'all-publications',
  searchInput: '',
});

export function questionFilterStorageKey(user) {
  const owner = user?.id || user?.uid || user?.email || 'anonymous';
  return `qbankctu:question-filters:${owner}`;
}

export function parseSavedQuestionFilters(rawValue) {
  if (!rawValue) return [];
  try {
    const payload = JSON.parse(rawValue);
    const items = Array.isArray(payload) ? payload : payload?.items;
    if (!Array.isArray(items)) return [];
    return items
      .filter((item) => item?.id && item?.name && item?.filters)
      .map((item) => ({
        id: String(item.id),
        name: String(item.name),
        filters: { ...QUESTION_FILTER_DEFAULTS, ...item.filters },
        updated_at: item.updated_at || null,
      }));
  } catch {
    return [];
  }
}

export function encodeSavedQuestionFilters(items) {
  return JSON.stringify({
    version: QUESTION_FILTER_STORAGE_VERSION,
    items,
  });
}
