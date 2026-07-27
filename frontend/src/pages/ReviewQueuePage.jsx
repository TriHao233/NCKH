import React, { useContext, useEffect, useMemo, useState } from 'react';
import {
  assignQuestionReview,
  autoEvaluateQuestion,
  claimQuestionReview,
  exportQuestionMoodle,
  fetchQuestionSourcePdf,
  getQuestionSources,
  listQuestionEvaluations,
  listQuestionMoodlePublications,
  listQuestionReviews,
  listQuestions,
  publishQuestionToMoodle,
  releaseQuestionReview,
  reviewQuestion,
} from '../api/questions';
import { AuthContext } from '../context/AuthContext';
import { BLOOM_LEVELS, QUESTION_TYPES, questionTypeLabel } from '../constants/generationEnums';
import '../css/ReviewQueuePage.css';

const REVIEW_STATUS_LABEL = {
  all: 'Tất cả',
  PENDING: 'Chờ duyệt',
  APPROVED: 'Đã duyệt',
  NEEDS_REVISION: 'Cần sửa',
  REJECTED: 'Từ chối',
};

const COLOR_LABEL = {
  all: 'Mọi mức chất lượng',
  GREEN: 'Đạt tốt',
  YELLOW: 'Cần xem lại',
  RED: 'Rủi ro cao',
};

const EVALUATION_STATUS_LABEL = {
  NOT_STARTED: 'Chưa đánh giá',
  QUEUED: 'Chờ AI đánh giá',
  PROCESSING: 'Đang đánh giá',
  RUNNING: 'Đang đánh giá',
  PASSED: 'Đạt AI',
  FAILED: 'Chưa đạt AI',
  ERROR: 'AI lỗi',
  STALE: 'Cần đánh giá lại',
};

const PUBLICATION_STATUS_LABEL = {
  NOT_PUBLISHED: 'Chưa ghi mô phỏng',
  PENDING: 'Đang chờ',
  PUBLISHED: 'Đã ghi mô phỏng',
  FAILED: 'Mô phỏng lỗi',
};

const ASSIGNMENT_STATUS_LABEL = {
  all: 'Mọi phân công',
  mine: 'Của tôi',
  UNASSIGNED: 'Chưa claim',
  ASSIGNED: 'Đã gán',
  IN_REVIEW: 'Đang xử lý',
};

const PAGE_SIZE = 20;

const SCORE_COMPONENTS = [
  {
    key: 'faithfulness',
    label: 'Bám sát nguồn',
  },
  {
    key: 'contextual_relevancy',
    label: 'Phù hợp ngữ cảnh',
  },
  {
    key: 'answer_relevancy',
    label: 'Đáp án phù hợp',
  },
  {
    key: 'bloom_alignment',
    label: 'Đúng Bloom',
  },
  {
    key: 'clo_alignment',
    label: 'Đúng CLO',
  },
];

const REVIEW_RUBRIC = [
  { key: 'source_alignment', label: 'Bám sát nguồn' },
  { key: 'answer_correctness', label: 'Đáp án đúng' },
  { key: 'bloom_clo_alignment', label: 'Đúng Bloom/CLO' },
  { key: 'language_quality', label: 'Diễn đạt rõ' },
  { key: 'moodle_readiness', label: 'Sẵn sàng Moodle' },
];

function defaultReviewDraft(question, decision) {
  return {
    questionId: question.id,
    questionCode: question.question_code,
    decision,
    overallNote: '',
    overrideReason: '',
    checklist: REVIEW_RUBRIC.map((item) => ({
      ...item,
      passed: decision === 'APPROVED',
      note: '',
    })),
    issues: [],
  };
}

function reviewDraftKey(questionId, decision) {
  return `review-draft:${questionId}:${decision}`;
}

function loadReviewDraft(question, decision) {
  const fallback = defaultReviewDraft(question, decision);
  try {
    const saved = localStorage.getItem(reviewDraftKey(question.id, decision));
    if (!saved) return fallback;
    const parsed = JSON.parse(saved);
    return {
      ...fallback,
      ...parsed,
      checklist: REVIEW_RUBRIC.map((item) => {
        const savedItem = (parsed.checklist || []).find((entry) => entry.key === item.key);
        return savedItem ? { ...item, ...savedItem } : { ...item, passed: false, note: '' };
      }),
      issues: Array.isArray(parsed.issues)
        ? parsed.issues.map((issue, index) => ({ id: issue.id || `issue-${index}`, ...issue }))
        : [],
    };
  } catch {
    return fallback;
  }
}

function compactIssues(issues) {
  return (issues || [])
    .map((issue) => ({
      title: (issue.title || '').trim(),
      severity: issue.severity || 'MEDIUM',
      detail: (issue.detail || '').trim(),
      source_chunk_id: issue.source_chunk_id || null,
      page_number: issue.page_number ? Number(issue.page_number) : null,
    }))
    .filter((issue) => issue.title || issue.detail);
}

function reviewIssuesOf(review) {
  if (Array.isArray(review?.revision_issues)) return review.revision_issues;
  if (Array.isArray(review?.review_form?.revision_issues)) {
    return review.review_form.revision_issues;
  }
  return [];
}

function score(value) {
  return typeof value === 'number' ? value.toFixed(2) : '--';
}

function percent(value) {
  return typeof value === 'number' ? `${Math.round(value * 100)}%` : '--';
}

function formatDate(value) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--';
  return date.toLocaleString('vi-VN');
}

function evaluationModeLabel(mode) {
  if (mode === 'local_llm') return 'AI cục bộ';
  if (mode === 'heuristic_fallback') return 'Đánh giá dự phòng';
  if (mode === 'heuristic') return 'Chấm nhanh nội bộ';
  return mode || '--';
}

function qualityColorLabel(value) {
  return COLOR_LABEL[value] || value || '--';
}

function evaluationStatusLabel(value) {
  return EVALUATION_STATUS_LABEL[value] || value || '--';
}

function isEvaluationBusy(question) {
  return ['QUEUED', 'PROCESSING', 'RUNNING'].includes(question?.evaluation_status);
}

