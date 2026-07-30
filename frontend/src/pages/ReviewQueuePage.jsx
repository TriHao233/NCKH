import React, { useContext, useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  assignQuestionReview,
  autoEvaluateQuestion,
  claimQuestionReview,
  exportQuestionMoodle,
  fetchQuestionSourcePdf,
  addQuestionComment,
  getQuestion,
  getReviewDashboard,
  getQuestionSources,
  listQuestionEvaluations,
  listQuestionComments,
  listQuestionMoodlePublications,
  listQuestionReviews,
  listQuestions,
  publishQuestionToMoodle,
  releaseQuestionReview,
  reviewQuestion,
} from '../api/questions';
import { listSubjects } from '../api/catalog';
import { listReviewerOptions, listTeacherOptions } from '../api/users';
import { AuthContext } from '../context/AuthContext';
import { BLOOM_LEVELS, QUESTION_TYPES, questionTypeLabel } from '../constants/generationEnums';
import {
  DEFAULT_REVIEW_COMMENT_TEMPLATES,
  encodeSavedReviewTemplates,
  parseSavedReviewTemplates,
  reviewTemplateStorageKey,
  templatesForDecision,
} from '../utils/reviewCommentTemplates';
import '../css/ReviewQueuePage.css';

const REVIEW_STATUS_LABEL = {
  all: 'Tất cả',
  PROCESSED: 'Đã xử lý',
  PENDING: 'Chờ duyệt',
  APPROVED: 'Đã duyệt',
  NEEDS_REVISION: 'Cần sửa',
  REJECTED: 'Từ chối',
};

const QUESTION_ID_PATTERN = /^[a-f\d]{24}$/i;

function isValidQuestionId(value) {
  return typeof value === 'string' && QUESTION_ID_PATTERN.test(value);
}

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
  UNASSIGNED: 'Chưa nhận',
  ASSIGNED: 'Đã gán',
  IN_REVIEW: 'Đang xử lý',
};

const PAGE_SIZE = 20;

function queueFiltersFromSearch(search, role) {
  const params = new URLSearchParams(search);
  const defaultTab = role === 'Admin' ? 'unassigned' : 'mine';
  const requestedStatus = params.get('status');
  const requestedAssignment = params.get('assignment');
  const status = Object.prototype.hasOwnProperty.call(REVIEW_STATUS_LABEL, requestedStatus)
    ? requestedStatus
    : 'PENDING';
  const assignment = ['all', 'mine', 'UNASSIGNED', 'ASSIGNED', 'IN_REVIEW'].includes(requestedAssignment)
    ? requestedAssignment
    : (defaultTab === 'unassigned' ? 'UNASSIGNED' : 'mine');
  let tab = 'custom';
  if (status === 'PENDING' && assignment === 'mine') tab = 'mine';
  if (status === 'PENDING' && assignment === 'UNASSIGNED') tab = 'unassigned';
  if (status === 'PROCESSED' && assignment === 'all') tab = 'processed';
  return { status, assignment, tab };
}

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
    secondaryRequired: false,
    secondaryReason: '',
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

