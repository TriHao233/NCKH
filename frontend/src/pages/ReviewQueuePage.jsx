import React, { useContext, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  assignQuestionReview,
  autoEvaluateQuestion,
  claimQuestionReview,
  exportQuestionMoodle,
  fetchQuestionSourcePdf,
  addQuestionComment,
  deleteQuestionReviewDraft,
  deleteQuestionComment,
  getQuestion,
  getQuestionReviewDraft,
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
  saveQuestionReviewDraft,
  updateQuestionComment,
} from '../api/questions';
import { listAvailableAiModels, listSubjects } from '../api/catalog';
import { listReviewerOptions, listTeacherOptions } from '../api/users';
import { AuthContext } from '../context/AuthContext';
import { permissionsForUser } from '../auth/permissions';
import { BLOOM_LEVELS, QUESTION_TYPES, difficultyLabel, questionTypeLabel } from '../constants/generationEnums';
import {
  DEFAULT_REVIEW_COMMENT_TEMPLATES,
  encodeSavedReviewTemplates,
  parseSavedReviewTemplates,
  reviewTemplateStorageKey,
  templatesForDecision,
} from '../utils/reviewCommentTemplates';
import {
  answerGuardrailInsights,
  evaluationContractInsights,
  evaluationInsights,
  metadataGuardrailInsights,
  mergeAiSuggestionsIntoDraft,
} from '../utils/reviewAiSuggestions';
import '../css/ReviewQueuePage.css';

const REVIEW_STATUS_LABEL = {
  all: 'Tất cả',
  PENDING: 'Chờ duyệt',
  PROCESSED: 'Đã xử lý',
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
  QUEUED: 'Đang chờ AI đánh giá',
  PROCESSING: 'Đang được AI đánh giá',
  RUNNING: 'Đang được AI đánh giá',
  PASSED: 'AI đề xuất đạt',
  FAILED: 'AI đề xuất xem lại',
  ERROR: 'Chưa đánh giá được',
  STALE: 'Cần đánh giá lại',
};

const PUBLICATION_STATUS_LABEL = {
  NOT_PUBLISHED: 'Chưa đưa lên Moodle',
  PENDING: 'Đang đưa lên Moodle',
  PUBLISHED: 'Đã đưa lên Moodle',
  FAILED: 'Chưa đưa lên được',
};