function canQueueEvaluation(question) {
  return question && !isEvaluationBusy(question) && question.evaluation_status !== 'PASSED';
}

function publicationStatusLabel(value) {
  return PUBLICATION_STATUS_LABEL[value] || value || '--';
}

function assignmentOf(question) {
  const assignment = question?.review_assignment || {};
  return {
    status: assignment.status || 'UNASSIGNED',
    reviewer_user_id: assignment.reviewer_user_id || '',
    assigned_by_user_id: assignment.assigned_by_user_id || '',
    assigned_at: assignment.assigned_at || null,
    claimed_at: assignment.claimed_at || null,
    lock_expires_at: assignment.lock_expires_at || null,
    last_released_at: assignment.last_released_at || null,
    release_reason: assignment.release_reason || '',
  };
}

function isReviewLockExpired(assignment) {
  if (!assignment?.lock_expires_at) return false;
  const expiresAt = new Date(assignment.lock_expires_at);
  return !Number.isNaN(expiresAt.getTime()) && expiresAt.getTime() <= Date.now();
}

function isAssignmentMine(question, user) {
  const reviewerId = assignmentOf(question).reviewer_user_id;
  return Boolean(reviewerId && user?.id && String(reviewerId) === String(user.id));
}

function assignmentStatusLabel(question, user) {
  const assignment = assignmentOf(question);
  const mine = isAssignmentMine(question, user);
  if (assignment.status === 'IN_REVIEW' && isReviewLockExpired(assignment)) {
    return mine ? 'Lock của tôi hết hạn' : 'Lock hết hạn';
  }
  if (assignment.status === 'IN_REVIEW') return mine ? 'Tôi đang xử lý' : 'Đang xử lý';
  if (assignment.status === 'ASSIGNED') return mine ? 'Đã gán cho tôi' : 'Đã gán';
  return ASSIGNMENT_STATUS_LABEL[assignment.status] || assignment.status || 'Chưa claim';
}

function evaluatorModelLabel(model = {}) {
  if (model.model_name) return model.model_name;
  return model.model_code || '--';
}

function assessmentType(question) {
  return String(question?.classification?.assessment_type || '').toLowerCase();
}

function refId(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  return value.id || value._id || '';
}

function shortId(value) {
  const text = refId(value);
  if (!text) return '--';
  return text.length > 12 ? `${text.slice(0, 6)}...${text.slice(-4)}` : text;
}

function pageRangeLabel(pageRange = {}) {
  if (Array.isArray(pageRange.pages) && pageRange.pages.length > 0) {
    return `Trang ${pageRange.pages.join(', ')}`;
  }
  if (pageRange.start && pageRange.end) {
    return pageRange.start === pageRange.end
      ? `Trang ${pageRange.start}`
      : `Trang ${pageRange.start}-${pageRange.end}`;
  }
  if (pageRange.start) return `Trang ${pageRange.start}`;
  return 'Chưa có trang';
}

function firstSourcePage(source) {
  const pageNumber = source?.pages?.[0]?.page_number || source?.page_range?.start;
  return pageNumber ? Number(pageNumber) : 1;
}