function hours(value) {
  return typeof value === 'number' ? `${value.toFixed(1)}h` : '--';
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

function canRetryEvaluation(question) {
  return question && ['ERROR', 'FAILED', 'STALE'].includes(question.evaluation_status);
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
    revision: Number(assignment.revision || 0),
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
    return mine ? 'Quyền xử lý của tôi đã hết hạn' : 'Quyền xử lý đã hết hạn';
  }
  if (assignment.status === 'IN_REVIEW') return mine ? 'Tôi đang xử lý' : 'Đang xử lý';
  if (assignment.status === 'ASSIGNED') return mine ? 'Đã gán cho tôi' : 'Đã gán';
  return ASSIGNMENT_STATUS_LABEL[assignment.status] || assignment.status || 'Chưa nhận';
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
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useContext(AuthContext);
  const initialQueueFilters = queueFiltersFromSearch(location.search, user?.role);
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState(initialQueueFilters.status);
  const [assignmentFilter, setAssignmentFilter] = useState(initialQueueFilters.assignment);
  const [activeQueueTab, setActiveQueueTab] = useState(initialQueueFilters.tab);
  const [advancedFiltersOpen, setAdvancedFiltersOpen] = useState(false);
  const [waitingFilter, setWaitingFilter] = useState('all');
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [typeFilter, setTypeFilter] = useState('all');
  const [bloomFilter, setBloomFilter] = useState('all');
  const [colorFilter, setColorFilter] = useState('all');
  const [subjectFilter, setSubjectFilter] = useState('all');
  const [chapterFilter, setChapterFilter] = useState('all');
  const [cloFilter, setCloFilter] = useState('all');
  const [evaluationStatusFilter, setEvaluationStatusFilter] = useState('all');
  const [publicationStatusFilter, setPublicationStatusFilter] = useState('all');
  const [creatorFilter, setCreatorFilter] = useState('all');
  const [minScore, setMinScore] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [catalogSubjects, setCatalogSubjects] = useState([]);
  const [catalogFilterError, setCatalogFilterError] = useState('');
  const [teacherOptions, setTeacherOptions] = useState([]);
  const [teacherFilterError, setTeacherFilterError] = useState('');
  const [reviewerOptions, setReviewerOptions] = useState([]);
  const [reviewerFilterError, setReviewerFilterError] = useState('');
  const [selected, setSelected] = useState(null);
  const [evaluations, setEvaluations] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [comments, setComments] = useState([]);
  const [commentBody, setCommentBody] = useState('');
  const [commentMentionIds, setCommentMentionIds] = useState([]);
  const [commentBusy, setCommentBusy] = useState(false);
  const [commentError, setCommentError] = useState('');
  const [publications, setPublications] = useState([]);
  const [sourceViewer, setSourceViewer] = useState(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState('');
  const [activeSourceIndex, setActiveSourceIndex] = useState(0);
  const [activeSourcePage, setActiveSourcePage] = useState(1);
  const [sourcePdf, setSourcePdf] = useState(null);
  const [sourcePdfLoading, setSourcePdfLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [actionError, setActionError] = useState('');
  const [busyId, setBusyId] = useState('');
  const [reviewDraft, setReviewDraft] = useState(null);
  const [reviewFormError, setReviewFormError] = useState('');
  const [reviewTemplates, setReviewTemplates] = useState([...DEFAULT_REVIEW_COMMENT_TEMPLATES]);
  const [templateTitle, setTemplateTitle] = useState('');
  const [assignmentDraft, setAssignmentDraft] = useState(null);
  const [assignmentError, setAssignmentError] = useState('');
  const [dashboard, setDashboard] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState('');
  const [openedDeepLinkId, setOpenedDeepLinkId] = useState('');

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
        subjectId: subjectFilter === 'all' ? undefined : subjectFilter,
        chapterId: chapterFilter === 'all' ? undefined : chapterFilter,
        cloId: cloFilter === 'all' ? undefined : cloFilter,
        minScore: Number.isFinite(numericMinScore) ? numericMinScore : undefined,
        evaluationStatus: evaluationStatusFilter === 'all' ? undefined : evaluationStatusFilter,
        publicationStatus: publicationStatusFilter === 'all' ? undefined : publicationStatusFilter,
        creatorUserId: creatorFilter === 'all' ? undefined : creatorFilter,
        search: searchTerm || undefined,
        assignmentStatus,
        assignedTo: assignmentFilter === 'mine' ? 'me' : undefined,
        waitingHoursMin: waitingFilter === 'all' ? undefined : waitingFilter,
        overdueOnly,
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

  const fetchCatalogFilters = async () => {
    setCatalogFilterError('');
    try {
      const result = await listSubjects();
      setCatalogSubjects(result || []);
    } catch (err) {
      setCatalogFilterError(err.message || 'Không tải được bộ lọc môn học');
      setCatalogSubjects([]);
    }
  };

  const fetchTeacherFilters = async () => {
    setTeacherFilterError('');
    try {
      const result = await listTeacherOptions();
      setTeacherOptions(result.items || []);
    } catch (err) {
      setTeacherFilterError(err.message || 'Không tải được bộ lọc giảng viên');
      setTeacherOptions([]);
    }
  };

  const fetchReviewerOptions = async () => {
    setReviewerFilterError('');
    try {
      const result = await listReviewerOptions();
      setReviewerOptions(result.items || []);
    } catch (err) {
      setReviewerFilterError(err.message || 'Không tải được danh sách người duyệt');
      setReviewerOptions([]);
    }
  };

  const fetchDashboard = async () => {
    setDashboardLoading(true);
    setDashboardError('');
    try {
      setDashboard(await getReviewDashboard());
    } catch (err) {
      setDashboardError(err.message || 'Không tải được tổng quan người duyệt');
      setDashboard(null);
    } finally {
      setDashboardLoading(false);
    }
  };

  const loadHistory = async (question) => {
    setSelected(question);
    setReviewDraft(null);
    setAssignmentDraft(null);
    setReviewFormError('');
    setAssignmentError('');
    setComments([]);
    setCommentBody('');
    setCommentMentionIds([]);
    setCommentError('');
    setActionError('');
    setHistoryError('');
    setHistoryLoading(true);
    setSourceLoading(true);
    setSourceError('');
    setSourceViewer(null);
    setSourcePdf(null);
    setSourcePdfLoading(false);
    setActiveSourceIndex(0);
    setActiveSourcePage(1);
    try {
      const [evaluationResult, reviewResult, publicationResult, commentResult, sourceResult] = await Promise.allSettled([
        listQuestionEvaluations(question.id),
        listQuestionReviews(question.id),
        listQuestionMoodlePublications(question.id),
        listQuestionComments(question.id),
        getQuestionSources(question.id),
      ]);

      const failedHistoryParts = [];
      if (evaluationResult.status === 'fulfilled') {
        setEvaluations(evaluationResult.value.items || []);
      } else {
        setEvaluations([]);
        failedHistoryParts.push('đánh giá AI');
      }
      if (reviewResult.status === 'fulfilled') {
        setReviews(reviewResult.value.items || []);
      } else {
        setReviews([]);
        failedHistoryParts.push('lịch sử kiểm duyệt');
      }
      if (publicationResult.status === 'fulfilled') {
        setPublications(publicationResult.value.items || []);
      } else {
        setPublications([]);
        failedHistoryParts.push('lịch sử Moodle');
      }
      if (commentResult.status === 'fulfilled') {
        setComments(commentResult.value.items || []);
      } else {
        setComments([]);
        failedHistoryParts.push('bình luận');
      }
      if (failedHistoryParts.length > 0) {
        setHistoryError(`Không tải được ${failedHistoryParts.join(', ')}. Các phần còn lại vẫn có thể sử dụng.`);
      }

      if (sourceResult.status === 'rejected') {
        setSourceError(sourceResult.reason?.message || 'Không tải được nguồn câu hỏi');
        return;
      }

      const sourceData = sourceResult.value;
      setSourceViewer(sourceData);
      const firstSource = sourceData.items?.[0];
      setActiveSourcePage(firstSourcePage(firstSource));
      setSourceLoading(false);
      if (sourceData.document?.pdf_available) {
        setSourcePdfLoading(true);
        try {
          setSourcePdf(await fetchQuestionSourcePdf(question.id));
        } catch (err) {
          setSourceError(err.message || 'Không mở được PDF nguồn');
        } finally {
          setSourcePdfLoading(false);
        }
      }
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
    const next = queueFiltersFromSearch(location.search, user?.role);
    setStatusFilter(next.status);
    setAssignmentFilter(next.assignment);
    setActiveQueueTab(next.tab);
    setPage(1);
  }, [location.search, user?.role]);

  useEffect(() => {
    fetchQuestions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    page,
    statusFilter,
    assignmentFilter,
    waitingFilter,
    overdueOnly,
    typeFilter,
    bloomFilter,
    colorFilter,
    subjectFilter,
    chapterFilter,
    cloFilter,
    evaluationStatusFilter,
    publicationStatusFilter,
    creatorFilter,
    minScore,
    searchTerm,
  ]);

  useEffect(() => {
    fetchCatalogFilters();
    fetchTeacherFilters();
    fetchReviewerOptions();
    fetchDashboard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selected) return;
    const fresh = questions.find((item) => item.id === selected.id);
    if (fresh) {
      setSelected(fresh);
      return;
    }
    const linkedQuestionId = new URLSearchParams(location.search).get('questionId') || '';
    if (linkedQuestionId && selected.id === linkedQuestionId) return;
    setSelected(null);
    setEvaluations([]);
    setReviews([]);
    setComments([]);
    setCommentBody('');
    setCommentMentionIds([]);
    setCommentError('');
    setPublications([]);
    setSourceViewer(null);
    setSourceError('');
    setSourcePdf(null);
  }, [location.search, questions, selected]);

  useEffect(() => {
    const questionId = new URLSearchParams(location.search).get('questionId') || '';
    if (!questionId) {
      setOpenedDeepLinkId('');
      return;
    }
    if (openedDeepLinkId === questionId) return;
    if (!isValidQuestionId(questionId)) {
      const params = new URLSearchParams(location.search);
      params.delete('questionId');
      navigate(
        {
          pathname: location.pathname,
          search: params.toString() ? `?${params.toString()}` : '',
        },
        { replace: true },
      );
      setOpenedDeepLinkId('');
      setError('Liên kết câu hỏi không hợp lệ.');
      return;
    }
    const openLinkedQuestion = async () => {
      try {
        const localQuestion = questions.find((question) => question.id === questionId);
        const question = localQuestion || await getQuestion(questionId);
        await loadHistory(question);
        setOpenedDeepLinkId(questionId);
      } catch (err) {
        setError('Không mở được câu hỏi từ liên kết. Câu hỏi có thể đã bị xóa hoặc bạn không có quyền xem.');
        setOpenedDeepLinkId(questionId);
      }
    };
    openLinkedQuestion();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, location.search, navigate, questions, openedDeepLinkId]);

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

  useEffect(() => {
    const saved = parseSavedReviewTemplates(
      localStorage.getItem(reviewTemplateStorageKey(user)),
    );
    setReviewTemplates([...DEFAULT_REVIEW_COMMENT_TEMPLATES, ...saved]);
  }, [user?.email, user?.id, user?.uid]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const pageEnd = Math.min(page * PAGE_SIZE, total);

  const updateFilter = (setter) => (value) => {
    setter(value);
    setPage(1);
  };

  const applyQueueTab = (tab) => {
    setActiveQueueTab(tab);
    setPage(1);
    if (tab === 'mine') {
      setStatusFilter('PENDING');
      setAssignmentFilter('mine');
      return;
    }
    if (tab === 'unassigned') {
      setStatusFilter('PENDING');
      setAssignmentFilter('UNASSIGNED');
      return;
    }
    setStatusFilter('PROCESSED');
    setAssignmentFilter('all');
  };

  const updateQueueFilter = (setter) => (value) => {
    setActiveQueueTab('custom');
    updateFilter(setter)(value);
  };

  const updateSubjectFilter = (value) => {
    setSubjectFilter(value);
    setChapterFilter('all');
    setCloFilter('all');
    setPage(1);
  };

  const resetAdvancedFilters = () => {
    setWaitingFilter('all');
    setOverdueOnly(false);
    setTypeFilter('all');
    setBloomFilter('all');
    setColorFilter('all');
    setSubjectFilter('all');
    setChapterFilter('all');
    setCloFilter('all');
    setEvaluationStatusFilter('all');
    setPublicationStatusFilter('all');
    setCreatorFilter('all');
    setMinScore('');
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
      setActionError('Bạn cần nhận câu hỏi và giữ quyền xử lý còn hiệu lực trước khi kiểm duyệt.');
      return;
    }
    setActionError('');
    setReviewFormError('');
    setReviewDraft(loadReviewDraft(question, decision));
  };

  const updateReviewDraft = (updates) => {
    setReviewDraft((current) => ({ ...current, ...updates }));
  };

  const persistReviewTemplates = (customTemplates) => {
    const normalized = customTemplates.slice(0, 20);
    localStorage.setItem(
      reviewTemplateStorageKey(user),
      encodeSavedReviewTemplates(normalized),
    );
    setReviewTemplates([...DEFAULT_REVIEW_COMMENT_TEMPLATES, ...normalized]);
  };

  const applyReviewTemplate = (template) => {
    const currentNote = (reviewDraft?.overallNote || '').trim();
    updateReviewDraft({
      overallNote: currentNote ? `${currentNote}\n${template.body}` : template.body,
    });
    setReviewFormError('');
  };

  const saveCurrentReviewTemplate = () => {
    const body = (reviewDraft?.overallNote || '').trim();
    if (!body) {
      setReviewFormError('Cần có ghi chú tổng trước khi lưu mẫu.');
      return;
    }
    const title = templateTitle.trim() || body.split('\n')[0].slice(0, 60);
    const customTemplates = reviewTemplates.filter((template) => !template.built_in);
    persistReviewTemplates([
      {
        id: `tpl-${Date.now()}`,
        title,
        body,
        decision: reviewDraft.decision,
        updated_at: new Date().toISOString(),
      },
      ...customTemplates,
    ]);
    setTemplateTitle('');
    setReviewFormError('');
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
    const [items] = await Promise.all([fetchQuestions(), fetchDashboard()]);
    const fresh = items.find((item) => item.id === question.id);
    if (fresh) {
      await loadHistory(fresh);
    }
  };

  const claimReview = async (question) => {
    setBusyId(question.id);
    setActionError('');
    try {
      const claimedQuestion = await claimQuestionReview(question.id);
      setActiveQueueTab('mine');
      setStatusFilter('PENDING');
      setAssignmentFilter('mine');
      setPage(1);
      await Promise.all([loadHistory(claimedQuestion), fetchDashboard()]);
    } catch (err) {
      setActionError(`Không thể bắt đầu duyệt: ${err.message}`);
    } finally {
      setBusyId('');
    }
  };

  const releaseReview = async (question) => {
    setBusyId(question.id);
    setActionError('');
    try {
      await releaseQuestionReview(question.id);
      await refreshAfterAction(question);
    } catch (err) {
      setActionError(`Không thể trả câu: ${err.message}`);
    } finally {
      setBusyId('');
    }
  };

  const openAssignmentForm = (question, { unassign = false } = {}) => {
    const assignment = assignmentOf(question);
    setAssignmentError('');
    setAssignmentDraft({
      question,
      reviewerUserId: unassign ? '' : assignment.reviewer_user_id,
      note: unassign ? 'Bỏ phân công kiểm duyệt' : '',
      expectedRevision: assignment.revision,
      activeLock: assignment.status === 'IN_REVIEW' && !isReviewLockExpired(assignment),
      force: false,
    });
  };

  const submitAssignmentForm = async () => {
    if (!assignmentDraft?.question) return;
    const question = assignmentDraft.question;
    const reviewerId = assignmentDraft.reviewerUserId.trim();
    if (assignmentDraft.activeLock && !assignmentDraft.force) {
      setAssignmentError('Câu hỏi đang được xử lý. Hãy xác nhận ghi đè và nêu rõ lý do.');
      return;
    }
    if (assignmentDraft.force && !assignmentDraft.note.trim()) {
      setAssignmentError('Cần ghi rõ lý do khi ghi đè phân công đang xử lý.');
      return;
    }
    setBusyId(question.id);
    setAssignmentError('');
    try {
      await assignQuestionReview(question.id, {
        reviewer_user_id: reviewerId || null,
        note: assignmentDraft.note.trim(),
        expected_revision: assignmentDraft.expectedRevision,
        force: assignmentDraft.force,
      });
      setAssignmentDraft(null);
      await refreshAfterAction(question);
    } catch (err) {
      setAssignmentError(err.message || 'Phân công kiểm duyệt thất bại');
    } finally {
      setBusyId('');
    }
  };

  const unassignReview = (question) => {
    openAssignmentForm(question, { unassign: true });
  };

  const toggleCommentMention = (userId) => {
    setCommentMentionIds((current) => (
      current.includes(userId)
        ? current.filter((id) => id !== userId)
        : [...current, userId]
    ));
  };

  const submitComment = async (event) => {
    event.preventDefault();
    if (!selected) return;
    const body = commentBody.trim();
    if (!body) {
      setCommentError('Vui lòng nhập nội dung bình luận.');
      return;
    }
    setCommentBusy(true);
    setCommentError('');
    try {
      await addQuestionComment(selected.id, {
        body,
        mention_user_ids: commentMentionIds,
      });
      const result = await listQuestionComments(selected.id);
      setComments(result.items || []);
      setCommentBody('');
      setCommentMentionIds([]);
    } catch (err) {
      setCommentError(err.message || 'Không gửi được bình luận');
    } finally {
      setCommentBusy(false);
    }
  };

  const runEvaluation = async (question) => {
    setBusyId(question.id);
    setActionError('');
    try {
      await autoEvaluateQuestion(question.id, {
        expected_version: question.current_version,
        fallback_to_heuristic: false,
      });
      await refreshAfterAction(question);
    } catch (err) {
      setActionError(`Không thể thử lại đánh giá AI: ${err.message}`);
    } finally {
      setBusyId('');
    }
  };

  const submitReviewForm = async () => {
    if (!selected || !reviewDraft) return;
    if (!canReviewQuestion(selected)) {
      setReviewFormError('Bạn cần nhận câu hỏi và giữ quyền xử lý còn hiệu lực trước khi kiểm duyệt.');
      return;
    }
    const revisionIssues = compactIssues(reviewDraft.issues);
    const overallNote = reviewDraft.overallNote.trim();
    const adminDirectReview = (
      user?.role === 'Admin'
      && !(
        selectedAssignment.status === 'IN_REVIEW'
        && isAssignmentMine(selected, user)
        && !isReviewLockExpired(selectedAssignment)
      )
    );
    const needsOverride = reviewDraft.decision === 'APPROVED' && selected.evaluation_status !== 'PASSED';
    if (adminDirectReview && !overallNote) {
      setReviewFormError('Admin duyệt thay Reviewer phải ghi rõ lý do trong ghi chú tổng.');
      return;
    }
    if (needsOverride && !reviewDraft.overrideReason.trim()) {
      setReviewFormError('Cần ghi lý do override khi duyệt câu chưa đạt AI.');
      return;
    }
    if (reviewDraft.decision === 'REJECTED' && !overallNote && revisionIssues.length === 0) {
      setReviewFormError('Cần ghi lý do khi từ chối câu hỏi.');
      return;
    }
    if (reviewDraft.decision === 'NEEDS_REVISION' && revisionIssues.length === 0) {
      setReviewFormError('Cần thêm ít nhất một lỗi để giảng viên sửa.');
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
    if (reviewDraft.decision === 'APPROVED' && reviewDraft.secondaryRequired) {
      payload.secondary_required = true;
      payload.secondary_reason = reviewDraft.secondaryReason || overallNote;
    }
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
    setActionError('');
    try {
      await publishQuestionToMoodle(question.id, {
        expected_version: question.current_version,
        export_format: 'BOTH',
        mock: true,
      });
      await refreshAfterAction(question);
    } catch (err) {
      setActionError(`Không thể ghi mô phỏng Moodle: ${err.message}`);
    } finally {
      setBusyId('');
    }
  };

  const exportMoodle = async (question, format) => {
    setBusyId(question.id);
    setActionError('');
    try {
      const content = await exportQuestionMoodle(question.id, format);
      downloadMoodleExport(question, format, content);
    } catch (err) {
      setActionError(`Không thể xuất ${format.toUpperCase()}: ${err.message}`);
    } finally {
      setBusyId('');
    }
  };

  const latestEvaluation = evaluations[0];
  const dashboardWorkload = dashboard?.workload || {};
  const dashboardPerformance = dashboard?.performance || {};
  const dashboardDecisions = dashboard?.decisions || {};
  const dashboardSubjects = dashboard?.subjects || [];
  const dashboardCalibration = dashboard?.calibration || {};
  const mentionOptions = useMemo(() => {
    const map = new Map();
    [...teacherOptions, ...reviewerOptions].forEach((option) => {
      if (option?.id) map.set(option.id, option);
    });
    return Array.from(map.values());
  }, [teacherOptions, reviewerOptions]);
  const processedCount = (
    (dashboardDecisions.APPROVED || 0)
    + (dashboardDecisions.NEEDS_REVISION || 0)
    + (dashboardDecisions.REJECTED || 0)
  );
  const advancedFilterCount = [
    waitingFilter !== 'all',
    overdueOnly,
    typeFilter !== 'all',
    bloomFilter !== 'all',
    colorFilter !== 'all',
    subjectFilter !== 'all',
    chapterFilter !== 'all',
    cloFilter !== 'all',
    evaluationStatusFilter !== 'all',
    publicationStatusFilter !== 'all',
    creatorFilter !== 'all',
    minScore !== '',
  ].filter(Boolean).length;
  const latestEvidence = latestEvaluation?.evidence || {};
  const latestScores = latestEvaluation?.scores || {};
  const latestWeights = latestEvaluation?.policy?.weights || {};
  const qualitySummary = selected?.quality_summary || {};
  const overallScore = latestScores.overall ?? qualitySummary.overall_score;
  const evaluationColor = latestEvaluation?.color || qualitySummary.color;
  const latestModel = latestEvaluation?.evaluator_model || {};
  const selectedAssignment = assignmentOf(selected);
  const isAdminDirectReview = (
    user?.role === 'Admin'
    && !(
      selectedAssignment.status === 'IN_REVIEW'
      && isAssignmentMine(selected, user)
      && !isReviewLockExpired(selectedAssignment)
    )
  );
  const selectedCatalogSubject = catalogSubjects.find((subject) => subject.id === subjectFilter);
  const chapterFilterOptions = selectedCatalogSubject?.chapters || [];
  const cloFilterOptions = selectedCatalogSubject?.learning_outcomes || [];
  const sourceItems = sourceViewer?.items || [];
  const activeSource = sourceItems[activeSourceIndex] || sourceItems[0] || null;
  const activeSourcePages = activeSource?.pages || [];
  const activePageRecord = activeSourcePages.find((pageItem) => (
    pageItem.page_number === activeSourcePage
  )) || activeSourcePages[0] || null;
  const pdfPage = activeSourcePage || activePageRecord?.page_number || 1;
  const sourcePdfUrl = sourcePdf?.url ? `${sourcePdf.url}#page=${pdfPage}` : '';
  const reviewNeedsOverride = reviewDraft?.decision === 'APPROVED' && selected?.evaluation_status !== 'PASSED';
  const availableReviewTemplates = reviewDraft
    ? templatesForDecision(reviewTemplates, reviewDraft.decision)
    : [];

  return (
    <main className="review-page">
      <section className="review-toolbar">
        <div className="review-toolbar__title">
          <span>Hàng đợi kiểm duyệt</span>
          <h1>Kiểm duyệt câu hỏi</h1>
        </div>
      </section>

      <section className="review-dashboard" aria-label="Tổng quan công việc kiểm duyệt">
        <div className="review-dashboard__group">
          <div className="review-dashboard__head">
            <span>Khối lượng xử lý</span>
            <b>{dashboardLoading ? 'Đang tải' : `${dashboardWorkload.pending || 0} câu chờ`}</b>
          </div>
          <div className="review-dashboard__metrics">
            <div>
              <b>{dashboardWorkload.unassigned || 0}</b>
              <span>Chưa nhận</span>
            </div>
            <div>
              <b>{dashboardWorkload.assigned || 0}</b>
              <span>Đã gán</span>
            </div>
            <div>
              <b>{dashboardWorkload.in_review || 0}</b>
              <span>Đang xử lý</span>
            </div>
            <div>
              <b>{dashboardWorkload.lock_expired || 0}</b>
              <span>Quá hạn giữ câu</span>
            </div>
            <div>
              <b>{dashboardWorkload.mine || 0}</b>
              <span>Của tôi</span>
            </div>
          </div>
        </div>

        <div className="review-dashboard__group review-dashboard__group--performance">
          <div className="review-dashboard__head">
            <span>30 ngày gần nhất</span>
            <b>{dashboardPerformance.reviews_30d || 0} lượt kiểm duyệt</b>
          </div>
          <div className="review-dashboard__metrics">
            <div>
              <b>{dashboardPerformance.reviews_7d || 0}</b>
              <span>7 ngày</span>
            </div>
            <div>
              <b>{percent(dashboardPerformance.approval_rate)}</b>
              <span>Tỷ lệ duyệt</span>
            </div>
            <div>
              <b>{dashboardPerformance.override_count || 0}</b>
              <span>Override AI</span>
            </div>
            <div>
              <b>{hours(dashboardPerformance.average_review_hours)}</b>
              <span>TB xử lý</span>
            </div>
            <div>
              <b>{dashboardPerformance.revision_issues || 0}</b>
              <span>Lỗi cần sửa</span>
            </div>
          </div>
        </div>

        <div className="review-dashboard__group review-dashboard__group--calibration">
          <div className="review-dashboard__head">
            <span>Calibration AI</span>
            <b>{percent(dashboardCalibration.agreement_rate)}</b>
          </div>
          <div className="review-dashboard__metrics">
            <div>
              <b>{dashboardCalibration.sample_size || 0}</b>
              <span>Mẫu so sánh</span>
            </div>
            <div>
              <b>{dashboardCalibration.disagreements || 0}</b>
              <span>Lệch AI-human</span>
            </div>
            <div>
              <b>{dashboardCalibration.ai_failed_but_approved || 0}</b>
              <span>AI rớt, human duyệt</span>
            </div>
            <div>
              <b>{dashboardCalibration.ai_passed_but_not_approved || 0}</b>
              <span>AI đạt, human giữ lại</span>
            </div>
          </div>
        </div>

        <div className="review-dashboard__group review-dashboard__group--subjects">
          <div className="review-dashboard__head">
            <span>Theo môn</span>
            <b>{dashboardDecisions.APPROVED || 0} duyệt</b>
          </div>
          <div className="review-subject-bars">
            {dashboardSubjects.slice(0, 4).map((subject) => (
              <div className="review-subject-bar" key={subject.subject_id || subject.label}>
                <span>{subject.label}</span>
                <b>{subject.reviewed}</b>
              </div>
            ))}
            {dashboardSubjects.length === 0 && (
              <p>{dashboardLoading ? 'Đang tính theo môn...' : 'Chưa có lượt kiểm duyệt theo môn.'}</p>
            )}
          </div>
        </div>
      </section>
      {dashboardError && <p className="review-error review-error--dashboard">{dashboardError}</p>}

      <section className="review-queue-tabs" aria-label="Luồng công việc kiểm duyệt">
        <button
          type="button"
          className={activeQueueTab === 'mine' ? 'review-queue-tab--active' : ''}
          onClick={() => applyQueueTab('mine')}
        >
          <b>{dashboardWorkload.mine || 0}</b>
          <span>Cần tôi xử lý</span>
        </button>
        <button
          type="button"
          className={activeQueueTab === 'unassigned' ? 'review-queue-tab--active' : ''}
          onClick={() => applyQueueTab('unassigned')}
        >
          <b>{dashboardWorkload.unassigned || 0}</b>
          <span>Chưa có người nhận</span>
        </button>
        <button
          type="button"
          className={activeQueueTab === 'processed' ? 'review-queue-tab--active' : ''}
          onClick={() => applyQueueTab('processed')}
        >
          <b>{processedCount}</b>
          <span>Đã xử lý</span>
        </button>
      </section>

      <section className="review-layout">
        <div className="review-list-panel">
          <div className="review-filter-bar">
            <input
              aria-label="Tìm câu hỏi"
              placeholder="Tìm mã hoặc nội dung..."
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
            />
            <button
              type="button"
              aria-expanded={advancedFiltersOpen}
              onClick={() => setAdvancedFiltersOpen((current) => !current)}
            >
              Bộ lọc nâng cao{advancedFilterCount > 0 ? ` (${advancedFilterCount})` : ''}
            </button>
          </div>

          {advancedFiltersOpen && (
            <div className="review-filters">
            <select value={statusFilter} onChange={(event) => updateQueueFilter(setStatusFilter)(event.target.value)}>
              {Object.entries(REVIEW_STATUS_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <select value={assignmentFilter} onChange={(event) => updateQueueFilter(setAssignmentFilter)(event.target.value)}>
              {Object.entries(ASSIGNMENT_STATUS_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <select value={waitingFilter} onChange={(event) => updateFilter(setWaitingFilter)(event.target.value)}>
              <option value="all">Mọi thời gian chờ</option>
              <option value="24">Chờ từ 24h</option>
              <option value="72">Chờ từ 72h</option>
              <option value="168">Chờ từ 7 ngày</option>
            </select>
            <label className="review-filter-toggle">
              <input
                type="checkbox"
                checked={overdueOnly}
                onChange={(event) => updateFilter(setOverdueOnly)(event.target.checked)}
              />
              Quá hạn giữ câu
            </label>
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
            <select value={subjectFilter} onChange={(event) => updateSubjectFilter(event.target.value)}>
              <option value="all">Mọi môn học</option>
              {catalogSubjects.map((subject) => (
                <option key={subject.id} value={subject.id}>
                  {subject.subject_code} - {subject.subject_name}
                </option>
              ))}
            </select>
            <select
              value={chapterFilter}
              onChange={(event) => updateFilter(setChapterFilter)(event.target.value)}
              disabled={subjectFilter === 'all'}
            >
              <option value="all">Mọi chương</option>
              {chapterFilterOptions.map((chapter) => (
                <option key={childId(chapter)} value={childId(chapter)}>
                  {chapter.chapter_code} - {chapter.chapter_name}
                </option>
              ))}
            </select>
            <select
              value={cloFilter}
              onChange={(event) => updateFilter(setCloFilter)(event.target.value)}
              disabled={subjectFilter === 'all'}
            >
              <option value="all">Mọi CLO</option>
              {cloFilterOptions.map((clo) => (
                <option key={childId(clo)} value={childId(clo)}>
                  {clo.clo_code}
                </option>
              ))}
            </select>
            <select value={evaluationStatusFilter} onChange={(event) => updateFilter(setEvaluationStatusFilter)(event.target.value)}>
              <option value="all">Mọi trạng thái AI</option>
              {Object.entries(EVALUATION_STATUS_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <select value={publicationStatusFilter} onChange={(event) => updateFilter(setPublicationStatusFilter)(event.target.value)}>
              <option value="all">Mọi trạng thái Moodle</option>
              {Object.entries(PUBLICATION_STATUS_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <select value={creatorFilter} onChange={(event) => updateFilter(setCreatorFilter)(event.target.value)}>
              <option value="all">Mọi giảng viên</option>
              {teacherOptions.map((teacher) => (
                <option key={teacher.id} value={teacher.id}>
                  {teacher.display_name || teacher.email}
                </option>
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
              <button type="button" className="review-filter-reset" onClick={resetAdvancedFilters}>
                Xóa bộ lọc nâng cao
              </button>
            </div>
          )}

          {catalogFilterError && <p className="review-error review-error--filters">{catalogFilterError}</p>}
          {teacherFilterError && <p className="review-error review-error--filters">{teacherFilterError}</p>}
          {reviewerFilterError && <p className="review-error review-error--filters">{reviewerFilterError}</p>}
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
                  <span>Người duyệt</span>
                  <b>{selectedAssignment.reviewer_user_id || '--'}</b>
                </div>
                <div>
                  <span>Nhận lúc</span>
                  <b>{formatDate(selectedAssignment.claimed_at || selectedAssignment.assigned_at)}</b>
                </div>
                <div>
                  <span>Hết hạn giữ câu</span>
                  <b>{formatDate(selectedAssignment.lock_expires_at)}</b>
                </div>
                <div>
                  <span>Duyệt lần 2</span>
                  <b>{selected.secondary_review?.status || 'NOT_REQUIRED'}</b>
                </div>
              </section>
              <div className="detail-actions">
                {user?.role !== 'Admin' && (
                  <button
                    type="button"
                    className="detail-action-primary"
                    disabled={busyId === selected.id || !canClaimQuestion(selected)}
                    onClick={() => claimReview(selected)}
                  >
                    {selectedAssignment.status === 'IN_REVIEW' && isAssignmentMine(selected, user)
                      ? 'Gia hạn phiên duyệt'
                      : 'Bắt đầu duyệt'}
                  </button>
                )}
                {user?.role !== 'Admin' && canReleaseQuestion(selected) && (
                  <button type="button" disabled={busyId === selected.id} onClick={() => releaseReview(selected)}>
                    Trả lại hàng đợi
                  </button>
                )}
                {user?.role === 'Admin' && (
                  <button
                    type="button"
                    className="detail-action-primary"
                    disabled={busyId === selected.id || selected.review_status !== 'PENDING'}
                    onClick={() => openAssignmentForm(selected)}
                  >
                    Phân công
                  </button>
                )}
                {user?.role === 'Admin' && canReleaseQuestion(selected) && (
                  <button type="button" disabled={busyId === selected.id || !canReleaseQuestion(selected)} onClick={() => unassignReview(selected)}>
                    Bỏ gán
                  </button>
                )}
                {canRetryEvaluation(selected) && (
                  <button type="button" disabled={busyId === selected.id} onClick={() => runEvaluation(selected)}>
                    Thử lại đánh giá AI
                  </button>
                )}
                <button
                  type="button"
                  className={user?.role === 'Admin' ? '' : 'detail-action-primary'}
                  disabled={busyId === selected.id || isEvaluationBusy(selected) || !canReviewQuestion(selected)}
                  onClick={() => openReviewForm(selected, 'APPROVED')}
                >
                  {user?.role === 'Admin' ? 'Duyệt thay Reviewer' : 'Duyệt'}
                </button>
                <button type="button" disabled={busyId === selected.id || !canReviewQuestion(selected)} onClick={() => openReviewForm(selected, 'NEEDS_REVISION')}>Cần sửa</button>
                <button type="button" disabled={busyId === selected.id || !canReviewQuestion(selected)} onClick={() => openReviewForm(selected, 'REJECTED')}>Từ chối</button>
              </div>
              {actionError && <p className="review-error review-error--action">{actionError}</p>}

              {selected.review_status === 'APPROVED' && (
                <details className="review-secondary-actions">
                  <summary>Xuất bản và xuất file</summary>
                  <div>
                    <button
                      type="button"
                      disabled={busyId === selected.id || selected.publication_status === 'PUBLISHED'}
                      onClick={() => publish(selected)}
                    >
                      Ghi mô phỏng Moodle
                    </button>
                    <button type="button" disabled={busyId === selected.id} onClick={() => exportMoodle(selected, 'gift')}>
                      Tải GIFT
                    </button>
                    <button type="button" disabled={busyId === selected.id} onClick={() => exportMoodle(selected, 'xml')}>
                      Tải XML
                    </button>
                  </div>
                </details>
              )}

              {historyLoading ? (
                <p className="review-empty">Đang tải minh chứng...</p>
              ) : (
                <>
                  {historyError && <p className="review-error review-error--history">{historyError}</p>}
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

                  <section className="comment-thread">
                    <div className="comment-thread__head">
                      <h3>Trao đổi</h3>
                      <span>{comments.length} bình luận</span>
                    </div>
                    <div className="comment-list">
                      {comments.slice(-6).map((comment) => (
                        <div className="comment-item" key={comment.id || comment._id}>
                          <b>{comment.author_role || 'User'}</b>
                          <p>{comment.body}</p>
                          <small>{formatDate(comment.created_at)}</small>
                        </div>
                      ))}
                      {comments.length === 0 && <p className="review-empty">Chưa có trao đổi.</p>}
                    </div>
                    <form className="comment-form" onSubmit={submitComment}>
                      <textarea
                        value={commentBody}
                        onChange={(event) => setCommentBody(event.target.value)}
                        rows={3}
                        placeholder="Viết bình luận hoặc phản hồi..."
                      />
                      <div className="comment-mentions">
                        {mentionOptions.slice(0, 8).map((option) => (
                          <label key={option.id}>
                            <input
                              type="checkbox"
                              checked={commentMentionIds.includes(option.id)}
                              onChange={() => toggleCommentMention(option.id)}
                            />
                            {option.display_name || option.email}
                          </label>
                        ))}
                      </div>
                      {commentError && <p className="review-form-error">{commentError}</p>}
                      <button type="submit" disabled={commentBusy}>
                        {commentBusy ? 'Đang gửi...' : 'Gửi bình luận'}
                      </button>
                    </form>
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
              <div className="review-template-panel">
                <div className="review-template-head">
                  <h3>Mẫu nhận xét</h3>
                  <div>
                    <input
                      value={templateTitle}
                      onChange={(event) => setTemplateTitle(event.target.value)}
                      placeholder="Tên mẫu"
                    />
                    <button type="button" onClick={saveCurrentReviewTemplate}>
                      Lưu mẫu
                    </button>
                  </div>
                </div>
                <div className="review-template-list">
                  {availableReviewTemplates.map((template) => (
                    <button
                      type="button"
                      key={template.id}
                      onClick={() => applyReviewTemplate(template)}
                    >
                      <b>{template.title}</b>
                      <span>{template.body}</span>
                    </button>
                  ))}
                </div>
              </div>
              <label className="review-form-field">
                <span>
                  Ghi chú tổng
                  {isAdminDirectReview ? ' (bắt buộc khi duyệt thay Reviewer)' : ''}
                </span>
                <textarea
                  value={reviewDraft.overallNote}
                  onChange={(event) => updateReviewDraft({ overallNote: event.target.value })}
                  rows={4}
                  required={isAdminDirectReview}
                />
              </label>
              {reviewDraft.decision === 'APPROVED' && (
                <div className="secondary-review-box">
                  <label>
                    <input
                      type="checkbox"
                      checked={Boolean(reviewDraft.secondaryRequired)}
                      onChange={(event) => updateReviewDraft({ secondaryRequired: event.target.checked })}
                    />
                    Cần duyệt lần 2 trước khi phê duyệt chính thức
                  </label>
                  {reviewDraft.secondaryRequired && (
                    <textarea
                      value={reviewDraft.secondaryReason}
                      onChange={(event) => updateReviewDraft({ secondaryReason: event.target.value })}
                      rows={2}
                      placeholder="Lý do cần người thứ hai kiểm duyệt"
                    />
                  )}
                </div>
              )}
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
                <h3>Lỗi cần giảng viên sửa</h3>
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
                Lưu kết quả kiểm duyệt
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
                <h2>Gán người duyệt</h2>
              </div>
              <button type="button" onClick={() => setAssignmentDraft(null)}>Đóng</button>
            </div>
            <label className="review-form-field">
              <span>Người duyệt/quản trị viên đang hoạt động</span>
              <select
                value={assignmentDraft.reviewerUserId}
                onChange={(event) => setAssignmentDraft((current) => ({
                  ...current,
                  reviewerUserId: event.target.value,
                }))}
              >
                <option value="">Bỏ gán người duyệt</option>
                {reviewerOptions.map((reviewer) => (
                  <option key={reviewer.id} value={reviewer.id}>
                    {reviewer.display_name || reviewer.email || reviewer.id}
                  </option>
                ))}
                {assignmentDraft.reviewerUserId
                  && !reviewerOptions.some((reviewer) => reviewer.id === assignmentDraft.reviewerUserId) && (
                  <option value={assignmentDraft.reviewerUserId}>
                    ID hiện tại: {assignmentDraft.reviewerUserId}
                  </option>
                )}
              </select>
            </label>
            {assignmentDraft.activeLock && (
              <>
                <p className="review-assignment-warning">
                  Câu hỏi đang được một Reviewer xử lý. Ghi đè sẽ thu hồi quyền nộp duyệt của người đó.
                </p>
                <label className="review-filter-toggle">
                  <input
                    type="checkbox"
                    checked={assignmentDraft.force}
                    onChange={(event) => setAssignmentDraft((current) => ({
                      ...current,
                      force: event.target.checked,
                    }))}
                  />
                  Xác nhận ghi đè phân công đang xử lý
                </label>
              </>
            )}
            <label className="review-form-field">
              <span>{assignmentDraft.force ? 'Lý do ghi đè (bắt buộc)' : 'Ghi chú'}</span>
              <textarea
                value={assignmentDraft.note}
                onChange={(event) => setAssignmentDraft((current) => ({
                  ...current,
                  note: event.target.value,
                }))}
                rows={3}
                required={assignmentDraft.force}
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
