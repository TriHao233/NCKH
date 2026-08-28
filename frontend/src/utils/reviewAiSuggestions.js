const VALID_SEVERITIES = new Set(['LOW', 'MEDIUM', 'HIGH']);

function numericScore(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function uniqueTexts(values) {
  const seen = new Set();
  const normalized = Array.isArray(values) ? values : (values ? [values] : []);
  return normalized
    .map((value) => String(value || '').trim())
    .filter((value) => {
      const key = value.toLocaleLowerCase('vi');
      if (!value || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

export function evaluationInsights(evaluation, components) {
  const scores = evaluation?.scores || {};
  const passMin = evaluation?.policy?.thresholds?.pass_min ?? 0.65;
  const scored = (components || [])
    .map((component) => ({ ...component, score: numericScore(scores[component.key]) }))
    .filter((component) => component.score !== null);
  const values = scored.map((component) => component.score);
  const spread = values.length ? Math.max(...values) - Math.min(...values) : null;
  return {
    passMin,
    weakCriteria: scored.filter((component) => component.score < passMin),
    uniformScores: values.length >= 3 && spread <= 0.02,
    spread,
  };
}

export function mergeAiSuggestionsIntoDraft(draft, evaluation, timestamp = Date.now()) {
  if (!draft || !evaluation) return draft;
  const feedback = evaluation.feedback || {};
  const evidence = evaluation.evidence || {};
  const scores = evaluation.scores || {};
  const severity = VALID_SEVERITIES.has(String(feedback.severity || '').toUpperCase())
    ? String(feedback.severity).toUpperCase()
    : 'MEDIUM';
  const suggestions = [
    ...uniqueTexts(feedback.missing),
    ...uniqueTexts(evidence.risks),
  ];
  const existingTexts = new Set(
    (draft.issues || []).map((issue) => String(issue.detail || issue.title || '').trim().toLocaleLowerCase('vi')),
  );
  const addedIssues = suggestions
    .filter((text) => !existingTexts.has(text.toLocaleLowerCase('vi')))
    .slice(0, 8)
    .map((text, index) => ({
      id: `ai-issue-${timestamp}-${index}`,
      title: `Góp ý AI ${index + 1}`,
      severity,
      detail: text,
      source_chunk_id: '',
      page_number: '',
    }));

  const summary = String(feedback.summary || evidence.reasoning || '').trim();
  const action = String(feedback.action || '').trim().toUpperCase();
  const aiNote = summary ? `Gợi ý AI${action ? ` (${action})` : ''}: ${summary}` : '';
  const currentNote = String(draft.overallNote || '').trim();
  const overallNote = aiNote && !currentNote.includes(aiNote)
    ? [currentNote, aiNote].filter(Boolean).join('\n')
    : currentNote;

  return {
    ...draft,
    overallNote,
    criteria: (draft.criteria || []).map((criterion) => {
      const value = numericScore(scores[criterion.key]);
      if (value === null) return criterion;
      return {
        ...criterion,
        rating: value >= 0.75 ? 'PASS' : value >= 0.5 ? 'REVIEW' : 'FAIL',
        note: criterion.note || `AI chấm ${value.toFixed(2)}; người duyệt cần đối chiếu trước khi kết luận.`,
      };
    }),
    issues: [...(draft.issues || []), ...addedIssues],
  };
}