function downloadMoodleExport(question, format, content) {
  const extension = format === 'xml' ? 'xml' : 'gift';
  const mimeType = format === 'xml' ? 'application/xml' : 'text/plain';
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${question.question_code || 'moodle-question'}.${extension}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function SourceText({ source, page }) {
  const excerpt = source?.context_excerpt || source?.chunk_text || '';
  const pageText = page?.text || source?.chunk_text || '';
  return (
    <div className="source-text">
      {excerpt && (
        <p className="source-highlight">
          <mark>{excerpt}</mark>
        </p>
      )}
      <p>{pageText || 'Chưa có OCR text cho trang này.'}</p>
    </div>
  );
}

function ReviewQueuePage() {
  const { user } = useContext(AuthContext);
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('PENDING');
  const [assignmentFilter, setAssignmentFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [bloomFilter, setBloomFilter] = useState('all');
  const [colorFilter, setColorFilter] = useState('all');
  const [minScore, setMinScore] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState(null);
  const [evaluations, setEvaluations] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [publications, setPublications] = useState([]);
  const [sourceViewer, setSourceViewer] = useState(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState('');
  const [activeSourceIndex, setActiveSourceIndex] = useState(0);
  const [activeSourcePage, setActiveSourcePage] = useState(1);
  const [sourcePdf, setSourcePdf] = useState(null);
  const [sourcePdfLoading, setSourcePdfLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [busyId, setBusyId] = useState('');
  const [bulkBusy, setBulkBusy] = useState(false);
  const [reviewDraft, setReviewDraft] = useState(null);
  const [reviewFormError, setReviewFormError] = useState('');
  const [assignmentDraft, setAssignmentDraft] = useState(null);
  const [assignmentError, setAssignmentError] = useState('');

  const fetchQuestions = async () => {
    setLoading(true);
    setError('');
    try {
      const numericMinScore = minScore === '' ? undefined : Number(minScore);
      const assignmentStatus = ['UNASSIGNED', 'ASSIGNED', 'IN_REVIEW'].includes(assignmentFilter)
        ? assignmentFilter
        : undefined;
      const result = await listQuestions({
        page,
        pageSize: PAGE_SIZE,
        reviewStatus: statusFilter === 'all' ? undefined : statusFilter,
        questionType: typeFilter === 'all' ? undefined : typeFilter,
        bloomLevel: bloomFilter === 'all' ? undefined : bloomFilter,
        qualityColor: colorFilter === 'all' ? undefined : colorFilter,
        minScore: Number.isFinite(numericMinScore) ? numericMinScore : undefined,
        search: searchTerm || undefined,
        assignmentStatus,
        assignedTo: assignmentFilter === 'mine' ? 'me' : undefined,
      });
      const items = result.items || [];
      setQuestions(items);
      setTotal(result.total || 0);
      return items;
    } catch (err) {
      setError(err.message || 'Không tải được hàng đợi kiểm duyệt');
      setQuestions([]);
      setTotal(0);
      return [];
    } finally {
      setLoading(false);
    }
  };

  const loadHistory = async (question) => {
    setSelected(question);
    setReviewDraft(null);
    setAssignmentDraft(null);
    setReviewFormError('');
    setAssignmentError('');
    setHistoryLoading(true);
    setSourceLoading(true);
    setSourceError('');
    setSourceViewer(null);
    setSourcePdf(null);
    setSourcePdfLoading(false);
    setActiveSourceIndex(0);
    setActiveSourcePage(1);
    try {
      const [evaluationResult, reviewResult, publicationResult, sourceResult] = await Promise.all([
        listQuestionEvaluations(question.id),
        listQuestionReviews(question.id),
        listQuestionMoodlePublications(question.id),
        getQuestionSources(question.id),
      ]);
      setEvaluations(evaluationResult.items || []);
      setReviews(reviewResult.items || []);
      setPublications(publicationResult.items || []);
      setSourceViewer(sourceResult);
      const firstSource = sourceResult.items?.[0];
      setActiveSourcePage(firstSourcePage(firstSource));
      setSourceLoading(false);
      if (sourceResult.document?.pdf_available) {
        setSourcePdfLoading(true);
        try {
          setSourcePdf(await fetchQuestionSourcePdf(question.id));
        } catch (err) {
          setSourceError(err.message || 'Không mở được PDF nguồn');
        } finally {
          setSourcePdfLoading(false);
        }
      }
    } catch (err) {
      setError(err.message || 'Không tải được lịch sử câu hỏi');
      setSourceError(err.message || 'Không tải được nguồn câu hỏi');
    } finally {
      setHistoryLoading(false);
      setSourceLoading(false);
    }
  };

  useEffect(() => {
    const handle = setTimeout(() => {
      setSearchTerm(searchInput.trim());
      setPage(1);
    }, 350);
    return () => clearTimeout(handle);
  }, [searchInput]);

  useEffect(() => {
    fetchQuestions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, statusFilter, assignmentFilter, typeFilter, bloomFilter, colorFilter, minScore, searchTerm]);

  useEffect(() => {
    if (!selected) return;
    const fresh = questions.find((item) => item.id === selected.id);
    if (fresh) {
      setSelected(fresh);
      return;
    }
    setSelected(null);
    setEvaluations([]);
    setReviews([]);
    setPublications([]);
    setSourceViewer(null);
    setSourceError('');
    setSourcePdf(null);
  }, [questions, selected]);

  useEffect(() => () => {
    if (sourcePdf?.url) {
      URL.revokeObjectURL(sourcePdf.url);
    }
  }, [sourcePdf?.url]);

  useEffect(() => {
    if (!reviewDraft?.questionId || !reviewDraft?.decision) return;
    localStorage.setItem(
      reviewDraftKey(reviewDraft.questionId, reviewDraft.decision),
      JSON.stringify(reviewDraft),
    );
  }, [reviewDraft]);

  const summary = useMemo(() => ({
    pending: questions.filter((item) => item.review_status === 'PENDING').length,
    mine: questions.filter((item) => isAssignmentMine(item, user)).length,
    passed: questions.filter((item) => item.evaluation_status === 'PASSED').length,
    green: questions.filter((item) => item.quality_summary?.color === 'GREEN').length,
    publishable: questions.filter((item) => item.review_status === 'APPROVED' && item.publication_status !== 'PUBLISHED').length,
  }), [questions, user]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const pageEnd = Math.min(page * PAGE_SIZE, total);

  const updateFilter = (setter) => (value) => {
    setter(value);
    setPage(1);
  };

  const openSource = (source, index) => {
    setActiveSourceIndex(index);
    setActiveSourcePage(firstSourcePage(source));
  };

  const canClaimQuestion = (question) => {
    if (!question || question.review_status !== 'PENDING') return false;
    const assignment = assignmentOf(question);
    return (
      assignment.status === 'UNASSIGNED'
      || isAssignmentMine(question, user)
      || isReviewLockExpired(assignment)
      || user?.role === 'Admin'
    );
  };

  const canReleaseQuestion = (question) => {
    if (!question || question.review_status !== 'PENDING') return false;
    const assignment = assignmentOf(question);
    if (assignment.status === 'UNASSIGNED') return false;
    return user?.role === 'Admin' || isAssignmentMine(question, user);
  };

  const canReviewQuestion = (question) => {
    if (!question || question.review_status !== 'PENDING') return false;
    if (user?.role === 'Admin') return true;
    const assignment = assignmentOf(question);
    return (
      assignment.status === 'IN_REVIEW'
      && isAssignmentMine(question, user)
      && !isReviewLockExpired(assignment)
    );
  };

  const openReviewForm = (question, decision) => {
    if (!canReviewQuestion(question)) {
      alert('Bạn cần claim câu hỏi và giữ lock còn hiệu lực trước khi kiểm duyệt.');
      return;
    }
    setReviewFormError('');
    setReviewDraft(loadReviewDraft(question, decision));
  };

  const updateReviewDraft = (updates) => {
    setReviewDraft((current) => ({ ...current, ...updates }));
  };

  const updateChecklistItem = (key, updates) => {
    setReviewDraft((current) => ({
      ...current,
      checklist: current.checklist.map((item) => (
        item.key === key ? { ...item, ...updates } : item
      )),
    }));
  };

  const addReviewIssue = () => {
    setReviewDraft((current) => ({
      ...current,
      issues: [
        ...current.issues,
        {
          id: `issue-${Date.now()}`,
          title: '',
          severity: 'MEDIUM',
          detail: '',
          source_chunk_id: '',
          page_number: '',
        },
      ],
    }));
  };

  const updateReviewIssue = (id, updates) => {
    setReviewDraft((current) => ({
      ...current,
      issues: current.issues.map((issue) => (
        issue.id === id ? { ...issue, ...updates } : issue
      )),
    }));
  };

  const removeReviewIssue = (id) => {
    setReviewDraft((current) => ({
      ...current,
      issues: current.issues.filter((issue) => issue.id !== id),
    }));
  };

  const refreshAfterAction = async (question) => {
    const items = await fetchQuestions();
    const fresh = items.find((item) => item.id === question.id);
    if (fresh) {
      await loadHistory(fresh);
    }
  };

  const claimReview = async (question) => {
    setBusyId(question.id);
    try {
      await claimQuestionReview(question.id);
      await refreshAfterAction(question);
    } catch (err) {
      alert('Claim review thất bại: ' + err.message);
    } finally {
      setBusyId('');
    }
  };

  const releaseReview = async (question) => {
    setBusyId(question.id);
    try {
      await releaseQuestionReview(question.id);
      await refreshAfterAction(question);
    } catch (err) {
      alert('Release review thất bại: ' + err.message);
    } finally {
      setBusyId('');
    }
  };

  const openAssignmentForm = (question) => {
    setAssignmentError('');
    setAssignmentDraft({
      question,
      reviewerUserId: assignmentOf(question).reviewer_user_id,
      note: '',
    });
  };

  const submitAssignmentForm = async () => {
    if (!assignmentDraft?.question) return;
    const question = assignmentDraft.question;
    const reviewerId = assignmentDraft.reviewerUserId.trim();
    setBusyId(question.id);
    setAssignmentError('');
    try {
      await assignQuestionReview(question.id, {
        reviewer_user_id: reviewerId || null,
        note: assignmentDraft.note,
      });
      setAssignmentDraft(null);
      await refreshAfterAction(question);
    } catch (err) {
      setAssignmentError(err.message || 'Phân công review thất bại');
    } finally {
      setBusyId('');
    }
  };

  const unassignReview = async (question) => {
    if (!window.confirm(`Bỏ phân công review cho ${question.question_code}?`)) return;
    setBusyId(question.id);
    try {
      await assignQuestionReview(question.id, {
        reviewer_user_id: null,
        note: 'Admin bỏ phân công',
      });
      await refreshAfterAction(question);
    } catch (err) {
      alert('Bỏ phân công review thất bại: ' + err.message);
    } finally {
      setBusyId('');
    }
  };

  const runEvaluation = async (question) => {
    setBusyId(question.id);
    try {
      await autoEvaluateQuestion(question.id, {
        expected_version: question.current_version,
        fallback_to_heuristic: false,
      });
      await refreshAfterAction(question);
    } catch (err) {
      alert('Đánh giá AI thất bại: ' + err.message);
    } finally {
      setBusyId('');
    }
  };

  const submitReviewForm = async () => {
    if (!selected || !reviewDraft) return;
    if (!canReviewQuestion(selected)) {
      setReviewFormError('Bạn cần claim câu hỏi và giữ lock còn hiệu lực trước khi kiểm duyệt.');
      return;
    }
    const revisionIssues = compactIssues(reviewDraft.issues);
    const overallNote = reviewDraft.overallNote.trim();
    const needsOverride = reviewDraft.decision === 'APPROVED' && selected.evaluation_status !== 'PASSED';
    if (needsOverride && !reviewDraft.overrideReason.trim()) {
      setReviewFormError('Cần ghi lý do override khi duyệt câu chưa đạt AI.');
      return;
    }
    if (reviewDraft.decision === 'REJECTED' && !overallNote && revisionIssues.length === 0) {
      setReviewFormError('Cần ghi lý do khi từ chối câu hỏi.');
      return;
    }
    if (reviewDraft.decision === 'NEEDS_REVISION' && revisionIssues.length === 0) {
      setReviewFormError('Cần thêm ít nhất một lỗi cần Teacher sửa.');
      return;
    }
    const payload = {
      expected_version: selected.current_version,
      decision: reviewDraft.decision,
      note: overallNote,
      review_form: {
        checklist: reviewDraft.checklist.map((item) => ({
          key: item.key,
          label: item.label,
          passed: Boolean(item.passed),
          note: item.note || '',
        })),
        overall_note: overallNote,
        revision_issues: revisionIssues,
      },
    };
    if (needsOverride) {
      payload.override = {
        applied: true,
        reason: reviewDraft.overrideReason.trim(),
      };
      if (typeof selected.quality_summary?.overall_score === 'number') {
        payload.override.score = selected.quality_summary.overall_score;
      }
      if (selected.quality_summary?.color) {
        payload.override.color = selected.quality_summary.color;
      }
    }
    setBusyId(selected.id);
    setReviewFormError('');
    try {
      await reviewQuestion(selected.id, payload);
      localStorage.removeItem(reviewDraftKey(selected.id, reviewDraft.decision));
      setReviewDraft(null);
      await refreshAfterAction(selected);
    } catch (err) {
      setReviewFormError(err.message || 'Kiểm duyệt thất bại');
    } finally {
      setBusyId('');
    }
  };

  const publish = async (question) => {
    setBusyId(question.id);
    try {
      await publishQuestionToMoodle(question.id, {
        expected_version: question.current_version,
        export_format: 'BOTH',
        mock: true,
      });
      await refreshAfterAction(question);
    } catch (err) {
      alert('Ghi mô phỏng Moodle thất bại: ' + err.message);
    } finally {
      setBusyId('');
    }
  };

  const exportMoodle = async (question, format) => {
    setBusyId(question.id);
    try {
      const content = await exportQuestionMoodle(question.id, format);
      downloadMoodleExport(question, format, content);
    } catch (err) {
      alert('Export Moodle thất bại: ' + err.message);
    } finally {
      setBusyId('');
    }
  };

  const runBulkEvaluate = async () => {
    const targets = questions.filter((question) => canQueueEvaluation(question)).slice(0, 10);
    if (targets.length === 0) return;
    if (!window.confirm(`Đưa ${targets.length} câu đang lọc vào hàng đợi AI đánh giá?`)) return;
    setBulkBusy(true);
    try {
      for (const question of targets) {
        await autoEvaluateQuestion(question.id, {
          expected_version: question.current_version,
          fallback_to_heuristic: false,
        });
      }
      await fetchQuestions();
    } catch (err) {
      alert('Đánh giá hàng loạt dừng lại: ' + err.message);
    } finally {
      setBulkBusy(false);
    }
  };

  const runBulkApproveGreen = async () => {
    const targets = questions
      .filter((question) => (
        canReviewQuestion(question)
        && question.evaluation_status === 'PASSED'
        && question.quality_summary?.color === 'GREEN'
      ))
      .slice(0, 10);
    if (targets.length === 0) return;
    const note = 'Duyệt hàng loạt các câu đạt tốt';
    if (!window.confirm(`Duyệt ${targets.length} câu đạt tốt đang lọc?`)) return;
    setBulkBusy(true);
    try {
      for (const question of targets) {
        await reviewQuestion(question.id, {
          expected_version: question.current_version,
          decision: 'APPROVED',
          note,
          review_form: {
            checklist: REVIEW_RUBRIC.map((item) => ({
              ...item,
              passed: true,
              note: '',
            })),
            overall_note: note,
            revision_issues: [],
          },
        });
      }
      await fetchQuestions();
    } catch (err) {
      alert('Duyệt hàng loạt dừng lại: ' + err.message);
    } finally {
      setBulkBusy(false);
    }
  };

  const latestEvaluation = evaluations[0];
  const latestEvidence = latestEvaluation?.evidence || {};
  const latestScores = latestEvaluation?.scores || {};
  const latestWeights = latestEvaluation?.policy?.weights || {};
  const qualitySummary = selected?.quality_summary || {};
  const overallScore = latestScores.overall ?? qualitySummary.overall_score;
  const evaluationColor = latestEvaluation?.color || qualitySummary.color;
  const latestModel = latestEvaluation?.evaluator_model || {};
  const selectedAssignment = assignmentOf(selected);
  const sourceItems = sourceViewer?.items || [];
  const activeSource = sourceItems[activeSourceIndex] || sourceItems[0] || null;
  const activeSourcePages = activeSource?.pages || [];
  const activePageRecord = activeSourcePages.find((pageItem) => (
    pageItem.page_number === activeSourcePage
  )) || activeSourcePages[0] || null;
  const pdfPage = activeSourcePage || activePageRecord?.page_number || 1;
  const sourcePdfUrl = sourcePdf?.url ? `${sourcePdf.url}#page=${pdfPage}` : '';
  const reviewNeedsOverride = reviewDraft?.decision === 'APPROVED' && selected?.evaluation_status !== 'PASSED';

  return (
    <main className="review-page">
      <section className="review-toolbar">
        <div className="review-toolbar__title">
          <span>Hàng đợi kiểm duyệt</span>
          <h1>Kiểm duyệt câu hỏi</h1>
        </div>
        <div className="review-actions">
          <button type="button" className="btn btn--outline" disabled={bulkBusy} onClick={runBulkEvaluate}>
            Xếp hàng AI
          </button>
          <button type="button" className="btn btn--primary" disabled={bulkBusy} onClick={runBulkApproveGreen}>
            Duyệt câu đạt tốt
          </button>
        </div>
      </section>

      <section className="review-summary">
        <button type="button" onClick={() => updateFilter(setStatusFilter)('PENDING')}>
          <b>{statusFilter === 'PENDING' ? total : summary.pending}</b>
          <span>Chờ duyệt</span>
        </button>
        <button type="button" onClick={() => updateFilter(setAssignmentFilter)('mine')}>
          <b>{assignmentFilter === 'mine' ? total : summary.mine}</b>
          <span>Của tôi</span>
        </button>
        <button type="button" onClick={() => updateFilter(setColorFilter)('GREEN')}>
          <b>{colorFilter === 'GREEN' ? total : summary.green}</b>
          <span>Đạt tốt</span>
        </button>
        <button type="button" onClick={() => updateFilter(setMinScore)('0.8')}>
          <b>{minScore === '0.8' ? total : summary.passed}</b>
          <span>AI đạt</span>
        </button>
        <button type="button" onClick={() => updateFilter(setStatusFilter)('APPROVED')}>
          <b>{statusFilter === 'APPROVED' ? total : summary.publishable}</b>
          <span>Đã duyệt</span>
        </button>
      </section>

      <section className="review-layout">
        <div className="review-list-panel">
          <div className="review-filters">
            <select value={statusFilter} onChange={(event) => updateFilter(setStatusFilter)(event.target.value)}>
              {Object.entries(REVIEW_STATUS_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <select value={assignmentFilter} onChange={(event) => updateFilter(setAssignmentFilter)(event.target.value)}>
              {Object.entries(ASSIGNMENT_STATUS_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <select value={typeFilter} onChange={(event) => updateFilter(setTypeFilter)(event.target.value)}>
              <option value="all">Mọi dạng câu hỏi</option>
              {QUESTION_TYPES.map((type) => (
                <option key={type.backend} value={type.backend}>{type.label}</option>
              ))}
            </select>
            <select value={bloomFilter} onChange={(event) => updateFilter(setBloomFilter)(event.target.value)}>
              <option value="all">Mọi Bloom</option>
              {BLOOM_LEVELS.map((level) => (
                <option key={level.level} value={level.level}>{level.label}</option>
              ))}
            </select>
            <select value={colorFilter} onChange={(event) => updateFilter(setColorFilter)(event.target.value)}>
              {Object.entries(COLOR_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <input
              type="number"
              min="0"
              max="1"
              step="0.05"
              placeholder="Điểm tối thiểu"
              value={minScore}
              onChange={(event) => updateFilter(setMinScore)(event.target.value)}
            />
            <input
              placeholder="Tìm mã hoặc nội dung..."
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
            />
          </div>

          {error && <p className="review-error">{error}</p>}
          {loading ? (
            <p className="review-empty">Đang tải hàng đợi...</p>
          ) : (
            <div className="review-list">
              {questions.map((question) => (
                <article
                  key={question.id}
                  className={`review-row ${selected?.id === question.id ? 'review-row--active' : ''}`}
                  onClick={() => loadHistory(question)}
                >
                  <div>
                    <div className="review-row__meta">
                      <span>{question.question_code}</span>
                      <span>{questionTypeLabel(assessmentType(question))}</span>
                      <span>{question.classification?.bloom?.name || 'Bloom --'}</span>
                      <span className={`assignment-chip assignment-chip--${assignmentOf(question).status.toLowerCase()}`}>
                        {assignmentStatusLabel(question, user)}
                      </span>
                      {(question.clos || []).slice(0, 2).map((clo) => (
                        <span className="review-clo-chip" key={refId(clo.id || clo)}>
                          {clo.code || clo.clo_code || 'CLO'}
                        </span>
                      ))}
                    </div>
                    <p>{question.content}</p>
                  </div>
                  <div className="review-row__status">
                    <b className={`quality-${question.quality_summary?.color || 'NONE'}`}>
                      {score(question.quality_summary?.overall_score)}
                    </b>
                    <span>
                      {question.quality_summary?.color
                        ? qualityColorLabel(question.quality_summary.color)
                        : evaluationStatusLabel(question.evaluation_status)}
                    </span>
                    <small>{REVIEW_STATUS_LABEL[question.review_status] || question.review_status}</small>
                  </div>
                </article>
              ))}
              {questions.length === 0 && <p className="review-empty">Không có câu hỏi phù hợp bộ lọc.</p>}
              <div className="review-pagination">
                <span>
                  {pageStart}-{pageEnd} / {total} kết quả
                </span>
                <div>
                  <button
                    type="button"
                    disabled={loading || page <= 1}
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                  >
                    Trước
                  </button>
                  <button
                    type="button"
                    disabled={loading || page >= totalPages}
                    onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                  >
                    Sau
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        <aside className="review-detail-panel">
          {!selected ? (
            <p className="review-empty">Chọn một câu hỏi để xem minh chứng, tài liệu nguồn và lịch sử.</p>
          ) : (
            <>
              <div className="detail-head">
                <span>{selected.question_code}</span>
                <h2>{selected.content}</h2>
                {(selected.clos || []).length > 0 && (
                  <div className="detail-clo-list">
                    {selected.clos.map((clo) => (
                      <span key={refId(clo.id || clo)}>
                        <b>{clo.code || clo.clo_code || 'CLO'}</b>
                        {clo.description ? ` - ${clo.description}` : ''}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <section className="assignment-panel">
                <div>
                  <span>Phân công</span>
                  <b>{assignmentStatusLabel(selected, user)}</b>
                </div>
                <div>
                  <span>Reviewer</span>
                  <b>{selectedAssignment.reviewer_user_id || '--'}</b>
                </div>
                <div>
                  <span>Claim lúc</span>
                  <b>{formatDate(selectedAssignment.claimed_at || selectedAssignment.assigned_at)}</b>
                </div>
                <div>
                  <span>Hết lock</span>
                  <b>{formatDate(selectedAssignment.lock_expires_at)}</b>
                </div>
              </section>
              <div className="detail-actions">
                <button type="button" disabled={busyId === selected.id || !canClaimQuestion(selected)} onClick={() => claimReview(selected)}>
                  {selectedAssignment.status === 'IN_REVIEW' && isAssignmentMine(selected, user) ? 'Gia hạn claim' : 'Claim'}
                </button>
                <button type="button" disabled={busyId === selected.id || !canReleaseQuestion(selected)} onClick={() => releaseReview(selected)}>
                  Release
                </button>
                {user?.role === 'Admin' && (
                  <button type="button" disabled={busyId === selected.id || selected.review_status !== 'PENDING'} onClick={() => openAssignmentForm(selected)}>
                    Gán reviewer
                  </button>
                )}
                {user?.role === 'Admin' && (
                  <button type="button" disabled={busyId === selected.id || !canReleaseQuestion(selected)} onClick={() => unassignReview(selected)}>
                    Bỏ gán
                  </button>
                )}
                <button type="button" disabled={busyId === selected.id || !canQueueEvaluation(selected)} onClick={() => runEvaluation(selected)}>
                  {selected.evaluation_status === 'ERROR' || selected.evaluation_status === 'FAILED' || selected.evaluation_status === 'STALE'
                    ? 'Thử lại AI'
                    : 'AI đánh giá'}
                </button>
                <button
                  type="button"
                  className="detail-action-primary"
                  disabled={busyId === selected.id || isEvaluationBusy(selected) || !canReviewQuestion(selected)}
                  onClick={() => openReviewForm(selected, 'APPROVED')}
                >
                  Duyệt
                </button>
                <button type="button" disabled={busyId === selected.id || !canReviewQuestion(selected)} onClick={() => openReviewForm(selected, 'NEEDS_REVISION')}>Cần sửa</button>
                <button type="button" disabled={busyId === selected.id || !canReviewQuestion(selected)} onClick={() => openReviewForm(selected, 'REJECTED')}>Từ chối</button>
                <button
                  type="button"
                  disabled={busyId === selected.id || selected.review_status !== 'APPROVED' || selected.publication_status === 'PUBLISHED'}
                  onClick={() => publish(selected)}
                >
                  Mô phỏng Moodle
                </button>
                <button
                  type="button"
                  disabled={busyId === selected.id || selected.review_status !== 'APPROVED'}
                  onClick={() => exportMoodle(selected, 'gift')}
                >
                  GIFT
                </button>
                <button
                  type="button"
                  disabled={busyId === selected.id || selected.review_status !== 'APPROVED'}
                  onClick={() => exportMoodle(selected, 'xml')}
                >
                  XML
                </button>
              </div>

              {historyLoading ? (
                <p className="review-empty">Đang tải minh chứng...</p>
              ) : (
                <>
                  <section className="evaluation-panel">
                    <div className="evaluation-total">
                      <div>
                        <span>Tổng điểm</span>
                        <b className={`quality-${evaluationColor || 'NONE'}`}>{score(overallScore)}</b>
                      </div>
                      <div>
                        <span>Kết luận</span>
                        <strong>
                          {latestEvaluation
                            ? (latestEvaluation.passed ? 'Đạt' : 'Chưa đạt')
                            : evaluationStatusLabel(selected.evaluation_status)}
                        </strong>
                      </div>
                      <div>
                        <span>Mức chất lượng</span>
                        <strong className={`quality-${evaluationColor || 'NONE'}`}>{qualityColorLabel(evaluationColor)}</strong>
                      </div>
                      <div>
                        <span>Cách đánh giá</span>
                        <strong>{evaluationModeLabel(latestEvidence.mode)}</strong>
                      </div>
                    </div>

                    <div className="score-grid">
                      {SCORE_COMPONENTS.map((component) => (
                        <div key={component.key}>
                          <span>{component.label}</span>
                          <b>{score(latestScores[component.key])}</b>
                          <small>
                            Trọng số {percent(latestWeights[component.key])}
                          </small>
                        </div>
                      ))}
                    </div>

                    <div className="evaluation-meta">
                      <span>
                        Mô hình: <b>{evaluatorModelLabel(latestModel)}</b>
                      </span>
                      <span>Bộ tiêu chí: <b>{latestEvaluation?.policy?.name || '--'}</b></span>
                      <span>Đánh giá lúc: <b>{formatDate(latestEvaluation?.created_at || qualitySummary.evaluated_at)}</b></span>
                    </div>
                    {!latestEvaluation && (
                      <p className="evaluation-note">
                        Chưa có kết quả đánh giá AI cho câu hỏi này.
                      </p>
                    )}
                  </section>

                  <section className="evidence-block">
                    <h3>Minh chứng đánh giá</h3>
                    <p>{latestEvidence.supporting_excerpt || latestEvidence.source_excerpt || 'Chưa có minh chứng.'}</p>
                    {latestEvidence.reasoning && <span>{latestEvidence.reasoning}</span>}
                    {qualitySummary.error?.message && <span>Lỗi đánh giá AI: {qualitySummary.error.message}</span>}
                    {latestEvidence.fallback_reason && <span>Lý do dùng đánh giá dự phòng: {latestEvidence.fallback_reason}</span>}
                  </section>

                  <section className="source-viewer">
                    <div className="source-viewer__head">
                      <h3>Nguồn câu hỏi</h3>
                      <span>{sourceViewer?.document?.title || 'Không có tài liệu nguồn'}</span>
                    </div>
                    {sourceError && <p className="source-warning">{sourceError}</p>}
                    {(sourceViewer?.warnings || []).map((warning) => (
                      <p className="source-warning" key={warning}>{warning}</p>
                    ))}
                    {sourceLoading ? (
                      <p className="review-empty">Đang tải nguồn câu hỏi...</p>
                    ) : sourceItems.length === 0 ? (
                      <p className="review-empty">Không có citation nguồn cho câu hỏi này.</p>
                    ) : (
                      <>
                        <div className="source-list">
                          {sourceItems.map((source, index) => (
                            <button
                              type="button"
                              key={source.chunk_id || index}
                              className={`source-card ${activeSource === source ? 'source-card--active' : ''}`}
                              onClick={() => openSource(source, index)}
                            >
                              <span>Citation #{source.citation_order}</span>
                              <b>{pageRangeLabel(source.page_range)}</b>
                              <small>Chunk {shortId(source.chunk_id)} · Hash {shortId(source.chunk_content_hash)}</small>
                              {source.is_current_chunk_set === false && <em>Nguồn cũ</em>}
                            </button>
                          ))}
                        </div>

                        {activeSource && (
                          <div className="source-detail">
                            <div className="source-meta-grid">
                              <span>Chunk ID <b>{activeSource.chunk_id || '--'}</b></span>
                              <span>Chunk set <b>{shortId(activeSource.chunk_set_id)}</b></span>
                              <span>Hiện hành <b>{activeSource.is_current_chunk_set === false ? 'Không' : 'Có'}</b></span>
                              <span>Content hash <b>{shortId(activeSource.current_content_hash || activeSource.chunk_content_hash)}</b></span>
                            </div>
                            {(activeSource.warnings || []).map((warning) => (
                              <p className="source-warning" key={warning}>{warning}</p>
                            ))}
                            <div className="source-page-tabs">
                              {activeSourcePages.map((pageItem) => (
                                <button
                                  type="button"
                                  key={pageItem.page_number}
                                  className={pageItem.page_number === activeSourcePage ? 'source-page-tabs__active' : ''}
                                  onClick={() => setActiveSourcePage(pageItem.page_number)}
                                >
                                  Trang {pageItem.page_number}
                                </button>
                              ))}
                            </div>
                            <div className="source-pdf">
                              {sourcePdfLoading ? (
                                <p>Đang mở PDF...</p>
                              ) : sourcePdfUrl ? (
                                <iframe src={sourcePdfUrl} title={`PDF nguồn ${sourceViewer?.document?.original_filename || ''}`} />
                              ) : (
                                <p>Không có PDF gốc khả dụng.</p>
                              )}
                            </div>
                            <SourceText source={activeSource} page={activePageRecord} />
                          </div>
                        )}
                      </>
                    )}
                  </section>

                  <section className="history-grid">
                    <div>
                      <h3>Lịch sử kiểm duyệt</h3>
                      {reviews.slice(0, 4).map((review) => (
                        <div className="history-review" key={review.id || review._id}>
                          <p><b>{REVIEW_STATUS_LABEL[review.decision] || review.decision}</b> {review.note || ''}</p>
                          {reviewIssuesOf(review).length > 0 && (
                            <div className="history-issue-list">
                              {reviewIssuesOf(review).slice(0, 3).map((issue, index) => (
                                <small className="history-issue" key={`${issue.title || issue.detail}-${index}`}>
                                  {issue.severity || 'MEDIUM'} · {issue.title || issue.detail}
                                  {issue.page_number ? ` · Trang ${issue.page_number}` : ''}
                                </small>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                      {reviews.length === 0 && <p>Chưa có lượt kiểm duyệt.</p>}
                    </div>
                    <div>
                      <h3>Mô phỏng Moodle</h3>
                      {publications.slice(0, 4).map((publication) => (
                        <p key={publication.id || publication._id}>
                          <b>{publicationStatusLabel(publication.status)}</b> {publication.moodle_question_ref_id || ''}
                        </p>
                      ))}
                      {publications.length === 0 && <p>Chưa ghi mô phỏng.</p>}
                    </div>
                  </section>
                </>
              )}
            </>
          )}
        </aside>
      </section>

      {reviewDraft && (
        <div className="review-modal-backdrop">
          <form
            className="review-modal"
            onSubmit={(event) => {
              event.preventDefault();
              submitReviewForm();
            }}
          >
            <div className="review-modal__head">
              <div>
                <span>{reviewDraft.questionCode}</span>
                <h2>{REVIEW_STATUS_LABEL[reviewDraft.decision] || reviewDraft.decision}</h2>
              </div>
              <button type="button" onClick={() => setReviewDraft(null)}>Đóng</button>
            </div>

            <section className="review-form-section">
              <h3>Checklist</h3>
              <div className="review-rubric-grid">
                {reviewDraft.checklist.map((item) => (
                  <div className="review-rubric-item" key={item.key}>
                    <label>
                      <input
                        type="checkbox"
                        checked={item.passed}
                        onChange={(event) => updateChecklistItem(item.key, { passed: event.target.checked })}
                      />
                      <span>{item.label}</span>
                    </label>
                    <input
                      value={item.note}
                      onChange={(event) => updateChecklistItem(item.key, { note: event.target.value })}
                      placeholder="Ghi chú"
                    />
                  </div>
                ))}
              </div>
            </section>

            <section className="review-form-section">
              <label className="review-form-field">
                <span>Ghi chú tổng</span>
                <textarea
                  value={reviewDraft.overallNote}
                  onChange={(event) => updateReviewDraft({ overallNote: event.target.value })}
                  rows={4}
                />
              </label>
              {reviewNeedsOverride && (
                <label className="review-form-field">
                  <span>Lý do override</span>
                  <textarea
                    value={reviewDraft.overrideReason}
                    onChange={(event) => updateReviewDraft({ overrideReason: event.target.value })}
                    rows={3}
                    required
                  />
                </label>
              )}
            </section>

            <section className="review-form-section">
              <div className="review-issue-head">
                <h3>Lỗi cần Teacher sửa</h3>
                <button type="button" onClick={addReviewIssue}>Thêm lỗi</button>
              </div>
              {reviewDraft.issues.length === 0 && (
                <p className="review-form-muted">Chưa có lỗi cần sửa.</p>
              )}
              {reviewDraft.issues.map((issue) => (
                <div className="review-issue-row" key={issue.id}>
                  <input
                    value={issue.title}
                    onChange={(event) => updateReviewIssue(issue.id, { title: event.target.value })}
                    placeholder="Tiêu đề lỗi"
                  />
                  <select
                    value={issue.severity}
                    onChange={(event) => updateReviewIssue(issue.id, { severity: event.target.value })}
                  >
                    <option value="LOW">Nhẹ</option>
                    <option value="MEDIUM">Vừa</option>
                    <option value="HIGH">Nghiêm trọng</option>
                  </select>
                  <select
                    value={issue.source_chunk_id}
                    onChange={(event) => updateReviewIssue(issue.id, { source_chunk_id: event.target.value })}
                  >
                    <option value="">Không gắn nguồn</option>
                    {sourceItems.map((source, index) => (
                      <option key={source.chunk_id || index} value={source.chunk_id || ''}>
                        Citation #{source.citation_order} · {pageRangeLabel(source.page_range)}
                      </option>
                    ))}
                  </select>
                  <input
                    type="number"
                    min="1"
                    value={issue.page_number}
                    onChange={(event) => updateReviewIssue(issue.id, { page_number: event.target.value })}
                    placeholder="Trang"
                  />
                  <textarea
                    value={issue.detail}
                    onChange={(event) => updateReviewIssue(issue.id, { detail: event.target.value })}
                    placeholder="Chi tiết"
                    rows={2}
                  />
                  <button type="button" onClick={() => removeReviewIssue(issue.id)}>Xóa</button>
                </div>
              ))}
            </section>

            {reviewFormError && <p className="review-form-error">{reviewFormError}</p>}
            <div className="review-modal__foot">
              <button type="button" onClick={() => setReviewDraft(null)}>Hủy</button>
              <button type="submit" className="detail-action-primary" disabled={busyId === selected?.id}>
                Gửi review
              </button>
            </div>
          </form>
        </div>
      )}

      {assignmentDraft && (
        <div className="review-modal-backdrop">
          <form
            className="review-modal review-modal--compact"
            onSubmit={(event) => {
              event.preventDefault();
              submitAssignmentForm();
            }}
          >
            <div className="review-modal__head">
              <div>
                <span>{assignmentDraft.question.question_code}</span>
                <h2>Gán reviewer</h2>
              </div>
              <button type="button" onClick={() => setAssignmentDraft(null)}>Đóng</button>
            </div>
            <label className="review-form-field">
              <span>Reviewer/Admin ID</span>
              <input
                value={assignmentDraft.reviewerUserId}
                onChange={(event) => setAssignmentDraft((current) => ({
                  ...current,
                  reviewerUserId: event.target.value,
                }))}
              />
            </label>
            <label className="review-form-field">
              <span>Ghi chú</span>
              <textarea
                value={assignmentDraft.note}
                onChange={(event) => setAssignmentDraft((current) => ({
                  ...current,
                  note: event.target.value,
                }))}
                rows={3}
              />
            </label>
            {assignmentError && <p className="review-form-error">{assignmentError}</p>}
            <div className="review-modal__foot">
              <button type="button" onClick={() => setAssignmentDraft(null)}>Hủy</button>
              <button type="submit" className="detail-action-primary" disabled={busyId === assignmentDraft.question.id}>
                Lưu phân công
              </button>
            </div>
          </form>
        </div>
      )}
    </main>
  );
}

export default ReviewQueuePage;