const ASSIGNMENT_STATUS_LABEL = {
  all: 'Mọi phân công',
  mine: 'Của tôi',
  UNASSIGNED: 'Chưa nhận',
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

const REVIEW_CRITERIA = SCORE_COMPONENTS.map((item) => ({
  ...item,
  description: {
    faithfulness: 'Câu hỏi, đáp án và giải thích có căn cứ trong tài liệu nguồn.',
    contextual_relevancy: 'Câu hỏi tập trung vào nội dung quan trọng của môn học.',
    answer_relevancy: 'Đáp án đúng, rõ ràng và phù hợp với dạng câu hỏi.',
    bloom_alignment: 'Thao tác tư duy khớp cấp Bloom đã gắn.',
    clo_alignment: 'Câu hỏi thực sự đo được CLO đã chọn.',
  }[item.key],
}));

const CRITERION_RATING_LABEL = {
  PASS: 'Đạt',
  REVIEW: 'Cần xem lại',
  FAIL: 'Không đạt',
  NO_DATA: 'Không đủ dữ liệu',
};

const SECONDARY_REVIEW_STATUS_LABEL = {
  NOT_REQUIRED: 'Không yêu cầu',
  AWAITING_SECONDARY: 'Đang chờ duyệt lần hai',
  COMPLETED: 'Đã duyệt lần hai',
};

const ISSUE_SEVERITY_LABEL = {
  LOW: 'Nhẹ',
  MEDIUM: 'Vừa',
  HIGH: 'Nghiêm trọng',
};

const AI_ACTION_LABEL = {
  APPROVE: 'Có thể duyệt',
  NEEDS_REVISION: 'Nên yêu cầu sửa',
  REJECT: 'Nên từ chối',
};

const AI_SEVERITY_LABEL = {
  LOW: 'Lỗi nhẹ',
  MEDIUM: 'Lỗi vừa',
  HIGH: 'Lỗi nghiêm trọng',
};

const OPTION_VERDICT_LABEL = {
  SUPPORTED: 'Được nguồn hỗ trợ',
  CONTRADICTED: 'Mâu thuẫn với nguồn',
  NOT_IN_SOURCE: 'Không có trong nguồn',
  AMBIGUOUS: 'Chưa đủ rõ',
};

const USER_ROLE_LABEL = {
  Admin: 'Quản trị viên',
  Teacher: 'Giảng viên',
  Reviewer: 'Người duyệt',
  Student: 'Sinh viên',
  User: 'Người dùng',
};

const REVIEW_RUBRIC = [
  { key: 'source_alignment', label: 'Bám sát nguồn' },
  { key: 'answer_correctness', label: 'Đáp án đúng' },
  { key: 'bloom_clo_alignment', label: 'Đúng Bloom/CLO' },
  { key: 'language_quality', label: 'Diễn đạt rõ' },
  { key: 'moodle_readiness', label: 'Sẵn sàng Moodle' },
];

const QUESTION_TYPE_GUIDANCE = {
  dung_sai: [
    'Mệnh đề phải hoàn chỉnh và chỉ có thể hoàn toàn Đúng hoặc hoàn toàn Sai.',
    'Từ khóa trọng tâm và dữ kiện bị thay đổi phải truy ra được trong nguồn.',
    'Đáp án chuẩn hóa A = Đúng, B = Sai; giải thích nêu rõ vì sao.',
  ],
  trac_nghiem: ['Chỉ có một đáp án đúng nhất.', 'Phương án nhiễu cùng loại, hợp lý và không làm lộ đáp án.'],
  nhieu_lua_chon: ['Có ít nhất hai đáp án đúng độc lập.', 'Không có lựa chọn bao hàm làm số đáp án đúng bị mơ hồ.'],
  dien_khuyet: ['Có một đáp án xác định.', 'Không hỏi từ nối hoặc chi tiết vụn vặt.'],
  ghep_cot: ['Hai cột cùng loại và quan hệ ghép rõ ràng.', 'Không thể ghép chỉ bằng mẹo hình thức.'],
  sap_xep: ['Nguồn thực sự chứa quy trình hoặc chuỗi phụ thuộc.', 'Chỉ có một thứ tự hợp lý.'],
  tinh_huong: ['Tình huống đủ dữ kiện để ra quyết định.', 'Đáp án đòi hỏi suy luận, không chỉ nhớ định nghĩa.'],
};

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
    criteria: REVIEW_CRITERIA.map((item) => ({
      ...item,
      rating: decision === 'APPROVED' ? 'PASS' : 'REVIEW',
      note: '',
      source_chunk_id: '',
      page_number: '',
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
      criteria: REVIEW_CRITERIA.map((item) => {
        const savedItem = (parsed.criteria || []).find((entry) => entry.key === item.key);
        return savedItem
          ? { ...item, ...savedItem }
          : { ...item, rating: decision === 'APPROVED' ? 'PASS' : 'REVIEW', note: '', source_chunk_id: '', page_number: '' };
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
  return typeof value === 'number' ? `${value.toFixed(1)} giờ` : '--';
}

function formatDate(value) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--';
  return date.toLocaleString('vi-VN');
}

function textList(value) {
  const values = Array.isArray(value) ? value : (value ? [value] : []);
  return values.map((item) => String(item || '').trim()).filter(Boolean);
}

function waitingTime(value) {
  if (!value) return '--';
  const submitted = new Date(value);
  if (Number.isNaN(submitted.getTime())) return '--';
  const hoursWaiting = Math.max(0, (Date.now() - submitted.getTime()) / 3600000);
  if (hoursWaiting < 24) return `${Math.max(1, Math.floor(hoursWaiting))} giờ`;
  return `${Math.floor(hoursWaiting / 24)} ngày`;
}

function bloomDisplay(classification = {}) {
  const bloom = classification.bloom || {};
  if (!bloom.level) return 'Bloom chưa gắn';
  return `${bloom.level}. ${bloom.name || BLOOM_LEVELS.find((item) => item.level === bloom.level)?.label?.replace(/^\d+\.\s*/, '') || 'Bloom'}`;
}

function evaluationModeLabel(mode) {
  if (mode === 'local_llm') return 'AI của hệ thống';
  if (mode === 'heuristic_fallback') return 'Hệ thống đánh giá dự phòng';
  if (mode === 'heuristic') return 'Hệ thống chấm nhanh';
  return mode ? 'Hệ thống hỗ trợ' : '--';
}

function secondaryReviewStatusLabel(value) {
  return SECONDARY_REVIEW_STATUS_LABEL[value] || 'Không yêu cầu';
}

function issueSeverityLabel(value) {
  return ISSUE_SEVERITY_LABEL[value] || 'Vừa';
}

function userRoleLabel(value) {
  return USER_ROLE_LABEL[value] || 'Người dùng';
}

function qualityColorLabel(value) {
  return COLOR_LABEL[value] || 'Chưa xác định';
}

function evaluationStatusLabel(value) {
  return EVALUATION_STATUS_LABEL[value] || 'Chưa đánh giá';
}

function isEvaluationBusy(question) {
  return ['QUEUED', 'PROCESSING', 'RUNNING'].includes(question?.evaluation_status);
}

function canQueueEvaluation(question) {
  return question && !isEvaluationBusy(question) && question.evaluation_status !== 'PASSED';
}

function publicationStatusLabel(value) {
  return PUBLICATION_STATUS_LABEL[value] || 'Chưa xác định';
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
    return mine ? 'Quyền xử lý của tôi đã hết hạn' : 'Quyền xử lý đã hết hạn';
  }
  if (assignment.status === 'IN_REVIEW') return mine ? 'Tôi đang xử lý' : 'Đang xử lý';
  if (assignment.status === 'ASSIGNED') return mine ? 'Đã gán cho tôi' : 'Đã gán';
  return ASSIGNMENT_STATUS_LABEL[assignment.status] || 'Chưa nhận';
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

function questionSubjectId(question) {
  return refId(
    question?.subject_id
    || question?.classification?.subject?.id
    || question?.classification?.subject,
  );
}

function subjectOptionLabel(subject) {
  if (!subject) return '';
  const code = subject.subject_code || '';
  const name = subject.subject_name || subject.name || subject.title || '';
  return [code, name].filter(Boolean).join(' - ') || refId(subject);
}

function userOptionLabel(option) {
  return option?.display_name || option?.email || refId(option);
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
  const excerpt = source?.evidence?.quote || source?.context_excerpt || source?.chunk_text || '';
  const pageText = page?.text || source?.chunk_text || '';
  return (
    <div className="source-text">
      {excerpt && (
        <p className="source-highlight">
          <mark>{excerpt}</mark>
        </p>
      )}
      <p>{pageText || 'Chưa trích xuất được nội dung của trang này.'}</p>
    </div>
  );
}

function ReviewQueuePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useContext(AuthContext);
  const userPermissions = permissionsForUser(user);
  const canReviewQuestions = userPermissions.includes('questions.review');
  const canAssignReviews = userPermissions.includes('questions.review_assign');
  const canEvaluateQuestions = userPermissions.includes('questions.evaluate');
  const canOverrideEvaluation = userPermissions.includes('questions.review_override');
  const canPublishMoodle = userPermissions.includes('questions.publish_moodle');
  const canExportMoodle = userPermissions.includes('questions.export_moodle');
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('PENDING');
  const [assignmentFilter, setAssignmentFilter] = useState('all');
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
  const [submittedFromFilter, setSubmittedFromFilter] = useState('');
  const [submittedToFilter, setSubmittedToFilter] = useState('');
  const [sortMode, setSortMode] = useState('priority');
  const [sourcePresenceFilter, setSourcePresenceFilter] = useState('all');
  const [secondaryStatusFilter, setSecondaryStatusFilter] = useState('all');
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [catalogSubjects, setCatalogSubjects] = useState([]);
  const [catalogFilterError, setCatalogFilterError] = useState('');
  const [evaluationModels, setEvaluationModels] = useState([]);
  const [evaluationModelCode, setEvaluationModelCode] = useState('');
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
  const [editingCommentId, setEditingCommentId] = useState('');
  const [editingCommentBody, setEditingCommentBody] = useState('');
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
  const [serverReviewDraft, setServerReviewDraft] = useState(null);
  const [draftSaveState, setDraftSaveState] = useState('');
  const [reviewFormError, setReviewFormError] = useState('');
  const [reviewTemplates, setReviewTemplates] = useState([...DEFAULT_REVIEW_COMMENT_TEMPLATES]);
  const [templateTitle, setTemplateTitle] = useState('');
  const [assignmentDraft, setAssignmentDraft] = useState(null);
  const [assignmentError, setAssignmentError] = useState('');
  const [dashboard, setDashboard] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState('');
  const [openedDeepLinkId, setOpenedDeepLinkId] = useState('');
  const [workspaceView, setWorkspaceView] = useState('queue');
  const [detailView, setDetailView] = useState('question');
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);

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
        submittedFrom: submittedFromFilter || undefined,
        submittedTo: submittedToFilter || undefined,
        sortBy: sortMode,
        sourcePresence: sourcePresenceFilter === 'all' ? undefined : sourcePresenceFilter,
        secondaryStatus: secondaryStatusFilter === 'all' ? undefined : secondaryStatusFilter,
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

  const fetchEvaluationModels = async () => {
    try {
      const result = await listAvailableAiModels('QUESTION_EVALUATION');
      const items = result.items || [];
      setEvaluationModels(items);
      setEvaluationModelCode((current) => (
        items.some((item) => item.code === current)
          ? current
          : (result.default_model_code || items[0]?.code || '')
      ));
    } catch {
      setEvaluationModels([]);
      setEvaluationModelCode('');
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
    setServerReviewDraft(null);
    setDraftSaveState('');
    setDetailView('question');
    setAssignmentDraft(null);
    setReviewFormError('');
    setAssignmentError('');
    setComments([]);
    setCommentBody('');
    setCommentMentionIds([]);
    setCommentError('');
    setEditingCommentId('');
    setEditingCommentBody('');
    setHistoryLoading(true);
    setSourceLoading(true);
    setSourceError('');
    setSourceViewer(null);
    setSourcePdf(null);
    setSourcePdfLoading(false);
    setActiveSourceIndex(0);
    setActiveSourcePage(1);
    try {
      const [evaluationResult, reviewResult, publicationResult, commentResult, sourceResult, draftResult] = await Promise.all([
        listQuestionEvaluations(question.id),
        listQuestionReviews(question.id),
        listQuestionMoodlePublications(question.id),
        listQuestionComments(question.id),
        getQuestionSources(question.id),
        getQuestionReviewDraft(question.id),
      ]);
      setEvaluations(evaluationResult.items || []);
      setReviews(reviewResult.items || []);
      setPublications(publicationResult.items || []);
      setComments(commentResult.items || []);
      setSourceViewer(sourceResult);
      setServerReviewDraft(draftResult.item || null);
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
    submittedFromFilter,
    submittedToFilter,
    sortMode,
    sourcePresenceFilter,
    secondaryStatusFilter,
    searchTerm,
  ]);

  useEffect(() => {
    fetchCatalogFilters();
    fetchEvaluationModels();
    fetchTeacherFilters();
    fetchReviewerOptions();
    fetchDashboard();
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
      setError('');
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
    if (!reviewDraft?.questionId || !selected || reviewDraft.questionId !== selected.id) return undefined;
    setDraftSaveState('Đang lưu bản nháp...');
    const handle = setTimeout(async () => {
      try {
        await saveQuestionReviewDraft(selected.id, {
          expected_version: selected.current_version,
          decision: reviewDraft.decision,
          draft: reviewDraft,
        });
        setDraftSaveState('Đã lưu bản nháp');
      } catch (err) {
        setDraftSaveState(err.message || 'Chưa lưu được bản nháp');
      }
    }, 900);
    return () => clearTimeout(handle);
  }, [reviewDraft, selected]);

  useEffect(() => {
    const saved = parseSavedReviewTemplates(
      localStorage.getItem(reviewTemplateStorageKey(user)),
    );
    setReviewTemplates([...DEFAULT_REVIEW_COMMENT_TEMPLATES, ...saved]);
  }, [user]);

  const summary = useMemo(() => ({
    pending: questions.filter((item) => item.review_status === 'PENDING').length,
    mine: questions.filter((item) => isAssignmentMine(item, user)).length,
    passed: questions.filter((item) => item.evaluation_status === 'PASSED').length,
    green: questions.filter((item) => item.quality_summary?.color === 'GREEN').length,
    publishable: questions.filter((item) => item.review_status === 'APPROVED' && item.publication_status !== 'PUBLISHED').length,
  }), [questions, user]);

  const queueErrors = useMemo(() => Array.from(new Set([
    catalogFilterError,
    teacherFilterError,
    reviewerFilterError,
    error,
  ].filter(Boolean))), [catalogFilterError, teacherFilterError, reviewerFilterError, error]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const pageEnd = Math.min(page * PAGE_SIZE, total);

  const updateFilter = (setter) => (value) => {
    setter(value);
    setPage(1);
  };

  const updateSubjectFilter = (value) => {
    setSubjectFilter(value);
    setChapterFilter('all');
    setCloFilter('all');
    setPage(1);
  };

  const openSource = (source, index) => {
    setActiveSourceIndex(index);
    setActiveSourcePage(firstSourcePage(source));
  };

  const canClaimQuestion = (question) => {
    if (!canReviewQuestions || !question || question.review_status !== 'PENDING') return false;
    const assignment = assignmentOf(question);
    return (
      assignment.status === 'UNASSIGNED'
      || isAssignmentMine(question, user)
      || isReviewLockExpired(assignment)
      || canAssignReviews
    );
  };

  const canReleaseQuestion = (question) => {
    if (!question || question.review_status !== 'PENDING') return false;
    const assignment = assignmentOf(question);
    if (assignment.status === 'UNASSIGNED') return false;
    return canAssignReviews || isAssignmentMine(question, user);
  };

  const canReviewQuestion = (question) => {
    if (!canReviewQuestions || !question || question.review_status !== 'PENDING') return false;
    if (canAssignReviews) return true;
    const assignment = assignmentOf(question);
    return (
      assignment.status === 'IN_REVIEW'
      && isAssignmentMine(question, user)
      && !isReviewLockExpired(assignment)
    );
  };

  const openReviewForm = (question, decision, { aiEvaluation = null } = {}) => {
    if (!canReviewQuestion(question)) {
      alert('Bạn cần nhận câu hỏi và giữ quyền xử lý còn hiệu lực trước khi kiểm duyệt.');
      return;
    }
    setReviewFormError('');
    const localDraft = loadReviewDraft(question, decision);
    const remoteDraft = serverReviewDraft?.decision === decision && !serverReviewDraft?.is_stale
      ? serverReviewDraft.draft
      : null;
    const draft = remoteDraft ? { ...localDraft, ...remoteDraft } : localDraft;
    setReviewDraft(aiEvaluation ? mergeAiSuggestionsIntoDraft(draft, aiEvaluation) : draft);
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

  const updateCriterion = (key, updates) => {
    setReviewDraft((current) => ({
      ...current,
      criteria: current.criteria.map((item) => (
        item.key === key ? { ...item, ...updates } : item
      )),
    }));
  };

  const discardReviewDraft = async () => {
    if (!selected || !reviewDraft) return;
    await deleteQuestionReviewDraft(selected.id).catch(() => null);
    localStorage.removeItem(reviewDraftKey(selected.id, reviewDraft.decision));
    setServerReviewDraft(null);
    setReviewDraft(null);
    setDraftSaveState('');
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
    try {
      await claimQuestionReview(question.id);
      await refreshAfterAction(question);
    } catch (err) {
      alert('Nhận câu kiểm duyệt thất bại: ' + err.message);
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
      alert('Trả câu kiểm duyệt thất bại: ' + err.message);
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
      setAssignmentError(err.message || 'Phân công kiểm duyệt thất bại');
    } finally {
      setBusyId('');
    }
  };

  const unassignReview = async (question) => {
    if (!window.confirm(`Bỏ phân công kiểm duyệt cho ${question.question_code}?`)) return;
    setBusyId(question.id);
    try {
      await assignQuestionReview(question.id, {
        reviewer_user_id: null,
        note: 'Admin bỏ phân công',
      });
      await refreshAfterAction(question);
    } catch (err) {
      alert('Bỏ phân công kiểm duyệt thất bại: ' + err.message);
    } finally {
      setBusyId('');
    }
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
    try {
      await autoEvaluateQuestion(question.id, {
        expected_version: question.current_version,
        fallback_to_heuristic: false,
        ...(evaluationModelCode ? { evaluator_model_code: evaluationModelCode } : {}),
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
      setReviewFormError('Bạn cần nhận câu hỏi và giữ quyền xử lý còn hiệu lực trước khi kiểm duyệt.');
      return;
    }
    const revisionIssues = compactIssues(reviewDraft.issues);
    const overallNote = reviewDraft.overallNote.trim();
    const criterionAssessments = reviewDraft.criteria || [];
    if (criterionAssessments.length !== REVIEW_CRITERIA.length) {
      setReviewFormError('Vui lòng đánh giá đủ 5 tiêu chí AI–người duyệt.');
      return;
    }
    if (reviewDraft.decision === 'APPROVED' && criterionAssessments.some((item) => item.rating === 'FAIL')) {
      setReviewFormError('Không thể duyệt khi còn tiêu chí “Không đạt”. Hãy chọn Cần sửa hoặc ghi nhận lại tiêu chí.');
      return;
    }
    const needsOverride = reviewDraft.decision === 'APPROVED' && selected.evaluation_status !== 'PASSED';
    if (needsOverride && !canOverrideEvaluation) {
      setReviewFormError('Tài khoản chưa được cấp quyền override đánh giá AI.');
      return;
    }
    if (needsOverride && !reviewDraft.overrideReason.trim()) {
      setReviewFormError('Cần ghi lý do khi duyệt câu mà AI đề xuất xem lại.');
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
        criterion_assessments: criterionAssessments.map((item) => ({
          key: item.key,
          label: item.label,
          rating: item.rating,
          note: item.note || '',
          source_chunk_id: item.source_chunk_id || null,
          page_number: item.page_number ? Number(item.page_number) : null,
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
      await deleteQuestionReviewDraft(selected.id).catch(() => null);
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
      alert('Tải câu hỏi Moodle thất bại: ' + err.message);
    } finally {
      setBusyId('');
    }
  };

  const runBulkEvaluate = async () => {
    const targets = questions.filter((question) => canQueueEvaluation(question)).slice(0, 10);
    if (targets.length === 0) return;
    if (!window.confirm(`Gửi ${targets.length} câu đang lọc để AI hỗ trợ đánh giá?`)) return;
    setBulkBusy(true);
    try {
      for (const question of targets) {
        await autoEvaluateQuestion(question.id, {
          expected_version: question.current_version,
          fallback_to_heuristic: false,
          ...(evaluationModelCode ? { evaluator_model_code: evaluationModelCode } : {}),
        });
      }
      await Promise.all([fetchQuestions(), fetchDashboard()]);
    } catch (err) {
      alert('Đánh giá hàng loạt dừng lại: ' + err.message);
    } finally {
      setBulkBusy(false);
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
  const catalogSubjectById = useMemo(() => {
    const map = new Map();
    catalogSubjects.forEach((subject) => map.set(refId(subject), subject));
    return map;
  }, [catalogSubjects]);
  const teacherById = useMemo(() => {
    const map = new Map();
    teacherOptions.forEach((teacher) => map.set(refId(teacher), teacher));
    return map;
  }, [teacherOptions]);
  const reviewerById = useMemo(() => {
    const map = new Map();
    reviewerOptions.forEach((reviewer) => map.set(refId(reviewer), reviewer));
    return map;
  }, [reviewerOptions]);
  const subjectLabelForQuestion = (question) => {
    const snapshot = question?.subject || question?.review_submission?.subject;
    return snapshot?.name
      || snapshot?.subject_name
      || subjectOptionLabel(catalogSubjectById.get(questionSubjectId(question)))
      || questionSubjectId(question)
      || 'Chưa gắn môn';
  };
  const submitterLabelForQuestion = (question) => {
    const submitterId = refId(question?.submitted_by_user_id);
    const snapshot = question?.review_submission?.submitted_by;
    return snapshot?.display_name
      || snapshot?.email
      || userOptionLabel(teacherById.get(submitterId))
      || submitterId
      || '--';
  };
  const reviewerLabelForQuestion = (question) => {
    const reviewerId = refId(assignmentOf(question).reviewer_user_id);
    return userOptionLabel(reviewerById.get(reviewerId)) || reviewerId || '--';
  };
  const latestEvidence = latestEvaluation?.evidence || {};
  const latestFeedback = latestEvaluation?.feedback || {};
  const latestScores = latestEvaluation?.scores || {};
  const latestWeights = latestEvaluation?.policy?.weights || {};
  const aiInsights = evaluationInsights(latestEvaluation, SCORE_COMPONENTS);
  const answerGuardrail = answerGuardrailInsights(latestEvaluation);
  const metadataGuardrail = metadataGuardrailInsights(latestEvaluation);
  const evaluationContract = evaluationContractInsights(latestEvaluation);
  const criterionStatus = evaluationContract.criterionStatus;
  const hardFailures = evaluationContract.hardFailures;
  const codeGuardrail = evaluationContract.codeGuardrail;
  const aiWeakCriterionKeys = new Set(aiInsights.weakCriteria.map((item) => item.key));
  const aiMissingItems = textList(latestFeedback.missing);
  const aiRiskItems = textList(latestEvidence.risks);
  const aiAction = String(latestFeedback.action || '').toUpperCase();
  const aiSeverity = String(latestFeedback.severity || '').toUpperCase();
  const qualitySummary = selected?.quality_summary || {};
  const overallScore = latestScores.overall ?? qualitySummary.overall_score;
  const evaluationColor = latestEvaluation?.color || qualitySummary.color;
  const latestModel = latestEvaluation?.evaluator_model || {};
  const selectedAssignment = assignmentOf(selected);
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
  const activeAdvancedFilterCount = [
    assignmentFilter !== 'all',
    waitingFilter !== 'all',
    overdueOnly,
    typeFilter !== 'all',
    bloomFilter !== 'all',
    colorFilter !== 'all',
    chapterFilter !== 'all',
    cloFilter !== 'all',
    evaluationStatusFilter !== 'all',
    creatorFilter !== 'all',
    sourcePresenceFilter !== 'all',
    secondaryStatusFilter !== 'all',
    sortMode !== 'priority',
  ].filter(Boolean).length;
  const switchWorkspaceView = (view) => {
    setWorkspaceView(view);
    setSelected(null);
    setPage(1);
    if (view === 'queue') setStatusFilter('PENDING');
    if (view === 'history') setStatusFilter('PROCESSED');
  };

  const saveEditedComment = async (comment) => {
    const body = editingCommentBody.trim();
    if (!body || !selected) return;
    setCommentBusy(true);
    setCommentError('');
    try {
      await updateQuestionComment(selected.id, comment.id || comment._id, { body });
      const result = await listQuestionComments(selected.id);
      setComments(result.items || []);
      setEditingCommentId('');
      setEditingCommentBody('');
    } catch (err) {
      setCommentError(err.message || 'Không sửa được bình luận');
    } finally {
      setCommentBusy(false);
    }
  };

  const removeComment = async (comment) => {
    if (!selected || !window.confirm('Xóa bình luận này?')) return;
    setCommentBusy(true);
    setCommentError('');
    try {
      await deleteQuestionComment(selected.id, comment.id || comment._id);
      const result = await listQuestionComments(selected.id);
      setComments(result.items || []);
    } catch (err) {
      setCommentError(err.message || 'Không xóa được bình luận');
    } finally {
      setCommentBusy(false);
    }
  };
  const resetAdvancedFilters = () => {
    setAssignmentFilter('all');
    setWaitingFilter('all');
    setOverdueOnly(false);
    setTypeFilter('all');
    setBloomFilter('all');
    setColorFilter('all');
    setChapterFilter('all');
    setCloFilter('all');
    setEvaluationStatusFilter('all');
    setPublicationStatusFilter('all');
    setCreatorFilter('all');
    setMinScore('');
    setSourcePresenceFilter('all');
    setSecondaryStatusFilter('all');
    setSortMode('priority');
    setPage(1);
  };

  return (
    <main className="review-page">
      <section className="review-toolbar">
        <div className="review-toolbar__title">
          <span>Hàng đợi kiểm duyệt</span>
          <h1>Kiểm duyệt câu hỏi</h1>
        </div>
        {workspaceView !== 'performance' && (
          <div className="review-actions">
            {evaluationModels.length > 0 && (
              <label className="review-model-picker">
                <span>AI hỗ trợ đánh giá</span>
                <select
                  aria-label="AI hỗ trợ đánh giá"
                  value={evaluationModelCode}
                  onChange={(event) => setEvaluationModelCode(event.target.value)}
                  disabled={bulkBusy || Boolean(busyId) || questions.length === 0}
                >
                  {evaluationModels.map((model) => (
                    <option key={model.code} value={model.code}>
                      {model.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button type="button" className="btn btn--outline" disabled={bulkBusy || questions.length === 0} onClick={runBulkEvaluate}>
              Đánh giá danh sách bằng AI
            </button>
          </div>
        )}
      </section>

      <nav className="review-workspace-tabs" aria-label="Khu vực người duyệt">
        <button type="button" className={workspaceView === 'queue' ? 'is-active' : ''} onClick={() => switchWorkspaceView('queue')}>
          Hàng cần duyệt
        </button>
        <button type="button" className={workspaceView === 'history' ? 'is-active' : ''} onClick={() => switchWorkspaceView('history')}>
          Đã xử lý
        </button>
        <button type="button" className={workspaceView === 'performance' ? 'is-active' : ''} onClick={() => switchWorkspaceView('performance')}>
          Thống kê và so sánh với AI
        </button>
      </nav>

      <section className="review-dashboard" aria-label="Tổng quan công việc kiểm duyệt" hidden={workspaceView !== 'performance'}>
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
              <span>Duyệt khác đề xuất AI</span>
            </div>
            <div>
              <b>{hours(dashboardPerformance.average_review_hours)}</b>
              <span>Xử lý trung bình</span>
            </div>
            <div>
              <b>{dashboardPerformance.revision_issues || 0}</b>
              <span>Lỗi cần sửa</span>
            </div>
          </div>
        </div>

        <div className="review-dashboard__group review-dashboard__group--calibration">
          <div className="review-dashboard__head">
            <span>Mức thống nhất với AI</span>
            <b>{percent(dashboardCalibration.agreement_rate)}</b>
          </div>
          <div className="review-dashboard__metrics">
            <div>
              <b>{dashboardCalibration.sample_size || 0}</b>
              <span>Mẫu so sánh</span>
            </div>
            <div>
              <b>{dashboardCalibration.disagreements || 0}</b>
              <span>Không cùng kết quả</span>
            </div>
            <div>
              <b>{dashboardCalibration.ai_failed_but_approved || 0}</b>
              <span>AI đề xuất xem lại, người duyệt vẫn duyệt</span>
            </div>
            <div>
              <b>{dashboardCalibration.ai_passed_but_not_approved || 0}</b>
              <span>AI đề xuất đạt, người duyệt giữ lại</span>
            </div>
          </div>
          <div className="review-calibration-criteria">
            {REVIEW_CRITERIA.map((criterion) => {
              const item = dashboardCalibration.criteria?.[criterion.key] || {};
              return (
                <div key={criterion.key}>
                  <span>{criterion.label}</span>
                  <b>{percent(item.agreement_rate)}</b>
                  <small>{item.sample_size || 0} mẫu · {item.disagreements || 0} lệch</small>
                </div>
              );
            })}
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
      {workspaceView === 'performance' && dashboardError && <p className="review-error review-error--dashboard">{dashboardError}</p>}

      <section className="review-summary" hidden={workspaceView === 'performance'}>
        <button type="button" onClick={() => updateFilter(setStatusFilter)('PENDING')}>
          <b>{statusFilter === 'PENDING' ? total : (dashboardWorkload.pending || 0)}</b>
          <span>Chờ duyệt</span>
        </button>
        <button type="button" onClick={() => updateFilter(setAssignmentFilter)('mine')}>
          <b>{assignmentFilter === 'mine' ? total : (dashboardWorkload.mine || 0)}</b>
          <span>Của tôi</span>
        </button>
        <button type="button" onClick={() => updateFilter(setColorFilter)('GREEN')}>
          <b>{colorFilter === 'GREEN' ? total : summary.green}</b>
          <span>AI đề xuất đạt</span>
        </button>
        <button type="button" onClick={() => updateFilter(setMinScore)('0.8')}>
          <b>{minScore === '0.8' ? total : summary.passed}</b>
          <span>Điểm AI đạt yêu cầu</span>
        </button>
        <button type="button" onClick={() => updateFilter(setStatusFilter)('APPROVED')}>
          <b>{statusFilter === 'APPROVED' ? total : (dashboardDecisions.APPROVED || 0)}</b>
          <span>Đã duyệt</span>
        </button>
      </section>

      <section
        className={`review-layout ${!loading && questions.length === 0 && !selected ? 'review-layout--empty' : ''}`}
        hidden={workspaceView === 'performance'}
      >
        <div className="review-list-panel">
          <div className="review-filters">
            <div className="review-filter-primary">
              <input
                aria-label="Tìm câu hỏi"
                placeholder="Tìm mã hoặc nội dung câu hỏi..."
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
              />
              <select aria-label="Môn học" value={subjectFilter} onChange={(event) => updateSubjectFilter(event.target.value)}>
                <option value="all">Tất cả môn học</option>
                {catalogSubjects.map((subject) => (
                  <option key={subject.id} value={subject.id}>
                    {subject.subject_code} - {subject.subject_name}
                  </option>
                ))}
              </select>
              <select aria-label="Trạng thái kiểm duyệt" value={statusFilter} onChange={(event) => updateFilter(setStatusFilter)(event.target.value)}>
                {Object.entries(REVIEW_STATUS_LABEL).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
              <button type="button" className={showAdvancedFilters ? 'is-active' : ''} onClick={() => setShowAdvancedFilters((value) => !value)}>
                Bộ lọc nâng cao{activeAdvancedFilterCount ? ` (${activeAdvancedFilterCount})` : ''}
              </button>
            </div>
            <div className="review-date-range">
              <span>Ngày gửi duyệt</span>
              <label>
                Từ
                <input type="date" value={submittedFromFilter} max={submittedToFilter || undefined} onChange={(event) => updateFilter(setSubmittedFromFilter)(event.target.value)} />
              </label>
              <label>
                Đến
                <input type="date" value={submittedToFilter} min={submittedFromFilter || undefined} onChange={(event) => updateFilter(setSubmittedToFilter)(event.target.value)} />
              </label>
            </div>
            <div className="review-filter-advanced" hidden={!showAdvancedFilters}>
              <select value={assignmentFilter} onChange={(event) => updateFilter(setAssignmentFilter)(event.target.value)}>
                {Object.entries(ASSIGNMENT_STATUS_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <select value={waitingFilter} onChange={(event) => updateFilter(setWaitingFilter)(event.target.value)}>
                <option value="all">Mọi mức ưu tiên</option>
                <option value="24">Chờ từ 24 giờ</option>
                <option value="72">Chờ từ 3 ngày</option>
                <option value="168">Chờ từ 7 ngày</option>
              </select>
              <label className="review-filter-toggle">
                <input type="checkbox" checked={overdueOnly} onChange={(event) => updateFilter(setOverdueOnly)(event.target.checked)} />
                Quá hạn giữ câu
              </label>
              <select value={typeFilter} onChange={(event) => updateFilter(setTypeFilter)(event.target.value)}>
                <option value="all">Mọi dạng câu hỏi</option>
                {QUESTION_TYPES.map((type) => <option key={type.backend} value={type.backend}>{type.label}</option>)}
              </select>
              <select value={bloomFilter} onChange={(event) => updateFilter(setBloomFilter)(event.target.value)}>
                <option value="all">Mọi cấp Bloom</option>
                {BLOOM_LEVELS.map((level) => <option key={level.level} value={level.level}>{level.label}</option>)}
              </select>
              <select value={colorFilter} onChange={(event) => updateFilter(setColorFilter)(event.target.value)}>
                {Object.entries(COLOR_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <select value={chapterFilter} onChange={(event) => updateFilter(setChapterFilter)(event.target.value)} disabled={subjectFilter === 'all'}>
                <option value="all">Mọi chương</option>
                {chapterFilterOptions.map((chapter) => <option key={childId(chapter)} value={childId(chapter)}>{chapter.chapter_code} - {chapter.chapter_name}</option>)}
              </select>
              <select value={cloFilter} onChange={(event) => updateFilter(setCloFilter)(event.target.value)} disabled={subjectFilter === 'all'}>
                <option value="all">Mọi CLO</option>
                {cloFilterOptions.map((clo) => <option key={childId(clo)} value={childId(clo)}>{clo.clo_code}</option>)}
              </select>
              <select value={evaluationStatusFilter} onChange={(event) => updateFilter(setEvaluationStatusFilter)(event.target.value)}>
                <option value="all">Mọi kết quả do AI đánh giá</option>
                {Object.entries(EVALUATION_STATUS_LABEL).filter(([value]) => value !== 'RUNNING').map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <select value={sourcePresenceFilter} onChange={(event) => updateFilter(setSourcePresenceFilter)(event.target.value)}>
                <option value="all">Mọi tình trạng nguồn</option>
                <option value="WITH_SOURCE">Có nguồn tham chiếu</option>
                <option value="MISSING_SOURCE">Thiếu nguồn tham chiếu</option>
              </select>
              <select value={secondaryStatusFilter} onChange={(event) => updateFilter(setSecondaryStatusFilter)(event.target.value)}>
                <option value="all">Mọi vòng kiểm duyệt</option>
                <option value="AWAITING_SECONDARY">Cần duyệt lần hai</option>
                <option value="COMPLETED">Đã duyệt lần hai</option>
              </select>
              <select value={creatorFilter} onChange={(event) => updateFilter(setCreatorFilter)(event.target.value)}>
                <option value="all">Mọi người gửi duyệt</option>
                {teacherOptions.map((teacher) => <option key={teacher.id} value={teacher.id}>{teacher.display_name || teacher.email}</option>)}
              </select>
              <select value={sortMode} onChange={(event) => updateFilter(setSortMode)(event.target.value)}>
                <option value="priority">Ưu tiên cần xử lý</option>
                <option value="oldest">Gửi lâu nhất</option>
                <option value="newest">Gửi mới nhất</option>
                <option value="ai_lowest">Xếp câu có điểm thấp trước</option>
                <option value="updated">Cập nhật gần nhất</option>
              </select>
              <button type="button" className="review-filter-reset" onClick={resetAdvancedFilters}>Xóa bộ lọc nâng cao</button>
            </div>
          </div>

          {queueErrors.length > 0 && (
            <div className="review-error" role="alert">
              {queueErrors.map((message) => <div key={message}>{message}</div>)}
            </div>
          )}
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
                      <span>{bloomDisplay(question.classification)}</span>
                      <span className={`difficulty-tag ${question.classification?.difficulty ? `difficulty-tag--${question.classification.difficulty}` : 'difficulty-tag--empty'}`}>
                        {difficultyLabel(question.classification?.difficulty) || 'Chưa gán độ khó'}
                      </span>
                      <span>{subjectLabelForQuestion(question)}</span>
                      {question.submitted_by_user_id && (
                        <span>Gửi: {submitterLabelForQuestion(question)}</span>
                      )}
                      <span title={formatDate(question.submitted_at)}>
                        Chờ {waitingTime(question.submitted_at)}
                      </span>
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
                    <div className="review-row__warnings">
                      {(!question.sources || question.sources.length === 0) && <span>Thiếu nguồn</span>}
                      {question.evaluation_status === 'ERROR' && <span>Chưa đánh giá được</span>}
                      {question.evaluation_status === 'STALE' && <span>Nguồn/câu hỏi đã đổi</span>}
                      {question.secondary_review?.status === 'AWAITING_SECONDARY' && <span>Cần duyệt lần hai</span>}
                    </div>
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
                    <small>{REVIEW_STATUS_LABEL[question.review_status] || 'Chưa xác định'}</small>
                  </div>
                </article>
              ))}
              {questions.length === 0 && (
                <div className="review-empty-state">
                  <span aria-hidden="true">✓</span>
                  <strong>Chưa có câu hỏi cần xử lý</strong>
                  <p>Thử đổi trạng thái, khoảng thời gian hoặc xóa các bộ lọc đang áp dụng.</p>
                </div>
              )}
              {total > 0 && (
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
              )}
            </div>
          )}
        </div>

        <aside className="review-detail-panel" hidden={!loading && questions.length === 0 && !selected}>
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
                  <span>Người gửi duyệt</span>
                  <b>{submitterLabelForQuestion(selected)}</b>
                </div>
                <div>
                  <span>Môn học</span>
                  <b>{subjectLabelForQuestion(selected)}</b>
                </div>
                <div>
                  <span>Độ khó</span>
                  <b>{difficultyLabel(selected.classification?.difficulty) || 'Chưa gán'}</b>
                </div>
                <div>
                  <span>Gửi duyệt lúc</span>
                  <b>{formatDate(selected.submitted_at)}</b>
                </div>
                <div>
                  <span>Người duyệt</span>
                  <b>{reviewerLabelForQuestion(selected)}</b>
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
                  <b>{secondaryReviewStatusLabel(selected.secondary_review?.status)}</b>
                </div>
              </section>
              <nav className="review-detail-tabs" aria-label="Nội dung kiểm duyệt">
                <button type="button" className={detailView === 'question' ? 'is-active' : ''} onClick={() => setDetailView('question')}>Câu hỏi & đáp án</button>
                <button type="button" className={detailView === 'source' ? 'is-active' : ''} onClick={() => setDetailView('source')}>Nguồn tham chiếu</button>
                <button type="button" className={detailView === 'ai' ? 'is-active' : ''} onClick={() => setDetailView('ai')}>Gợi ý từ AI</button>
                <button type="button" className={detailView === 'history' ? 'is-active' : ''} onClick={() => setDetailView('history')}>Trao đổi & lịch sử</button>
              </nav>
              <div className="detail-actions">
                <button type="button" disabled={busyId === selected.id || !canClaimQuestion(selected)} onClick={() => claimReview(selected)}>
                  {selectedAssignment.status === 'IN_REVIEW' && isAssignmentMine(selected, user) ? 'Gia hạn giữ câu' : 'Nhận câu'}
                </button>
                <button type="button" disabled={busyId === selected.id || !canReleaseQuestion(selected)} onClick={() => releaseReview(selected)}>
                  Trả câu
                </button>
                {canAssignReviews && (
                  <button type="button" disabled={busyId === selected.id || selected.review_status !== 'PENDING'} onClick={() => openAssignmentForm(selected)}>
                    Gán người duyệt
                  </button>
                )}
                {canAssignReviews && (
                  <button type="button" disabled={busyId === selected.id || !canReleaseQuestion(selected)} onClick={() => unassignReview(selected)}>
                    Bỏ gán
                  </button>
                )}
                <button type="button" disabled={busyId === selected.id || !canEvaluateQuestions || !canQueueEvaluation(selected)} onClick={() => runEvaluation(selected)}>
                  {selected.evaluation_status === 'ERROR' || selected.evaluation_status === 'FAILED' || selected.evaluation_status === 'STALE'
                    ? 'Nhờ AI đánh giá lại'
                    : 'Nhờ AI đánh giá'}
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
              </div>

              {historyLoading ? (
                <p className="review-empty">Đang tải minh chứng...</p>
              ) : (
                <>
                  <section className="question-answer-panel" hidden={detailView !== 'question'}>
                    <div className="question-answer-panel__meta">
                      <span>Dạng câu hỏi <b>{questionTypeLabel(assessmentType(selected))}</b></span>
                      <span>Mức Bloom <b>{bloomDisplay(selected.classification)}</b></span>
                      <span>Độ khó đã chọn <b>{difficultyLabel(selected.classification?.difficulty) || 'Chưa gán'}</b></span>
                      <span>Phiên bản <b>{selected.current_version}</b></span>
                    </div>
                    <h3>Nội dung câu hỏi</h3>
                    <p>{selected.content}</p>
                    <div className="question-option-list">
                      {Object.entries(selected.question_data?.options || {}).map(([key, value]) => (
                        <div key={key} className={String(selected.question_data?.correct_answer || '').split(',').map((item) => item.trim()).includes(key) ? 'is-correct' : ''}>
                          <b>{key}</b><span>{String(value)}</span>
                        </div>
                      ))}
                    </div>
                    <div className="question-answer-key">
                      <span>Đáp án</span>
                      <b>{selected.question_data?.correct_answer || 'Chưa có đáp án'}</b>
                    </div>
                    <div className="question-explanation">
                      <span>Giải thích</span>
                      <p>{selected.question_data?.explanation || 'Chưa có giải thích đáp án.'}</p>
                    </div>
                  </section>

                  <section className="evaluation-panel" hidden={detailView !== 'ai'}>
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
                        <div
                          key={component.key}
                          className={aiWeakCriterionKeys.has(component.key) ? 'score-card--weak' : ''}
                        >
                          <span>{component.label}</span>
                          <b>{criterionStatus[component.key] === 'NO_DATA' ? 'Thiếu dữ liệu' : score(latestScores[component.key])}</b>
                          <small>
                            Trọng số {percent(latestWeights[component.key])}
                          </small>
                          {aiWeakCriterionKeys.has(component.key) && (
                            <em>Dưới ngưỡng đạt {score(aiInsights.passMin)}</em>
                          )}
                        </div>
                      ))}
                    </div>

                    {latestEvaluation && (
                      <div className="ai-review-summary">
                        <div className="ai-review-summary__head">
                          <div>
                            <span>Đề xuất của AI</span>
                            <b>{AI_ACTION_LABEL[aiAction] || (latestEvaluation.passed ? 'Có thể duyệt' : 'Cần người duyệt xem lại')}</b>
                          </div>
                          {aiSeverity && <strong className={`ai-severity ai-severity--${aiSeverity.toLowerCase()}`}>{AI_SEVERITY_LABEL[aiSeverity] || aiSeverity}</strong>}
                        </div>
                        <p>{latestFeedback.summary || latestEvidence.reasoning || 'AI chưa cung cấp phần giải thích tổng quát.'}</p>
                        {answerGuardrail.applied && (
                          <div className="answer-guardrail-warning" role="alert">
                            <strong>Đã chặn tự động duyệt đáp án</strong>
                            <span>Hệ thống phát hiện kết quả AI chưa đủ tin cậy; người duyệt cần đối chiếu từng phương án với nguồn.</span>
                            <ul>
                              {answerGuardrail.issues.map((item) => <li key={item}>{item}</li>)}
                            </ul>
                          </div>
                        )}
                        {metadataGuardrail.applied && (
                          <div className="metadata-guardrail-warning" role="alert">
                            <strong>Thiếu metadata sư phạm bắt buộc</strong>
                            <ul>
                              {metadataGuardrail.issues.map((item) => <li key={item}>{item}</li>)}
                            </ul>
                          </div>
                        )}
                        {hardFailures.length > 0 && (
                          <div className="answer-guardrail-warning" role="alert">
                            <strong>Không thể tự động duyệt do lỗi bắt buộc</strong>
                            <ul>
                              {hardFailures.map((item) => <li key={`${item.code}-${item.message}`}>{item.code}: {item.message}</li>)}
                            </ul>
                          </div>
                        )}
                        {codeGuardrail.applied && (
                          <div className={codeGuardrail.passed ? 'metadata-guardrail-warning' : 'answer-guardrail-warning'}>
                            <strong>Kiểm tra code: {codeGuardrail.status || 'Chưa xác định'}</strong>
                            <span>{codeGuardrail.toolchain?.compiler_version || codeGuardrail.toolchain?.contract_version}</span>
                          </div>
                        )}
                        {answerGuardrail.optionChecks.length > 0 && (
                          <div className="option-checks">
                            <span>Kiểm chứng từng phương án</span>
                            <div className="option-checks__grid">
                              {answerGuardrail.optionChecks.map((item) => (
                                <div className={`option-check option-check--${item.verdict.toLowerCase()}`} key={item.key}>
                                  <div>
                                    <b>{item.key}</b>
                                    <strong>{OPTION_VERDICT_LABEL[item.verdict] || item.verdict || 'Chưa kết luận'}</strong>
                                    {item.sourceLabel && <em>{item.sourceLabel}</em>}
                                  </div>
                                  <p>{item.excerpt || 'AI chưa cung cấp trích dẫn.'}</p>
                                  {item.inferredFromComplement && (
                                    <small className="option-check__inferred">
                                      Hệ thống suy ra từ phương án {item.inferredFromComplement}
                                    </small>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {aiInsights.weakCriteria.length > 0 && (
                          <div className="ai-review-summary__criteria">
                            <span>Tiêu chí dưới ngưỡng:</span>
                            {aiInsights.weakCriteria.map((item) => <b key={item.key}>{item.label} ({score(item.score)})</b>)}
                          </div>
                        )}
                        {aiMissingItems.length > 0 && (
                          <div className="ai-review-summary__list">
                            <span>Nội dung còn thiếu</span>
                            <ul>{aiMissingItems.slice(0, 5).map((item) => <li key={item}>{item}</li>)}</ul>
                          </div>
                        )}
                        {aiRiskItems.length > 0 && (
                          <div className="ai-review-summary__list">
                            <span>Rủi ro cần đối chiếu</span>
                            <ul>{aiRiskItems.slice(0, 5).map((item) => <li key={item}>{item}</li>)}</ul>
                          </div>
                        )}
                        {aiInsights.uniformScores && (
                          <p className="ai-review-summary__warning">
                            Các tiêu chí có điểm gần như giống nhau. Người duyệt nên đối chiếu từng minh chứng thay vì chỉ dựa vào tổng điểm.
                          </p>
                        )}
                        {!latestEvaluation.passed && selected.review_status === 'PENDING' && (
                          <div className="ai-review-summary__action">
                            <button
                              type="button"
                              disabled={!canReviewQuestion(selected)}
                              onClick={() => openReviewForm(selected, 'NEEDS_REVISION', { aiEvaluation: latestEvaluation })}
                            >
                              Dùng góp ý AI cho phiếu Cần sửa
                            </button>
                            {!canReviewQuestion(selected) && <small>Nhận câu hỏi trước để tạo phiếu kiểm duyệt.</small>}
                          </div>
                        )}
                      </div>
                    )}

                    <div className="evaluation-meta">
                      <span>
                        AI hỗ trợ: <b>{evaluatorModelLabel(latestModel)}</b>
                      </span>
                      <span>Bộ tiêu chí: <b>{latestEvaluation ? 'Tiêu chí kiểm duyệt hiện hành' : '--'}</b></span>
                      {evaluationContract.scoreCoverage !== null && (
                        <span>Độ phủ dữ liệu chấm: <b>{percent(evaluationContract.scoreCoverage)}</b></span>
                      )}
                      <span>Đánh giá lúc: <b>{formatDate(latestEvaluation?.created_at || qualitySummary.evaluated_at)}</b></span>
                      {latestEvidence.assessed_difficulty ? (
                        <span>
                          Độ khó AI đề xuất: <b>{difficultyLabel(latestEvidence.assessed_difficulty)}</b>
                        </span>
                      ) : null}
                    </div>
                    {!latestEvaluation && (
                      <p className="evaluation-note">
                        Chưa có kết quả đánh giá AI cho câu hỏi này.
                      </p>
                    )}
                  </section>

                  <section className="evidence-block" hidden={detailView !== 'ai'}>
                    <h3>Minh chứng đánh giá</h3>
                    <p>{latestEvidence.supporting_excerpt || latestEvidence.source_excerpt || 'Chưa có minh chứng.'}</p>
                    {latestEvidence.reasoning && <span>{latestEvidence.reasoning}</span>}
                    {qualitySummary.error?.message && <span>Hệ thống chưa thể hoàn tất đánh giá. Vui lòng thử lại.</span>}
                    {latestEvidence.fallback_reason && <span>Hệ thống đã dùng phương pháp đánh giá dự phòng.</span>}
                  </section>

                  <section className="source-viewer" hidden={detailView !== 'source'}>
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
                      <p className="review-empty">Không có nguồn tham chiếu cho câu hỏi này.</p>
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
                              <span>Nguồn {source.citation_order}</span>
                              <b>{pageRangeLabel(source.page_range)}</b>
                              <small>Đoạn tham chiếu {index + 1}</small>
                              {source.evidence?.status === 'VERIFIED' && <em>Span đã xác minh</em>}
                              {source.is_current_chunk_set === false && <em>Nguồn cũ</em>}
                            </button>
                          ))}
                        </div>

                        {activeSource && (
                          <div className="source-detail">
                            <div className="source-meta-grid">
                              <span>Vị trí <b>{pageRangeLabel(activeSource.page_range)}</b></span>
                              <span>Thứ tự nguồn <b>{activeSource.citation_order || '--'}</b></span>
                              <span>Trạng thái <b>{activeSource.is_current_chunk_set === false ? 'Nguồn cũ' : 'Đang sử dụng'}</b></span>
                              {activeSource.evidence && (
                                <span>Evidence span <b>{activeSource.evidence.char_start}-{activeSource.evidence.char_end}</b></span>
                              )}
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
                                <p>Đang mở tài liệu...</p>
                              ) : sourcePdfUrl ? (
                                <iframe src={sourcePdfUrl} title={`PDF nguồn ${sourceViewer?.document?.original_filename || ''}`} />
                              ) : (
                                <p>
                                  {sourceViewer?.document?.original_filename?.toLowerCase().endsWith('.pdf')
                                    ? 'File PDF nguồn hiện không còn khả dụng.'
                                    : 'Tài liệu nguồn không phải PDF; đối chiếu bằng đoạn trích bên dưới.'}
                                </p>
                              )}
                            </div>
                            <SourceText source={activeSource} page={activePageRecord} />
                          </div>
                        )}
                      </>
                    )}
                  </section>

                  <section className="comment-thread" hidden={detailView !== 'history'}>
                    <div className="comment-thread__head">
                      <h3>Trao đổi</h3>
                      <span>{comments.length} bình luận</span>
                    </div>
                    <div className="comment-list">
                      {comments.slice(-6).map((comment) => (
                        <div className="comment-item" key={comment.id || comment._id}>
                          <b>{userRoleLabel(comment.author_role)}</b>
                          {editingCommentId === (comment.id || comment._id) ? (
                            <div className="comment-edit-row">
                              <textarea value={editingCommentBody} onChange={(event) => setEditingCommentBody(event.target.value)} rows={2} />
                              <button type="button" disabled={commentBusy || !editingCommentBody.trim()} onClick={() => saveEditedComment(comment)}>Lưu</button>
                              <button type="button" onClick={() => setEditingCommentId('')}>Hủy</button>
                            </div>
                          ) : (
                            <p>{comment.body}</p>
                          )}
                          <div className="comment-item__meta">
                            <small>{formatDate(comment.created_at)}{comment.edited_at ? ' · đã sửa' : ''}</small>
                            {(user?.role === 'Admin' || refId(comment.author_user_id) === refId(user?.id)) && editingCommentId !== (comment.id || comment._id) && (
                              <span>
                                <button type="button" onClick={() => { setEditingCommentId(comment.id || comment._id); setEditingCommentBody(comment.body); }}>Sửa</button>
                                <button type="button" onClick={() => removeComment(comment)}>Xóa</button>
                              </span>
                            )}
                          </div>
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

                  <section className="history-grid" hidden={detailView !== 'history'}>
                    <div>
                      <h3>Lịch sử kiểm duyệt</h3>
                      {reviews.slice(0, 4).map((review) => (
                        <div className="history-review" key={review.id || review._id}>
                          <p><b>{REVIEW_STATUS_LABEL[review.decision] || 'Chưa xác định'}</b> {review.note || ''}</p>
                          {reviewIssuesOf(review).length > 0 && (
                            <div className="history-issue-list">
                              {reviewIssuesOf(review).slice(0, 3).map((issue, index) => (
                                <small className="history-issue" key={`${issue.title || issue.detail}-${index}`}>
                                  {issueSeverityLabel(issue.severity)} · {issue.title || issue.detail}
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
                      <h3>Đưa câu hỏi lên Moodle</h3>
                      {publications.slice(0, 4).map((publication) => (
                        <p key={publication.id || publication._id}>
                          <b>{publicationStatusLabel(publication.status)}</b>
                        </p>
                      ))}
                      {publications.length === 0 && <p>Chưa có lần xuất bản.</p>}
                      <div className="history-moodle-actions">
                        <button type="button" disabled={busyId === selected.id || !canPublishMoodle || selected.review_status !== 'APPROVED' || selected.publication_status === 'PUBLISHED'} onClick={() => publish(selected)}>Ghi mô phỏng Moodle</button>
                        <button type="button" disabled={busyId === selected.id || !canExportMoodle || selected.review_status !== 'APPROVED'} onClick={() => exportMoodle(selected, 'gift')}>Tải tệp GIFT</button>
                        <button type="button" disabled={busyId === selected.id || !canExportMoodle || selected.review_status !== 'APPROVED'} onClick={() => exportMoodle(selected, 'xml')}>Tải tệp XML</button>
                      </div>
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
                <h2>{REVIEW_STATUS_LABEL[reviewDraft.decision] || 'Kết quả kiểm duyệt'}</h2>
                {draftSaveState && <small>{draftSaveState}</small>}
              </div>
              <button type="button" onClick={() => setReviewDraft(null)}>Đóng</button>
            </div>

            <section className="review-form-section">
              <div className="review-criterion-heading">
                <div>
                  <h3>So sánh gợi ý AI và quyết định của người duyệt</h3>
                  <p>Hãy đánh giá từng tiêu chí; AI chỉ đưa ra gợi ý tham khảo.</p>
                </div>
              </div>
              <div className="review-criterion-list">
                {(reviewDraft.criteria || []).map((item) => (
                  <div className="review-criterion-row" key={item.key}>
                    <div>
                      <b>{item.label}</b>
                      <small>{item.description}</small>
                    </div>
                    <div className="review-criterion-ai">
                      <span>AI gợi ý</span>
                      <b>{score(latestScores[item.key])}</b>
                    </div>
                    <label>
                      <span>Người duyệt</span>
                      <select value={item.rating} onChange={(event) => updateCriterion(item.key, { rating: event.target.value })}>
                        {Object.entries(CRITERION_RATING_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    </label>
                    <input value={item.note} onChange={(event) => updateCriterion(item.key, { note: event.target.value })} placeholder="Lý do hoặc ghi chú" />
                    <select value={item.source_chunk_id} onChange={(event) => updateCriterion(item.key, { source_chunk_id: event.target.value })}>
                      <option value="">Không gắn nguồn</option>
                      {sourceItems.map((source, index) => (
                        <option key={source.chunk_id || index} value={source.chunk_id || ''}>Nguồn #{source.citation_order} · {pageRangeLabel(source.page_range)}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </section>

            <section className="review-form-section">
              <h3>Danh sách kiểm tra cho dạng {questionTypeLabel(assessmentType(selected))}</h3>
              <ul className="review-type-guidance">
                {(QUESTION_TYPE_GUIDANCE[assessmentType(selected)] || []).map((item) => <li key={item}>{item}</li>)}
              </ul>
              <h4>Kiểm tra trước khi chốt</h4>
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
                <span>Ghi chú tổng</span>
                <textarea
                  value={reviewDraft.overallNote}
                  onChange={(event) => updateReviewDraft({ overallNote: event.target.value })}
                  rows={4}
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
                  <span>Lý do duyệt khác đề xuất AI</span>
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
                        Nguồn {source.citation_order} · {pageRangeLabel(source.page_range)}
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
              <button type="button" className="review-draft-delete" onClick={discardReviewDraft}>Xóa bản nháp</button>
              <button type="button" onClick={() => setReviewDraft(null)}>Đóng, tiếp tục sau</button>
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
                    Người duyệt hiện tại (không còn trong danh sách)
                  </option>
                )}
              </select>
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
