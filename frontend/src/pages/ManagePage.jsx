import React, { useContext, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  autoEvaluateQuestion,
  createQuestion,
  deleteQuestion,
  duplicateQuestion,
  getQuestion,
  listQuestionEvaluations,
  listQuestionMoodlePublications,
  listQuestionReviews,
  listQuestionVersions,
  listQuestions,
  publishQuestionToMoodle,
  reviewQuestion,
  submitQuestionForReview,
  updateQuestion,
} from '../api/questions';
import {
  cancelDocumentJob,
  deleteDocument,
  listDocumentJobs,
  listDocumentPages,
  listDocuments,
  reindexDocument,
  retryDocumentJob,
  updateDocument,
  updateDocumentPage,
} from '../api/documents';
import { listSubjects } from '../api/catalog';
import { BLOOM_LEVELS, QUESTION_TYPES, questionTypeLabel } from '../constants/generationEnums';
import { AuthContext } from '../context/AuthContext';
import {
  SINGLE_CHOICE_TYPES,
  MULTI_CHOICE_TYPES,
  correctAnswerValues,
  entriesToOptions,
  joinCorrectValues,
  normalizeQuestionType,
  optionEntriesForQuestion,
  validateQuestionAnswer,
} from '../utils/questionOptions';
import {
  QUESTION_FILTER_DEFAULTS,
  encodeSavedQuestionFilters,
  parseSavedQuestionFilters,
  questionFilterStorageKey,
} from '../utils/questionFilterPresets';
import { buildQuestionCoverage } from '../utils/questionCoverage';
import {
  buildBulkQuestionUpdatePayload,
  filterSubmittableQuestions,
  selectedQuestionsForIds,
  summarizeBulkSettled,
} from '../utils/questionBulkActions';
import {
  downloadCsv,
  downloadXlsx,
  rowsToCsv,
  timestampedCsvFilename,
  timestampedXlsxFilename,
} from '../utils/csvExport';
import {
  QUESTION_BANK_EXPORT_COLUMNS,
  downloadTextFile,
  parseQuestionBankImportFile,
  questionsToGift,
  questionsToMoodleXml,
  timestampedQuestionBankFilename,
} from '../utils/questionBankExchange';
import '../css/ManagePage.css';

const REVIEW_STATUS_LABEL = {
  DRAFT: 'Nháp',
  PENDING: 'Chờ duyệt',
  APPROVED: 'Đã duyệt',
  NEEDS_REVISION: 'Cần sửa',
  REJECTED: 'Từ chối',
};

const REVIEW_STATUS_CLASS = {
  DRAFT: 'status--draft',
  PENDING: 'status--pending',
  APPROVED: 'status--approved',
  NEEDS_REVISION: 'status--revise',
  REJECTED: 'status--revise',
};

const DOC_STATUS_LABEL = {
  UPLOADED: 'Đã tải lên',
  PROCESSING: 'Đang xử lý',
  READY: 'Đã xử lý',
  FAILED: 'Thất bại',
  ARCHIVED: 'Đã lưu trữ',
};

const JOB_STATUS_LABEL = {
  NOT_STARTED: 'Chưa chạy',
  QUEUED: 'Chờ chạy',
  PROCESSING: 'Đang chạy',
  COMPLETED: 'Hoàn tất',
  FAILED: 'Lỗi',
  CANCELLED: 'Đã hủy',
};

const PIPELINE_STEP_LABEL = {
  ocr_status: 'OCR',
  chunk_status: 'Chunk',
  index_status: 'Index',
};

const ACTIVE_DOCUMENT_JOB_STATUSES = new Set(['QUEUED', 'PROCESSING']);
const RETRYABLE_DOCUMENT_JOB_STATUSES = new Set(['FAILED', 'ERROR', 'STALE']);

const EVALUATION_STATUS_LABEL = {
  NOT_STARTED: 'Chưa đánh giá',
  QUEUED: 'Chờ AI đánh giá',
  PROCESSING: 'Đang đánh giá',
  PASSED: 'Đạt',
  FAILED: 'Không đạt',
  ERROR: 'AI lỗi',
  STALE: 'Cần đánh giá lại',
};

const PUBLICATION_STATUS_LABEL = {
  NOT_PUBLISHED: 'Chưa ghi mô phỏng',
  PUBLISHED: 'Đã ghi mô phỏng Moodle',
  STALE: 'Cần ghi mô phỏng lại',
  FAILED: 'Mô phỏng lỗi',
};

const QUALITY_COLOR_CLASS = {
  GREEN: 'quality--green',
  YELLOW: 'quality--yellow',
  RED: 'quality--red',
};

const QUALITY_COLOR_LABEL = {
  GREEN: 'Đạt tốt',
  YELLOW: 'Cần xem lại',
  RED: 'Rủi ro cao',
};

const DIFFICULTIES = [
  { value: 'de', label: 'Dễ' },
  { value: 'trung_binh', label: 'Trung bình' },
  { value: 'kho', label: 'Khó' },
];

const SUBMITTABLE_REVIEW_STATUSES = new Set(['DRAFT', 'NEEDS_REVISION']);
const QUESTION_BANK_EXPORT_FORMATS = [
  { value: 'csv', label: 'CSV' },
  { value: 'xlsx', label: 'XLSX' },
  { value: 'gift', label: 'GIFT' },
  { value: 'xml', label: 'XML Moodle' },
];
const QUESTION_IMPORT_ACCEPT = '.csv,.xlsx,.gift,.txt,.xml';

const QUICK_REVIEW_RUBRIC = [
  { key: 'source_alignment', label: 'Bám sát nguồn' },
  { key: 'answer_correctness', label: 'Đáp án đúng' },
  { key: 'bloom_clo_alignment', label: 'Đúng Bloom/CLO' },
  { key: 'language_quality', label: 'Diễn đạt rõ' },
  { key: 'moodle_readiness', label: 'Sẵn sàng Moodle' },
];

function formatDateTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('vi-VN');
}

function pipelineStatusClass(value) {
  const status = String(value || 'NOT_STARTED').toUpperCase();
  if (status === 'COMPLETED') return 'done';
  if (status === 'FAILED') return 'failed';
  if (['QUEUED', 'PROCESSING'].includes(status)) return 'active';
  if (status === 'CANCELLED') return 'cancelled';
  return 'idle';
}

function documentPipelineSteps(document) {
  const summary = document?.pipeline_summary || {};
  return Object.entries(PIPELINE_STEP_LABEL).map(([key, label]) => {
    const status = summary[key] || 'NOT_STARTED';
    return { key, label, status };
  });
}

function documentErrorMessage(document) {
  const error = document?.latest_error || {};
  return error.message || error.detail || '';
}

function jobErrorMessage(job) {
  const error = job?.error || {};
  return error.message || error.detail || '';
}

function pageTextPreview(page) {
  return page?.cleaned_text || page?.raw_text || '';
}

function canRetryDocumentJob(job) {
  return Boolean(job?.can_retry) || (
    ['OCR', 'CHUNK'].includes(job?.job_type) && RETRYABLE_DOCUMENT_JOB_STATUSES.has(job?.status)
  );
}

function canCancelDocumentJob(job) {
  return Boolean(job?.can_cancel) || ACTIVE_DOCUMENT_JOB_STATUSES.has(job?.status);
}

function canEditDocumentOcr(document) {
  const summary = document?.pipeline_summary || {};
  const blockingStatuses = new Set(['QUEUED', 'PROCESSING', 'COMPLETED']);
  return !blockingStatuses.has(summary.chunk_status) && !blockingStatuses.has(summary.index_status);
}

function canReindexDocument(document) {
  return document?.pipeline_summary?.chunk_status === 'COMPLETED';
}

function formatScore(value) {
  return typeof value === 'number' ? value.toFixed(2) : '—';
}

function latestEvaluationText(item) {
  const quality = item.quality_summary || {};
  if (!quality.overall_score && quality.overall_score !== 0) {
    return EVALUATION_STATUS_LABEL[item.evaluation_status] || item.evaluation_status;
  }
  return `${formatScore(quality.overall_score)} · ${QUALITY_COLOR_LABEL[quality.color] || 'Chưa phân mức'}`;
}

function isEvaluationBusy(item) {
  return ['QUEUED', 'PROCESSING', 'RUNNING'].includes(item?.evaluation_status);
}

function canQueueEvaluation(item) {
  return item && !isEvaluationBusy(item) && item.evaluation_status !== 'PASSED';
}

function questionAssessmentType(item) {
  return normalizeQuestionType(item?.classification?.assessment_type);
}

function refId(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  return value.id || value._id || '';
}

function questionSubjectId(item) {
  return refId(item?.classification?.subject?.id || item?.classification?.subject);
}

function questionDocumentId(item) {
  return refId(item?.document_id || item?.document?.id || item?.document);
}

function questionBloomLevel(item) {
  const level = item?.classification?.bloom?.level;
  return level ? String(level) : '';
}

function questionCloIds(item) {
  return (item?.clos || []).map((clo) => refId(clo.id || clo)).filter(Boolean);
}

function versionSourceChunkIds(version) {
  return (version?.sources || [])
    .map((source) => refId(source.chunk_id || source.chunk))
    .filter(Boolean);
}

function versionClassification(version) {
  return version?.classification || {};
}

function versionCloLabel(version) {
  const labels = (version?.clos || []).map((clo) => clo.code || clo.clo_code || refId(clo.id || clo));
  return labels.filter(Boolean).join(', ');
}

function stringifyComparable(value) {
  if (value === undefined || value === null || value === '') return '—';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

function persistSavedQuestionFilters(storageKey, items) {
  window.localStorage.setItem(
    storageKey,
    encodeSavedQuestionFilters(items),
  );
}

function makeSavedFilterId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  return `filter-${Date.now()}`;
}

function versionDiffRows(left, right) {
  if (!left || !right) return [];
  const leftClassification = versionClassification(left);
  const rightClassification = versionClassification(right);
  const rows = [
    {
      label: 'Nội dung',
      before: left.content,
      after: right.content,
    },
    {
      label: 'Lựa chọn',
      before: left.question_data?.options,
      after: right.question_data?.options,
    },
    {
      label: 'Đáp án',
      before: left.question_data?.correct_answer,
      after: right.question_data?.correct_answer,
    },
    {
      label: 'Giải thích',
      before: left.question_data?.explanation,
      after: right.question_data?.explanation,
    },
    {
      label: 'Bloom',
      before: leftClassification.bloom?.name || leftClassification.bloom?.level,
      after: rightClassification.bloom?.name || rightClassification.bloom?.level,
    },
    {
      label: 'CLO',
      before: versionCloLabel(left),
      after: versionCloLabel(right),
    },
    {
      label: 'Nguồn',
      before: versionSourceChunkIds(left),
      after: versionSourceChunkIds(right),
    },
  ].map((row) => ({
    ...row,
    before: stringifyComparable(row.before),
    after: stringifyComparable(row.after),
  }));
  return rows.filter((row) => row.before !== row.after);
}

function renderChoiceEditor({
  questionType,
  rawOptions,
  correctAnswer,
  onOptionChange,
  onCorrectAnswerChange,
  onToggleCorrectAnswer,
  keyPrefix,
}) {
  const entries = optionEntriesForQuestion({ questionType, rawOptions });

  if (SINGLE_CHOICE_TYPES.has(questionType)) {
    return (
      <div className="draft-option-editor">
        {entries.map((entry) => (
          <label className="draft-option-row" key={entry.key}>
            <input
              type="radio"
              name={`${keyPrefix}-answer`}
              checked={correctAnswer === entry.key}
              onChange={() => onCorrectAnswerChange(entry.key)}
            />
            <span className="draft-option-key">{entry.key}</span>
            <input
              className="field-input"
              value={entry.value}
              onChange={(event) => onOptionChange(entry.key, event.target.value)}
            />
          </label>
        ))}
      </div>
    );
  }

  if (MULTI_CHOICE_TYPES.has(questionType)) {
    const selectedAnswers = correctAnswerValues(correctAnswer);
    return (
      <div className="draft-option-editor">
        {entries.map((entry) => (
          <label className="draft-option-row" key={entry.key}>
            <input
              type="checkbox"
              checked={selectedAnswers.includes(entry.key)}
              onChange={() => onToggleCorrectAnswer(entry.key)}
            />
            <span className="draft-option-key">{entry.key}</span>
            <input
              className="field-input"
              value={entry.value}
              onChange={(event) => onOptionChange(entry.key, event.target.value)}
            />
          </label>
        ))}
      </div>
    );
  }

  if (entries.length > 0) {
    return (
      <div className="draft-option-editor">
        {entries.map((entry) => (
          <label className="draft-option-row draft-option-row--plain" key={entry.key}>
            <span className="draft-option-key">{entry.key}</span>
            <input
              className="field-input"
              value={entry.value}
              onChange={(event) => onOptionChange(entry.key, event.target.value)}
            />
          </label>
        ))}
        <label className="draft-edit-field">
          <span>Đáp án đúng</span>
          <input
            className="field-input"
            value={correctAnswer}
            onChange={(event) => onCorrectAnswerChange(event.target.value)}
          />
        </label>
      </div>
    );
  }

  return (
    <label className="draft-edit-field">
      <span>Đáp án đúng</span>
      <input
        className="field-input"
        value={correctAnswer}
        onChange={(event) => onCorrectAnswerChange(event.target.value)}
      />
    </label>
  );
}

function ManagePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useContext(AuthContext);
  const canEditQuestions = ['Admin', 'Teacher'].includes(user?.role);
  const canManageDocuments = ['Admin', 'Teacher'].includes(user?.role);
  const canReviewQuestions = ['Admin', 'Reviewer'].includes(user?.role);

  const [questions, setQuestions] = useState([]);
  const [questionsLoading, setQuestionsLoading] = useState(true);
  const [questionsError, setQuestionsError] = useState('');

  const [documents, setDocuments] = useState([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentsError, setDocumentsError] = useState('');
  const [documentJobsById, setDocumentJobsById] = useState({});
  const [documentJobsLoadingId, setDocumentJobsLoadingId] = useState('');
  const [documentJobActionKey, setDocumentJobActionKey] = useState('');
  const [documentJobsError, setDocumentJobsError] = useState(null);
  const [documentPagesById, setDocumentPagesById] = useState({});
  const [documentPagesLoadingId, setDocumentPagesLoadingId] = useState('');
  const [documentPagesError, setDocumentPagesError] = useState(null);
  const [ocrPageDrafts, setOcrPageDrafts] = useState({});
  const [savingOcrPageKey, setSavingOcrPageKey] = useState('');
  const [expandedDocumentId, setExpandedDocumentId] = useState('');
  const [expandedDocumentPagesId, setExpandedDocumentPagesId] = useState('');
  const [subjects, setSubjects] = useState([]);
  const [subjectsError, setSubjectsError] = useState('');

  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all-type');
  const [documentFilter, setDocumentFilter] = useState('all-documents');
  const [subjectFilter, setSubjectFilter] = useState('all-subjects');
  const [chapterFilter, setChapterFilter] = useState('all-chapters');
  const [cloFilter, setCloFilter] = useState('all-clos');
  const [bloomFilter, setBloomFilter] = useState('all-bloom');
  const [difficultyFilter, setDifficultyFilter] = useState('all-difficulties');
  const [evaluationFilter, setEvaluationFilter] = useState('all-evaluations');
  const [publicationFilter, setPublicationFilter] = useState('all-publications');
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [savedQuestionFilters, setSavedQuestionFilters] = useState([]);
  const [selectedSavedFilterId, setSelectedSavedFilterId] = useState('');
  const [savedFilterName, setSavedFilterName] = useState('');
  const [questionExportFormat, setQuestionExportFormat] = useState('csv');
  const [questionExchangeBusy, setQuestionExchangeBusy] = useState('');
  const [questionExchangeMessage, setQuestionExchangeMessage] = useState('');

  const [editing, setEditing] = useState(null);
  const [editContent, setEditContent] = useState('');
  const [editRawOptions, setEditRawOptions] = useState(null);
  const [editCorrectAnswer, setEditCorrectAnswer] = useState('');
  const [editExplanation, setEditExplanation] = useState('');
  const [editCloIds, setEditCloIds] = useState([]);
  const [editChangeNote, setEditChangeNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [selectedQuestionIds, setSelectedQuestionIds] = useState([]);
  const [bulkActionBusy, setBulkActionBusy] = useState('');
  const [bulkEditOpen, setBulkEditOpen] = useState(false);
  const [bulkEditDraft, setBulkEditDraft] = useState({
    bloomLevel: '',
    difficulty: '',
    applyClo: false,
    cloIds: [],
  });
  const [deletingId, setDeletingId] = useState(null);
  const [duplicatingQuestionId, setDuplicatingQuestionId] = useState(null);
  const [deletingDocId, setDeletingDocId] = useState(null);
  const [workflowBusyId, setWorkflowBusyId] = useState(null);
  const [selectedQuestion, setSelectedQuestion] = useState(null);
  const [evaluationHistory, setEvaluationHistory] = useState([]);
  const [reviewHistory, setReviewHistory] = useState([]);
  const [publicationHistory, setPublicationHistory] = useState([]);
  const [versionHistory, setVersionHistory] = useState([]);
  const [versionCompare, setVersionCompare] = useState({ left: '', right: '' });
  const [historyLoading, setHistoryLoading] = useState(false);
  const [workflowMessage, setWorkflowMessage] = useState('');
  const [restoringVersionId, setRestoringVersionId] = useState('');
  const [quickReviewDraft, setQuickReviewDraft] = useState(null);
  const [quickReviewError, setQuickReviewError] = useState('');
  const [openedDeepLinkId, setOpenedDeepLinkId] = useState('');

  const [creatingQuestion, setCreatingQuestion] = useState(false);
  const [newQuestionType, setNewQuestionType] = useState(QUESTION_TYPES[0]?.backend || '');
  const [newContent, setNewContent] = useState('');
  const [newRawOptions, setNewRawOptions] = useState(null);
  const [newCorrectAnswer, setNewCorrectAnswer] = useState('');
  const [newExplanation, setNewExplanation] = useState('');
  const [newSubjectId, setNewSubjectId] = useState('');
  const [newDocumentId, setNewDocumentId] = useState('');
  const [newCloIds, setNewCloIds] = useState([]);
  const [creatingSaving, setCreatingSaving] = useState(false);

  const [editingDoc, setEditingDoc] = useState(null);
  const [editDocTitle, setEditDocTitle] = useState('');
  const [editDocSubjectId, setEditDocSubjectId] = useState('');
  const [savingDoc, setSavingDoc] = useState(false);

  useEffect(() => {
    const handle = setTimeout(() => setSearchTerm(searchInput.trim()), 400);
    return () => clearTimeout(handle);
  }, [searchInput]);

  const savedFilterStorageKey = useMemo(
    () => questionFilterStorageKey(user),
    [user?.email, user?.id, user?.uid],
  );

  const currentQuestionFilter = useMemo(() => ({
    statusFilter,
    typeFilter,
    documentFilter,
    subjectFilter,
    chapterFilter,
    cloFilter,
    bloomFilter,
    difficultyFilter,
    evaluationFilter,
    publicationFilter,
    searchInput,
  }), [
    statusFilter,
    typeFilter,
    documentFilter,
    subjectFilter,
    chapterFilter,
    cloFilter,
    bloomFilter,
    difficultyFilter,
    evaluationFilter,
    publicationFilter,
    searchInput,
  ]);

  const applyQuestionFilter = (filters, { selectId = '', name = '' } = {}) => {
    const next = { ...QUESTION_FILTER_DEFAULTS, ...(filters || {}) };
    setStatusFilter(next.statusFilter);
    setTypeFilter(next.typeFilter);
    setDocumentFilter(next.documentFilter);
    setSubjectFilter(next.subjectFilter);
    setChapterFilter(next.chapterFilter);
    setCloFilter(next.cloFilter);
    setBloomFilter(next.bloomFilter);
    setDifficultyFilter(next.difficultyFilter);
    setEvaluationFilter(next.evaluationFilter);
    setPublicationFilter(next.publicationFilter);
    setSearchInput(next.searchInput);
    setSearchTerm(next.searchInput.trim());
    setSelectedSavedFilterId(selectId);
    setSavedFilterName(name);
  };

  const updateSavedQuestionFilters = (items) => {
    setSavedQuestionFilters(items);
    persistSavedQuestionFilters(savedFilterStorageKey, items);
  };

  const handleSaveQuestionFilter = () => {
    const name = savedFilterName.trim();
    if (!name) {
      alert('Vui lòng nhập tên bộ lọc.');
      return;
    }
    const existing = savedQuestionFilters.find((item) => item.id === selectedSavedFilterId);
    const record = {
      id: existing?.id || makeSavedFilterId(),
      name,
      filters: currentQuestionFilter,
      updated_at: new Date().toISOString(),
    };
    const nextItems = existing
      ? savedQuestionFilters.map((item) => (item.id === existing.id ? record : item))
      : [record, ...savedQuestionFilters].slice(0, 12);
    updateSavedQuestionFilters(nextItems);
    setSelectedSavedFilterId(record.id);
    setSavedFilterName(record.name);
  };

  const handleSelectSavedQuestionFilter = (filterId) => {
    if (!filterId) {
      setSelectedSavedFilterId('');
      setSavedFilterName('');
      return;
    }
    const saved = savedQuestionFilters.find((item) => item.id === filterId);
    if (!saved) return;
    applyQuestionFilter(saved.filters, { selectId: saved.id, name: saved.name });
  };

  const handleDeleteSavedQuestionFilter = () => {
    const saved = savedQuestionFilters.find((item) => item.id === selectedSavedFilterId);
    if (!saved) return;
    if (!window.confirm(`Xóa bộ lọc "${saved.name}"?`)) return;
    updateSavedQuestionFilters(savedQuestionFilters.filter((item) => item.id !== saved.id));
    setSelectedSavedFilterId('');
    setSavedFilterName('');
  };

  const handleResetQuestionFilters = () => {
    applyQuestionFilter(QUESTION_FILTER_DEFAULTS);
  };

  useEffect(() => {
    setSavedQuestionFilters(parseSavedQuestionFilters(window.localStorage.getItem(savedFilterStorageKey)));
    setSelectedSavedFilterId('');
    setSavedFilterName('');
  }, [savedFilterStorageKey]);

  const fetchQuestions = async (search) => {
    setQuestionsLoading(true);
    setQuestionsError('');
    try {
      const result = await listQuestions({
        page: 1,
        pageSize: 100,
        search: search || undefined,
        reviewStatus: statusFilter !== 'all' ? statusFilter : undefined,
        questionType: typeFilter !== 'all-type' ? typeFilter : undefined,
        bloomLevel: bloomFilter !== 'all-bloom' ? bloomFilter : undefined,
        documentId: documentFilter !== 'all-documents' ? documentFilter : undefined,
        subjectId: subjectFilter !== 'all-subjects' ? subjectFilter : undefined,
        chapterId: chapterFilter !== 'all-chapters' ? chapterFilter : undefined,
        cloId: cloFilter !== 'all-clos' ? cloFilter : undefined,
        difficulty: difficultyFilter !== 'all-difficulties' ? difficultyFilter : undefined,
        evaluationStatus: evaluationFilter !== 'all-evaluations' ? evaluationFilter : undefined,
        publicationStatus: publicationFilter !== 'all-publications' ? publicationFilter : undefined,
      });
      setQuestions(result.items || []);
    } catch (error) {
      setQuestionsError(error.message || 'Không tải được danh sách câu hỏi');
    } finally {
      setQuestionsLoading(false);
    }
  };

  const fetchDocuments = async () => {
    if (!canManageDocuments) {
      setDocuments([]);
      setDocumentsLoading(false);
      setDocumentsError('');
      return;
    }
    setDocumentsLoading(true);
    setDocumentsError('');
    try {
      const result = await listDocuments({ page: 1, pageSize: 100 });
      setDocuments(result.items || []);
    } catch (error) {
      setDocumentsError(error.message || 'Không tải được danh sách tài liệu');
    } finally {
      setDocumentsLoading(false);
    }
  };

  const fetchSubjects = async () => {
    setSubjectsError('');
    try {
      const result = await listSubjects();
      setSubjects(result || []);
    } catch (error) {
      setSubjectsError(error.message || 'Không tải được danh mục CLO');
    }
  };

  const loadWorkflowHistory = async (question, { keepMessage = false } = {}) => {
    if (!question) return;
    setHistoryLoading(true);
    if (!keepMessage) setWorkflowMessage('');
    setVersionHistory([]);
    setVersionCompare({ left: '', right: '' });
    try {
      const [evaluations, reviews, publications, versions] = await Promise.all([
        listQuestionEvaluations(question.id),
        listQuestionReviews(question.id),
        listQuestionMoodlePublications(question.id),
        listQuestionVersions(question.id),
      ]);
      const versionItems = versions || [];
      setSelectedQuestion(question);
      setEvaluationHistory(evaluations.items || []);
      setReviewHistory(reviews.items || []);
      setPublicationHistory(publications.items || []);
      setVersionHistory(versionItems);
      setVersionCompare({
        left: versionItems[1]?.id || versionItems[0]?.id || '',
        right: versionItems[0]?.id || '',
      });
    } catch (error) {
      setWorkflowMessage(error.message || 'Không tải được lịch sử kiểm duyệt');
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    fetchQuestions(searchTerm);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    searchTerm,
    statusFilter,
    typeFilter,
    documentFilter,
    subjectFilter,
    chapterFilter,
    cloFilter,
    bloomFilter,
    difficultyFilter,
    evaluationFilter,
    publicationFilter,
  ]);

  useEffect(() => {
    fetchDocuments();
  }, [canManageDocuments]);

  useEffect(() => {
    fetchSubjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedQuestion) return;
    const fresh = questions.find((question) => question.id === selectedQuestion.id);
    if (fresh && fresh !== selectedQuestion) {
      setSelectedQuestion(fresh);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questions]);

  useEffect(() => {
    setSelectedQuestionIds((current) => current.filter((id) => questions.some((question) => question.id === id)));
  }, [questions]);

  useEffect(() => {
    const questionId = new URLSearchParams(location.search).get('questionId') || '';
    if (!questionId) {
      setOpenedDeepLinkId('');
      return;
    }
    if (openedDeepLinkId === questionId) return;
    const openLinkedQuestion = async () => {
      try {
        const localQuestion = questions.find((question) => question.id === questionId);
        const question = localQuestion || await getQuestion(questionId);
        await loadWorkflowHistory(question);
        setOpenedDeepLinkId(questionId);
      } catch (error) {
        setWorkflowMessage(error.message || 'Không mở được câu hỏi từ thông báo');
        setOpenedDeepLinkId(questionId);
      }
    };
    openLinkedQuestion();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search, questions, openedDeepLinkId]);

  const counts = useMemo(() => ({
    all: questions.length,
    DRAFT: questions.filter((q) => q.review_status === 'DRAFT').length,
    APPROVED: questions.filter((q) => q.review_status === 'APPROVED').length,
    PENDING: questions.filter((q) => q.review_status === 'PENDING').length,
    NEEDS_REVISION: questions.filter((q) => q.review_status === 'NEEDS_REVISION').length,
    REJECTED: questions.filter((q) => q.review_status === 'REJECTED').length,
  }), [questions]);

  const filtered = useMemo(() => {
    return questions.filter((q) => {
      if (statusFilter !== 'all' && q.review_status !== statusFilter) return false;
      if (typeFilter !== 'all-type') {
        const assessmentType = questionAssessmentType(q);
        if (assessmentType !== typeFilter) return false;
      }
      if (documentFilter !== 'all-documents' && questionDocumentId(q) !== documentFilter) return false;
      if (bloomFilter !== 'all-bloom' && questionBloomLevel(q) !== bloomFilter) return false;
      return true;
    });
  }, [questions, statusFilter, typeFilter, documentFilter, bloomFilter]);

  const approvedForPublication = questions.filter((q) => (
    q.review_status === 'APPROVED' && q.publication_status !== 'PUBLISHED'
  ));

  const subjectById = useMemo(() => {
    const items = new Map();
    subjects.forEach((subject) => items.set(refId(subject), subject));
    return items;
  }, [subjects]);

  const selectedFilterSubject = subjectFilter !== 'all-subjects'
    ? subjectById.get(subjectFilter)
    : null;
  const filterChapters = (selectedFilterSubject?.chapters || []).filter((chapter) => chapter.is_active !== false);
  const filterLearningOutcomes = (selectedFilterSubject?.learning_outcomes || []).filter((clo) => clo.is_active !== false);
  const questionCoverage = useMemo(() => buildQuestionCoverage({
    questions: filtered,
    subject: selectedFilterSubject,
    bloomLevels: BLOOM_LEVELS,
  }), [filtered, selectedFilterSubject]);
  const coverageScopeLabel = selectedFilterSubject
    ? selectedFilterSubject.subject_name || selectedFilterSubject.name || selectedFilterSubject.title || refId(selectedFilterSubject)
    : 'Tất cả môn đang lọc';
  const coverageSections = [
    { key: 'bloom', label: 'Bloom', rows: questionCoverage.bloom, gapCount: questionCoverage.gaps.bloom },
    { key: 'chapters', label: 'Chương', rows: questionCoverage.chapters, gapCount: questionCoverage.gaps.chapters },
    { key: 'clos', label: 'CLO', rows: questionCoverage.clos, gapCount: questionCoverage.gaps.clos },
  ];
  const selectedQuestions = useMemo(
    () => selectedQuestionsForIds(questions, selectedQuestionIds),
    [questions, selectedQuestionIds],
  );
  const selectedSubmittableQuestions = useMemo(
    () => filterSubmittableQuestions(selectedQuestions, SUBMITTABLE_REVIEW_STATUSES),
    [selectedQuestions],
  );
  const filteredQuestionIds = useMemo(() => filtered.map((question) => question.id), [filtered]);
  const allFilteredSelected = filteredQuestionIds.length > 0
    && filteredQuestionIds.every((questionId) => selectedQuestionIds.includes(questionId));
  const selectedSubjectIds = Array.from(new Set(selectedQuestions.map(questionSubjectId).filter(Boolean)));
  const bulkCloSubject = selectedSubjectIds.length === 1 ? subjectById.get(selectedSubjectIds[0]) : null;
  const bulkLearningOutcomes = (bulkCloSubject?.learning_outcomes || []).filter((clo) => clo.is_active !== false);
  const exportableQuestions = selectedQuestions.length > 0 ? selectedQuestions : filtered;
  const exportScopeLabel = selectedQuestions.length > 0
    ? `${selectedQuestions.length} đã chọn`
    : `${filtered.length} đang lọc`;

  const handleSubjectFilterChange = (value) => {
    setSubjectFilter(value);
    setChapterFilter('all-chapters');
    setCloFilter('all-clos');
  };

  const editSubject = editing ? subjectById.get(questionSubjectId(editing)) : null;
  const editLearningOutcomes = (editSubject?.learning_outcomes || []).filter((clo) => clo.is_active !== false);
  const compareLeftVersion = versionHistory.find((version) => version.id === versionCompare.left) || null;
  const compareRightVersion = versionHistory.find((version) => version.id === versionCompare.right) || null;
  const compareRows = versionDiffRows(compareLeftVersion, compareRightVersion);

  const openEdit = (item) => {
    setEditing(item);
    setEditContent(item.content || '');
    setEditRawOptions(item.question_data?.options ?? null);
    setEditCorrectAnswer(item.question_data?.correct_answer ?? '');
    setEditExplanation(item.question_data?.explanation ?? '');
    setEditCloIds(questionCloIds(item));
    setEditChangeNote('');
  };

  const closeEdit = () => {
    if (saving) return;
    setEditing(null);
    setEditCloIds([]);
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editing) return;
    if (!editContent.trim()) {
      alert('Nội dung câu hỏi không được để trống.');
      return;
    }
    const answerValidationError = validateQuestionAnswer({
      questionType: questionAssessmentType(editing),
      rawOptions: editRawOptions,
      correctAnswer: editCorrectAnswer,
    });
    if (answerValidationError) {
      alert(answerValidationError);
      return;
    }
    setSaving(true);
    try {
      await updateQuestion(editing.id, {
        expected_version: editing.current_version,
        content: editContent,
        question_data: {
          ...editing.question_data,
          options: editRawOptions,
          correct_answer: editCorrectAnswer,
          explanation: editExplanation,
        },
        clo_ids: editCloIds,
        change_note: editChangeNote.trim() || 'Question edited',
      });
      setEditing(null);
      await fetchQuestions(searchTerm);
    } catch (error) {
      alert('Cập nhật câu hỏi thất bại: ' + error.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (item) => {
    if (!window.confirm(`Xoá câu hỏi "${item.question_code}"? Hành động này sẽ lưu trữ câu hỏi và ẩn khỏi ngân hàng.`)) {
      return;
    }
    setDeletingId(item.id);
    try {
      await deleteQuestion(item.id);
      await fetchQuestions(searchTerm);
    } catch (error) {
      alert('Xoá câu hỏi thất bại: ' + error.message);
    } finally {
      setDeletingId(null);
    }
  };

  const handleDuplicateQuestion = async (item) => {
    setDuplicatingQuestionId(item.id);
    try {
      const duplicate = await duplicateQuestion(item.id);
      await fetchQuestions(searchTerm);
      setWorkflowMessage(`Đã nhân bản ${item.question_code} thành ${duplicate.question_code} ở trạng thái nháp.`);
    } catch (error) {
      alert('Nhân bản câu hỏi thất bại: ' + error.message);
    } finally {
      setDuplicatingQuestionId(null);
    }
  };

  const toggleQuestionSelection = (questionId) => {
    setSelectedQuestionIds((current) => (
      current.includes(questionId)
        ? current.filter((id) => id !== questionId)
        : [...current, questionId]
    ));
  };

  const toggleFilteredSelection = () => {
    setSelectedQuestionIds((current) => {
      const next = new Set(current);
      if (allFilteredSelected) {
        filteredQuestionIds.forEach((id) => next.delete(id));
      } else {
        filteredQuestionIds.forEach((id) => next.add(id));
      }
      return Array.from(next);
    });
  };

  const resetBulkEditDraft = () => {
    setBulkEditDraft({
      bloomLevel: '',
      difficulty: '',
      applyClo: false,
      cloIds: [],
    });
  };

  const openBulkEdit = () => {
    if (selectedQuestions.length === 0) return;
    resetBulkEditDraft();
    setBulkEditOpen(true);
  };

  const closeBulkEdit = () => {
    if (bulkActionBusy === 'edit') return;
    setBulkEditOpen(false);
  };

  const toggleBulkClo = (cloId) => {
    setBulkEditDraft((current) => ({
      ...current,
      cloIds: current.cloIds.includes(cloId)
        ? current.cloIds.filter((id) => id !== cloId)
        : [...current.cloIds, cloId],
    }));
  };

  const handleBulkSubmit = async () => {
    if (selectedSubmittableQuestions.length === 0) {
      alert('Không có câu hỏi đã chọn nào ở trạng thái có thể gửi duyệt.');
      return;
    }
    if (!window.confirm(`Gửi duyệt ${selectedSubmittableQuestions.length} câu hỏi đã chọn?`)) return;
    setBulkActionBusy('submit');
    try {
      const results = await Promise.allSettled(
        selectedSubmittableQuestions.map((question) => (
          submitQuestionForReview(question.id).then(() => question.id)
        )),
      );
      const summary = summarizeBulkSettled(results);
      const successfulIds = new Set(
        results
          .filter((result) => result.status === 'fulfilled')
          .map((result) => result.value),
      );
      setSelectedQuestionIds((current) => current.filter((id) => !successfulIds.has(id)));
      await fetchQuestions(searchTerm);
      setWorkflowMessage(`Đã gửi duyệt ${summary.success}/${selectedSubmittableQuestions.length} câu hỏi.`);
      if (summary.failed > 0) {
        alert(`Có ${summary.failed} câu gửi duyệt thất bại. Lỗi đầu tiên: ${summary.firstError}`);
      }
    } finally {
      setBulkActionBusy('');
    }
  };

  const handleBulkArchive = async () => {
    if (selectedQuestions.length === 0) return;
    if (!window.confirm(`Lưu trữ ${selectedQuestions.length} câu hỏi đã chọn?`)) return;
    setBulkActionBusy('archive');
    try {
      const results = await Promise.allSettled(
        selectedQuestions.map((question) => deleteQuestion(question.id).then(() => question.id)),
      );
      const summary = summarizeBulkSettled(results);
      const successfulIds = new Set(
        results
          .filter((result) => result.status === 'fulfilled')
          .map((result) => result.value),
      );
      setSelectedQuestionIds((current) => current.filter((id) => !successfulIds.has(id)));
      await fetchQuestions(searchTerm);
      setWorkflowMessage(`Đã lưu trữ ${summary.success}/${selectedQuestions.length} câu hỏi.`);
      if (summary.failed > 0) {
        alert(`Có ${summary.failed} câu lưu trữ thất bại. Lỗi đầu tiên: ${summary.firstError}`);
      }
    } finally {
      setBulkActionBusy('');
    }
  };

  const handleBulkEdit = async (event) => {
    event.preventDefault();
    if (bulkEditDraft.applyClo && !bulkCloSubject) {
      alert('Chỉ có thể sửa CLO hàng loạt khi các câu đã chọn thuộc cùng một môn.');
      return;
    }
    const workItems = selectedQuestions
      .map((question) => ({
        question,
        payload: buildBulkQuestionUpdatePayload(question, bulkEditDraft),
      }))
      .filter((item) => item.payload);
    if (workItems.length === 0) {
      alert('Chọn ít nhất một trường cần cập nhật.');
      return;
    }
    setBulkActionBusy('edit');
    try {
      const results = await Promise.allSettled(
        workItems.map(({ question, payload }) => (
          updateQuestion(question.id, payload).then(() => question.id)
        )),
      );
      const summary = summarizeBulkSettled(results);
      const successfulIds = new Set(
        results
          .filter((result) => result.status === 'fulfilled')
          .map((result) => result.value),
      );
      setSelectedQuestionIds((current) => current.filter((id) => !successfulIds.has(id)));
      await fetchQuestions(searchTerm);
      setWorkflowMessage(`Đã cập nhật hàng loạt ${summary.success}/${workItems.length} câu hỏi.`);
      if (summary.success > 0) {
        setBulkEditOpen(false);
      }
      if (summary.failed > 0) {
        alert(`Có ${summary.failed} câu cập nhật thất bại. Lỗi đầu tiên: ${summary.firstError}`);
      }
    } finally {
      setBulkActionBusy('');
    }
  };

  const handleQuestionBankExport = () => {
    if (exportableQuestions.length === 0) {
      alert('Không có câu hỏi nào để xuất.');
      return;
    }
    const prefix = selectedQuestions.length > 0 ? 'question-bank-selected' : 'question-bank-filtered';
    if (questionExportFormat === 'csv') {
      downloadCsv(
        timestampedCsvFilename(prefix),
        rowsToCsv(QUESTION_BANK_EXPORT_COLUMNS, exportableQuestions),
      );
    } else if (questionExportFormat === 'xlsx') {
      downloadXlsx(
        timestampedXlsxFilename(prefix),
        QUESTION_BANK_EXPORT_COLUMNS,
        exportableQuestions,
        'Question bank',
      );
    } else if (questionExportFormat === 'gift') {
      downloadTextFile(
        timestampedQuestionBankFilename(prefix, 'gift'),
        questionsToGift(exportableQuestions),
        'text/plain;charset=utf-8',
      );
    } else if (questionExportFormat === 'xml') {
      downloadTextFile(
        timestampedQuestionBankFilename(prefix, 'xml'),
        questionsToMoodleXml(exportableQuestions),
        'application/xml;charset=utf-8',
      );
    }
    setQuestionExchangeMessage(`Đã xuất ${exportableQuestions.length} câu hỏi (${QUESTION_BANK_EXPORT_FORMATS.find((item) => item.value === questionExportFormat)?.label || questionExportFormat}).`);
  };

  const handleQuestionBankImportFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    setQuestionExchangeBusy('import');
    setQuestionExchangeMessage('');
    try {
      const parsed = await parseQuestionBankImportFile(file, { subjects });
      if (parsed.errors.length > 0) {
        const preview = parsed.errors.slice(0, 6).join('\n');
        const suffix = parsed.errors.length > 6 ? `\n... và ${parsed.errors.length - 6} lỗi khác` : '';
        alert(`Không nhập được file này:\n${preview}${suffix}`);
        return;
      }
      if (parsed.items.length === 0) {
        alert('File không có câu hỏi hợp lệ để nhập.');
        return;
      }
      if (!window.confirm(`Tạo ${parsed.items.length} câu hỏi từ file "${file.name}"?`)) return;

      const results = await Promise.allSettled(
        parsed.items.map((item) => createQuestion(item.payload).then(() => item.rowNumber)),
      );
      const summary = summarizeBulkSettled(results);
      await fetchQuestions(searchTerm);
      setQuestionExchangeMessage(`Đã nhập ${summary.success}/${parsed.items.length} câu hỏi từ ${file.name}.`);
      if (summary.failed > 0) {
        alert(`Có ${summary.failed} câu hỏi nhập thất bại. Lỗi đầu tiên: ${summary.firstError}`);
      }
    } catch (error) {
      alert('Nhập ngân hàng câu hỏi thất bại: ' + error.message);
    } finally {
      setQuestionExchangeBusy('');
    }
  };

  const handleSubmitForReview = async (item) => {
    if (!SUBMITTABLE_REVIEW_STATUSES.has(item.review_status)) {
      alert('Câu hỏi này không còn ở trạng thái có thể gửi duyệt.');
      return;
    }
    setWorkflowBusyId(item.id);
    try {
      await submitQuestionForReview(item.id);
      await refreshAfterWorkflow('Đã gửi duyệt và đưa vào hàng đợi AI đánh giá.', item);
    } catch (error) {
      alert('Gửi duyệt thất bại: ' + error.message);
    } finally {
      setWorkflowBusyId(null);
    }
  };

  const handleDeleteDocument = async (doc) => {
    if (!window.confirm(`Xoá tài liệu "${doc.title}"? Hành động này sẽ lưu trữ tài liệu và ẩn khỏi danh sách.`)) {
      return;
    }
    setDeletingDocId(doc.id);
    try {
      await deleteDocument(doc.id);
      await fetchDocuments();
    } catch (error) {
      alert('Xoá tài liệu thất bại: ' + error.message);
    } finally {
      setDeletingDocId(null);
    }
  };

  const toggleDocumentJobs = async (doc) => {
    if (expandedDocumentId === doc.id) {
      setExpandedDocumentId('');
      return;
    }
    setExpandedDocumentId(doc.id);
    setDocumentJobsError(null);
    if (documentJobsById[doc.id]) return;
    setDocumentJobsLoadingId(doc.id);
    try {
      const result = await listDocumentJobs(doc.id, { limit: 12 });
      setDocumentJobsById((current) => ({
        ...current,
        [doc.id]: result.items || [],
      }));
    } catch (error) {
      setDocumentJobsError({
        documentId: doc.id,
        message: error.message || 'Không tải được lịch sử job tài liệu',
      });
    } finally {
      setDocumentJobsLoadingId('');
    }
  };

  const toggleDocumentPages = async (doc) => {
    if (expandedDocumentPagesId === doc.id) {
      setExpandedDocumentPagesId('');
      return;
    }
    setExpandedDocumentPagesId(doc.id);
    setDocumentPagesError(null);
    if (documentPagesById[doc.id]) return;
    setDocumentPagesLoadingId(doc.id);
    try {
      const result = await listDocumentPages(doc.id, { limit: 12 });
      setDocumentPagesById((current) => ({
        ...current,
        [doc.id]: result.items || [],
      }));
    } catch (error) {
      setDocumentPagesError({
        documentId: doc.id,
        message: error.message || 'Không tải được OCR pages',
      });
    } finally {
      setDocumentPagesLoadingId('');
    }
  };

  const handleOcrPageDraftChange = (pageId, value) => {
    setOcrPageDrafts((current) => ({
      ...current,
      [pageId]: value,
    }));
  };

  const handleSaveOcrPage = async (doc, page) => {
    const actionKey = `${doc.id}:${page.id}`;
    const cleanedText = ocrPageDrafts[page.id] ?? pageTextPreview(page);
    setSavingOcrPageKey(actionKey);
    try {
      const updated = await updateDocumentPage(doc.id, page.id, { cleaned_text: cleanedText });
      setDocumentPagesById((current) => ({
        ...current,
        [doc.id]: (current[doc.id] || []).map((item) => (item.id === updated.id ? updated : item)),
      }));
      setOcrPageDrafts((current) => {
        const next = { ...current };
        delete next[page.id];
        return next;
      });
    } catch (error) {
      alert('Lưu OCR page thất bại: ' + error.message);
    } finally {
      setSavingOcrPageKey('');
    }
  };

  const refreshDocumentJobState = async (documentId) => {
    setDocumentJobsLoadingId(documentId);
    setDocumentJobsError(null);
    try {
      const [documentsResult, jobsResult] = await Promise.all([
        listDocuments({ page: 1, pageSize: 100 }),
        listDocumentJobs(documentId, { limit: 12 }),
      ]);
      setDocuments(documentsResult.items || []);
      setDocumentJobsById((current) => ({
        ...current,
        [documentId]: jobsResult.items || [],
      }));
    } catch (error) {
      setDocumentJobsError({
        documentId,
        message: error.message || 'Không tải được trạng thái job tài liệu',
      });
    } finally {
      setDocumentJobsLoadingId('');
    }
  };

  const handleRetryDocumentJob = async (doc, job) => {
    const actionKey = `retry:${job.id}`;
    setDocumentJobActionKey(actionKey);
    try {
      await retryDocumentJob(doc.id, job.id);
      await refreshDocumentJobState(doc.id);
    } catch (error) {
      alert('Retry OCR job thất bại: ' + error.message);
    } finally {
      setDocumentJobActionKey('');
    }
  };

  const handleCancelDocumentJob = async (doc, job) => {
    if (!window.confirm(`Hủy job ${job.job_type || 'Document'} #${job.attempt_no || 1}?`)) return;
    const actionKey = `cancel:${job.id}`;
    setDocumentJobActionKey(actionKey);
    try {
      await cancelDocumentJob(doc.id, job.id);
      await refreshDocumentJobState(doc.id);
    } catch (error) {
      alert('Hủy job thất bại: ' + error.message);
    } finally {
      setDocumentJobActionKey('');
    }
  };

  const handleReindexDocument = async (doc) => {
    const actionKey = `reindex:${doc.id}`;
    setDocumentJobActionKey(actionKey);
    try {
      await reindexDocument(doc.id);
      setExpandedDocumentId(doc.id);
      await refreshDocumentJobState(doc.id);
    } catch (error) {
      alert('Re-index tài liệu thất bại: ' + error.message);
    } finally {
      setDocumentJobActionKey('');
    }
  };

  const newSubject = newSubjectId ? subjectById.get(newSubjectId) : null;
  const newLearningOutcomes = (newSubject?.learning_outcomes || []).filter((clo) => clo.is_active !== false);

  const openCreateQuestion = () => {
    setNewQuestionType(QUESTION_TYPES[0]?.backend || '');
    setNewContent('');
    setNewRawOptions(null);
    setNewCorrectAnswer('');
    setNewExplanation('');
    setNewSubjectId('');
    setNewDocumentId('');
    setNewCloIds([]);
    setCreatingQuestion(true);
  };

  const closeCreateQuestion = () => {
    if (creatingSaving) return;
    setCreatingQuestion(false);
  };

  const toggleNewClo = (cloId) => {
    setNewCloIds((current) => (
      current.includes(cloId) ? current.filter((value) => value !== cloId) : [...current, cloId]
    ));
  };

  const handleCreateQuestion = async (e) => {
    e.preventDefault();
    if (!newContent.trim()) {
      alert('Nội dung câu hỏi không được để trống.');
      return;
    }
    const answerValidationError = validateQuestionAnswer({
      questionType: newQuestionType,
      rawOptions: newRawOptions,
      correctAnswer: newCorrectAnswer,
    });
    if (answerValidationError) {
      alert(answerValidationError);
      return;
    }
    setCreatingSaving(true);
    try {
      await createQuestion({
        content: newContent.trim(),
        question_type: newQuestionType,
        question_data: {
          options: newRawOptions,
          correct_answer: newCorrectAnswer,
          explanation: newExplanation,
        },
        subject_id: newSubjectId || null,
        document_id: newDocumentId || null,
        clo_ids: newCloIds,
      });
      setCreatingQuestion(false);
      await fetchQuestions(searchTerm);
    } catch (error) {
      alert('Tạo câu hỏi thất bại: ' + error.message);
    } finally {
      setCreatingSaving(false);
    }
  };

  const openEditDocument = (doc) => {
    setEditingDoc(doc);
    setEditDocTitle(doc.title || '');
    setEditDocSubjectId(refId(doc.subject_id || doc.subject) || '');
  };

  const closeEditDocument = () => {
    if (savingDoc) return;
    setEditingDoc(null);
  };

  const handleSaveDocument = async (e) => {
    e.preventDefault();
    if (!editingDoc) return;
    if (!editDocTitle.trim()) {
      alert('Tên tài liệu không được để trống.');
      return;
    }
    setSavingDoc(true);
    try {
      await updateDocument(editingDoc.id, {
        title: editDocTitle.trim(),
        subject_id: editDocSubjectId || null,
      });
      setEditingDoc(null);
      await fetchDocuments();
    } catch (error) {
      alert('Cập nhật tài liệu thất bại: ' + error.message);
    } finally {
      setSavingDoc(false);
    }
  };

  const refreshAfterWorkflow = async (message, item) => {
    setWorkflowMessage(message);
    await fetchQuestions(searchTerm);
    await loadWorkflowHistory(item, { keepMessage: true });
  };

  const handleAutoEvaluate = async (item) => {
    setWorkflowBusyId(item.id);
    try {
      await autoEvaluateQuestion(item.id, {
        expected_version: item.current_version,
        fallback_to_heuristic: false,
      });
      await refreshAfterWorkflow('Đã đưa câu hỏi vào hàng đợi AI đánh giá.', item);
    } catch (error) {
      alert('Đánh giá AI thất bại: ' + error.message);
    } finally {
      setWorkflowBusyId(null);
    }
  };

  const openQuickReview = (item, decision) => {
    setQuickReviewError('');
    setQuickReviewDraft({
      question: item,
      decision,
      note: '',
      overrideReason: '',
      issueTitle: '',
      issueSeverity: 'MEDIUM',
      issueDetail: '',
    });
  };

  const submitQuickReview = async () => {
    if (!quickReviewDraft?.question) return;
    const item = quickReviewDraft.question;
    const note = quickReviewDraft.note.trim();
    const issueTitle = quickReviewDraft.issueTitle.trim();
    const issueDetail = quickReviewDraft.issueDetail.trim();
    const revisionIssues = issueTitle || issueDetail
      ? [{
        title: issueTitle || issueDetail.slice(0, 160),
        severity: quickReviewDraft.issueSeverity,
        detail: issueDetail,
      }]
      : [];
    const needsOverride = quickReviewDraft.decision === 'APPROVED' && item.evaluation_status !== 'PASSED';
    if (needsOverride && !quickReviewDraft.overrideReason.trim()) {
      setQuickReviewError('Cần ghi lý do override khi duyệt câu chưa đạt AI.');
      return;
    }
    if (quickReviewDraft.decision === 'REJECTED' && !note && revisionIssues.length === 0) {
      setQuickReviewError('Cần ghi lý do khi từ chối câu hỏi.');
      return;
    }
    if (quickReviewDraft.decision === 'NEEDS_REVISION' && revisionIssues.length === 0) {
      setQuickReviewError('Cần thêm ít nhất một lỗi cần Teacher sửa.');
      return;
    }
    const payload = {
      expected_version: item.current_version,
      decision: quickReviewDraft.decision,
      note,
      review_form: {
        checklist: QUICK_REVIEW_RUBRIC.map((rubric) => ({
          ...rubric,
          passed: quickReviewDraft.decision === 'APPROVED',
          note: '',
        })),
        overall_note: note,
        revision_issues: revisionIssues,
      },
    };
    if (needsOverride) {
      payload.override = {
        applied: true,
        reason: quickReviewDraft.overrideReason.trim(),
      };
      if (typeof item.quality_summary?.overall_score === 'number') {
        payload.override.score = item.quality_summary.overall_score;
      }
      if (item.quality_summary?.color) {
        payload.override.color = item.quality_summary.color;
      }
    }
    setWorkflowBusyId(item.id);
    setQuickReviewError('');
    try {
      await reviewQuestion(item.id, payload);
      setQuickReviewDraft(null);
      await refreshAfterWorkflow('Đã cập nhật trạng thái kiểm duyệt.', item);
    } catch (error) {
      setQuickReviewError(error.message || 'Kiểm duyệt thất bại');
    } finally {
      setWorkflowBusyId(null);
    }
  };

  const handleRestoreVersion = async (version) => {
    if (!selectedQuestion || !version) return;
    if (version.version === selectedQuestion.current_version) return;
    if (!window.confirm(`Khôi phục ${selectedQuestion.question_code} về nội dung version ${version.version}?`)) {
      return;
    }
    const classification = versionClassification(version);
    const subjectId = refId(classification.subject?.id || classification.subject);
    const chapterId = refId(classification.chapter?.id || classification.chapter);
    const questionType = normalizeQuestionType(classification.assessment_type);
    const payload = {
      expected_version: selectedQuestion.current_version,
      content: version.content,
      question_data: version.question_data || {},
      bloom_level: classification.bloom?.level || undefined,
      difficulty: classification.difficulty || undefined,
      source_chunk_ids: versionSourceChunkIds(version),
      clo_ids: (version.clos || []).map((clo) => refId(clo.id || clo)).filter(Boolean),
      change_note: `Khôi phục từ version ${version.version}`,
    };
    if (questionType) payload.question_type = questionType;
    if (subjectId) payload.subject_id = subjectId;
    if (chapterId) payload.chapter_id = chapterId;

    setRestoringVersionId(version.id);
    try {
      const updated = await updateQuestion(selectedQuestion.id, payload);
      setWorkflowMessage(`Đã tạo version ${updated.current_version} từ version ${version.version}. Cần đánh giá/review lại.`);
      await fetchQuestions(searchTerm);
      await loadWorkflowHistory(updated, { keepMessage: true });
    } catch (error) {
      setWorkflowMessage(error.message || 'Khôi phục version thất bại');
    } finally {
      setRestoringVersionId('');
    }
  };

  const handlePublishMoodle = async (item) => {
    if (item.review_status !== 'APPROVED') {
      alert('Chỉ câu hỏi đã duyệt mới được ghi mô phỏng Moodle.');
      return;
    }
    if (!window.confirm(`Ghi mô phỏng Moodle cho ${item.question_code}?`)) {
      return;
    }
    setWorkflowBusyId(item.id);
    try {
      await publishQuestionToMoodle(item.id, {
        expected_version: item.current_version,
        export_format: 'BOTH',
        mock: true,
      });
      await refreshAfterWorkflow('Đã ghi mô phỏng Moodle.', item);
    } catch (error) {
      alert('Ghi mô phỏng Moodle thất bại: ' + error.message);
    } finally {
      setWorkflowBusyId(null);
    }
  };

  const updateEditOption = (optionKey, optionValue) => {
    const entries = optionEntriesForQuestion({
      questionType: questionAssessmentType(editing),
      rawOptions: editRawOptions,
    });
    const nextEntries = entries.map((entry) => (
      entry.key === optionKey ? { ...entry, value: optionValue } : entry
    ));
    setEditRawOptions(entriesToOptions(nextEntries));
  };

  const toggleEditCorrectAnswer = (optionKey) => {
    const entries = optionEntriesForQuestion({
      questionType: questionAssessmentType(editing),
      rawOptions: editRawOptions,
    });
    const currentValues = correctAnswerValues(editCorrectAnswer);
    const hasValue = currentValues.includes(optionKey);
    const nextValues = hasValue
      ? currentValues.filter((value) => value !== optionKey)
      : [...currentValues, optionKey];
    setEditCorrectAnswer(joinCorrectValues(nextValues, entries));
  };

  const toggleEditClo = (cloId) => {
    setEditCloIds((current) => (
      current.includes(cloId)
        ? current.filter((value) => value !== cloId)
        : [...current, cloId]
    ));
  };

  const renderEditAnswerEditor = () => {
    if (!editing) return null;
    return renderChoiceEditor({
      questionType: questionAssessmentType(editing),
      rawOptions: editRawOptions,
      correctAnswer: editCorrectAnswer,
      onOptionChange: updateEditOption,
      onCorrectAnswerChange: setEditCorrectAnswer,
      onToggleCorrectAnswer: toggleEditCorrectAnswer,
      keyPrefix: `edit-${editing.id}`,
    });
  };

  return (
    <main className="manage-page">
      <section className="page-hero">
        <div className="container manage-hero-row">
          <div>
            <div className="page-hero-badge">Khu vực quản lý</div>
            <h1 className="page-hero-title">Quản lý ngân hàng câu hỏi</h1>
            <p className="page-hero-desc">
              Theo dõi, chỉnh sửa và phê duyệt câu hỏi trước khi export hoặc ghi mô phỏng Moodle.
            </p>
          </div>
          <div className="manage-hero-actions">
            <button
              type="button"
              className="btn btn--outline"
              onClick={() => setStatusFilter('PENDING')}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>
              Hàng đợi duyệt
            </button>
            <button
              type="button"
              className="btn btn--primary"
              disabled={!canReviewQuestions || approvedForPublication.length === 0}
              onClick={() => handlePublishMoodle(approvedForPublication[0])}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="17 1 21 5 17 9" /><path d="M3 11V9a4 4 0 0 1 4-4h14" /><polyline points="7 23 3 19 7 15" /><path d="M21 13v2a4 4 0 0 1-4 4H3" /></svg>
              Mô phỏng Moodle
            </button>
          </div>
        </div>
      </section>

      <section className="manage-body">
        <div className="container manage-grid">
          {/* Main column */}
          <div className="manage-main">
            <div className="stats-row">
              <button type="button" className={`stat-card ${statusFilter === 'all' ? 'stat-card--active' : ''}`} onClick={() => setStatusFilter('all')}>
                <b>{counts.all}</b>
                <span>Tổng câu hỏi</span>
              </button>
              <button type="button" className={`stat-card ${statusFilter === 'DRAFT' ? 'stat-card--active' : ''}`} onClick={() => setStatusFilter('DRAFT')}>
                <b>{counts.DRAFT}</b>
                <span>Nháp</span>
              </button>
              <button type="button" className={`stat-card ${statusFilter === 'APPROVED' ? 'stat-card--active' : ''}`} onClick={() => setStatusFilter('APPROVED')}>
                <b>{counts.APPROVED}</b>
                <span>Đã duyệt</span>
              </button>
              <button type="button" className={`stat-card ${statusFilter === 'PENDING' ? 'stat-card--active' : ''}`} onClick={() => setStatusFilter('PENDING')}>
                <b>{counts.PENDING}</b>
                <span>Chờ duyệt</span>
              </button>
              <button type="button" className={`stat-card ${statusFilter === 'NEEDS_REVISION' ? 'stat-card--active' : ''}`} onClick={() => setStatusFilter('NEEDS_REVISION')}>
                <b>{counts.NEEDS_REVISION}</b>
                <span>Cần sửa</span>
              </button>
            </div>

            <div className="coverage-panel">
              <div className="coverage-panel-header">
                <div>
                  <h3>Độ phủ ngân hàng</h3>
                  <span>{coverageScopeLabel}</span>
                </div>
                <div className="coverage-total">
                  <b>{questionCoverage.total}</b>
                  <span>{questionCoverage.approvedTotal} đã duyệt</span>
                </div>
              </div>
              <div className="coverage-grid">
                {coverageSections.map((section) => (
                  <section className="coverage-section" key={section.key}>
                    <div className="coverage-section-title">
                      <h4>{section.label}</h4>
                      <span>{section.gapCount} trống</span>
                    </div>
                    <div className="coverage-list">
                      {section.rows.length === 0 ? (
                        <span className="coverage-empty">Chưa có dữ liệu</span>
                      ) : section.rows.map((row) => (
                        <div className={`coverage-row coverage-row--${row.status}`} key={row.id}>
                          <div className="coverage-row-meta">
                            <span>{row.label}</span>
                            <strong>{row.count}</strong>
                          </div>
                          <div className="coverage-track">
                            <span style={{ '--coverage-value': `${row.percent}%` }} />
                          </div>
                          <div className="coverage-row-foot">
                            <span>{row.approved} duyệt</span>
                            {row.target_percent > 0 && <span>Mục tiêu {row.target_percent}%</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            </div>

            <div className="card list-card">
              <div className="list-card-header">
                <h3>Danh sách câu hỏi</h3>
                <div className="list-toolbar">
                  {canEditQuestions && (
                    <button type="button" className="btn btn--primary" onClick={openCreateQuestion}>
                      + Thêm câu hỏi
                    </button>
                  )}
                  {canEditQuestions && (
                    <label className={`btn btn--outline question-import-button ${questionExchangeBusy ? 'question-import-button--disabled' : ''}`}>
                      Nhập CSV/XLSX/GIFT/XML
                      <input
                        type="file"
                        accept={QUESTION_IMPORT_ACCEPT}
                        disabled={Boolean(questionExchangeBusy)}
                        onChange={handleQuestionBankImportFile}
                      />
                    </label>
                  )}
                  <select
                    className="field-select exchange-format-select"
                    value={questionExportFormat}
                    onChange={(e) => setQuestionExportFormat(e.target.value)}
                  >
                    {QUESTION_BANK_EXPORT_FORMATS.map((format) => (
                      <option key={format.value} value={format.value}>{format.label}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="btn btn--outline"
                    disabled={exportableQuestions.length === 0}
                    onClick={handleQuestionBankExport}
                  >
                    Xuất {exportScopeLabel}
                  </button>
                  <select
                    className="field-select field-select--wide"
                    value={subjectFilter}
                    onChange={(e) => handleSubjectFilterChange(e.target.value)}
                  >
                    <option value="all-subjects">Tất cả môn</option>
                    {subjects.map((subject) => (
                      <option key={refId(subject)} value={refId(subject)}>
                        {subject.name || subject.title || refId(subject)}
                      </option>
                    ))}
                  </select>
                  <select
                    className="field-select"
                    value={chapterFilter}
                    disabled={!selectedFilterSubject}
                    onChange={(e) => setChapterFilter(e.target.value)}
                  >
                    <option value="all-chapters">
                      {selectedFilterSubject ? 'Tất cả chương' : 'Chọn môn để lọc chương'}
                    </option>
                    {filterChapters.map((chapter) => (
                      <option key={refId(chapter)} value={refId(chapter)}>
                        {chapter.chapter_name || chapter.name || chapter.title || refId(chapter)}
                      </option>
                    ))}
                  </select>
                  <select
                    className="field-select"
                    value={cloFilter}
                    disabled={!selectedFilterSubject}
                    onChange={(e) => setCloFilter(e.target.value)}
                  >
                    <option value="all-clos">
                      {selectedFilterSubject ? 'Tất cả CLO' : 'Chọn môn để lọc CLO'}
                    </option>
                    {filterLearningOutcomes.map((clo) => (
                      <option key={refId(clo)} value={refId(clo)}>
                        {clo.clo_code || clo.code || refId(clo)}
                      </option>
                    ))}
                  </select>
                  <select
                    className="field-select"
                    value={typeFilter}
                    onChange={(e) => setTypeFilter(e.target.value)}
                  >
                    <option value="all-type">Tất cả loại câu hỏi</option>
                    {QUESTION_TYPES.map((type) => (
                      <option key={type.backend} value={type.backend}>{type.label}</option>
                    ))}
                  </select>
                  {canManageDocuments && (
                    <select
                      className="field-select"
                      value={documentFilter}
                      onChange={(e) => setDocumentFilter(e.target.value)}
                    >
                      <option value="all-documents">Tất cả tài liệu</option>
                      {documents.map((doc) => (
                        <option key={doc.id} value={doc.id}>{doc.title}</option>
                      ))}
                    </select>
                  )}
                  <select
                    className="field-select"
                    value={bloomFilter}
                    onChange={(e) => setBloomFilter(e.target.value)}
                  >
                    <option value="all-bloom">Tất cả Bloom</option>
                    {BLOOM_LEVELS.map((bloom) => (
                      <option key={bloom.level} value={String(bloom.level)}>
                        {bloom.label}
                      </option>
                    ))}
                  </select>
                  <select
                    className="field-select"
                    value={difficultyFilter}
                    onChange={(e) => setDifficultyFilter(e.target.value)}
                  >
                    <option value="all-difficulties">Tất cả độ khó</option>
                    {DIFFICULTIES.map((difficulty) => (
                      <option key={difficulty.value} value={difficulty.value}>{difficulty.label}</option>
                    ))}
                  </select>
                  <select
                    className="field-select"
                    value={evaluationFilter}
                    onChange={(e) => setEvaluationFilter(e.target.value)}
                  >
                    <option value="all-evaluations">Tất cả AI</option>
                    {Object.entries(EVALUATION_STATUS_LABEL).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                  <select
                    className="field-select"
                    value={publicationFilter}
                    onChange={(e) => setPublicationFilter(e.target.value)}
                  >
                    <option value="all-publications">Tất cả Moodle</option>
                    {Object.entries(PUBLICATION_STATUS_LABEL).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                  <input
                    className="field-input search-input"
                    placeholder="Tìm câu hỏi..."
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                  />
                </div>
              </div>

              <div className="saved-filter-bar">
                <select
                  className="field-select field-select--wide"
                  value={selectedSavedFilterId}
                  onChange={(event) => handleSelectSavedQuestionFilter(event.target.value)}
                >
                  <option value="">Bộ lọc đã lưu</option>
                  {savedQuestionFilters.map((filter) => (
                    <option key={filter.id} value={filter.id}>{filter.name}</option>
                  ))}
                </select>
                <input
                  className="field-input saved-filter-name"
                  placeholder="Tên bộ lọc"
                  value={savedFilterName}
                  onChange={(event) => setSavedFilterName(event.target.value)}
                />
                <button type="button" className="btn btn--outline" onClick={handleSaveQuestionFilter}>
                  Lưu bộ lọc
                </button>
                <button
                  type="button"
                  className="btn btn--outline"
                  disabled={!selectedSavedFilterId}
                  onClick={handleDeleteSavedQuestionFilter}
                >
                  Xóa
                </button>
                <button type="button" className="btn btn--outline" onClick={handleResetQuestionFilters}>
                  Đặt lại
                </button>
              </div>

              {questionExchangeMessage && (
                <p className="question-exchange-message">{questionExchangeMessage}</p>
              )}

              {canEditQuestions && (
                <div className="bulk-action-bar">
                  <label className="bulk-select-all">
                    <input
                      type="checkbox"
                      checked={allFilteredSelected}
                      disabled={filteredQuestionIds.length === 0 || Boolean(bulkActionBusy)}
                      onChange={toggleFilteredSelection}
                    />
                    <span>Chọn danh sách đang hiển thị</span>
                  </label>
                  <span className="bulk-count">{selectedQuestions.length} đã chọn</span>
                  <div className="bulk-actions">
                    <button
                      type="button"
                      className="btn btn--outline"
                      disabled={selectedQuestions.length === 0 || Boolean(bulkActionBusy)}
                      onClick={openBulkEdit}
                    >
                      Sửa hàng loạt
                    </button>
                    <button
                      type="button"
                      className="btn btn--outline"
                      disabled={selectedSubmittableQuestions.length === 0 || Boolean(bulkActionBusy)}
                      onClick={handleBulkSubmit}
                    >
                      Gửi duyệt
                    </button>
                    <button
                      type="button"
                      className="btn btn--outline btn--danger"
                      disabled={selectedQuestions.length === 0 || Boolean(bulkActionBusy)}
                      onClick={handleBulkArchive}
                    >
                      Lưu trữ
                    </button>
                  </div>
                </div>
              )}

              {questionsError && <p className="manage-error">{questionsError}</p>}

              {questionsLoading ? (
                <p className="empty-note">Đang tải danh sách câu hỏi...</p>
              ) : (
                <div className="question-list">
                  {filtered.map((item) => (
                    <article key={item.id} className="question-item">
                      <div className="question-main">
                        <div className="question-meta-row">
                          {canEditQuestions && (
                            <label className="question-select">
                              <input
                                type="checkbox"
                                checked={selectedQuestionIds.includes(item.id)}
                                onChange={() => toggleQuestionSelection(item.id)}
                                aria-label={`Chọn ${item.question_code}`}
                              />
                            </label>
                          )}
                          <span className="q-id">{item.question_code}</span>
                          <span className="q-tag">{questionTypeLabel((item.classification?.assessment_type || '').toLowerCase())}</span>
                          <span className="bloom-tag">{item.classification?.bloom?.name || '—'}</span>
                          {(item.clos || []).slice(0, 2).map((clo) => (
                            <span className="clo-tag" key={refId(clo.id || clo)}>
                              {clo.code || clo.clo_code || 'CLO'}
                            </span>
                          ))}
                          {(item.clos || []).length > 2 && (
                            <span className="source-tag">+{item.clos.length - 2} CLO</span>
                          )}
                          <span className="source-tag">Phiên bản {item.current_version}</span>
                        </div>
                        <p>{item.content}</p>
                        <div className="question-workflow-row">
                          <span className={`quality-pill ${QUALITY_COLOR_CLASS[item.quality_summary?.color] || ''}`}>
                            AI: {latestEvaluationText(item)}
                          </span>
                          <span className="publication-pill">
                            {PUBLICATION_STATUS_LABEL[item.publication_status] || item.publication_status}
                          </span>
                        </div>
                      </div>
                      <div className="question-side">
                        <span className={`status-badge ${REVIEW_STATUS_CLASS[item.review_status] || ''}`}>
                          {REVIEW_STATUS_LABEL[item.review_status] || item.review_status}
                        </span>
                        <div className="question-actions question-actions--wrap">
                          <button type="button" className="mini-action" onClick={() => loadWorkflowHistory(item)}>
                            Chi tiết
                          </button>
                          {canEditQuestions && SUBMITTABLE_REVIEW_STATUSES.has(item.review_status) && (
                            <button
                              type="button"
                              className="mini-action mini-action--approve"
                              disabled={workflowBusyId === item.id}
                              onClick={() => handleSubmitForReview(item)}
                            >
                              Gửi duyệt
                            </button>
                          )}
                          {canReviewQuestions && (
                            <>
                              <button
                                type="button"
                                className="mini-action"
                                disabled={workflowBusyId === item.id || !canQueueEvaluation(item)}
                                onClick={() => handleAutoEvaluate(item)}
                              >
                                {item.evaluation_status === 'ERROR' || item.evaluation_status === 'FAILED' || item.evaluation_status === 'STALE'
                                  ? 'Thử lại AI'
                                  : 'AI đánh giá'}
                              </button>
                              <button
                                type="button"
                                className="mini-action mini-action--approve"
                                disabled={workflowBusyId === item.id || isEvaluationBusy(item)}
                                onClick={() => openQuickReview(item, 'APPROVED')}
                              >
                                Duyệt
                              </button>
                              <button
                                type="button"
                                className="mini-action"
                                disabled={workflowBusyId === item.id}
                                onClick={() => openQuickReview(item, 'NEEDS_REVISION')}
                              >
                                Cần sửa
                              </button>
                              <button
                                type="button"
                                className="mini-action mini-action--danger"
                                disabled={workflowBusyId === item.id}
                                onClick={() => openQuickReview(item, 'REJECTED')}
                              >
                                Từ chối
                              </button>
                              <button
                                type="button"
                                className="mini-action"
                                disabled={workflowBusyId === item.id || item.review_status !== 'APPROVED' || item.publication_status === 'PUBLISHED'}
                                onClick={() => handlePublishMoodle(item)}
                              >
                                Mô phỏng
                              </button>
                            </>
                          )}
                          {canEditQuestions && (
                            <>
                              <button
                                type="button"
                                className="icon-btn"
                                title="Nhân bản"
                                disabled={duplicatingQuestionId === item.id}
                                onClick={() => handleDuplicateQuestion(item)}
                              >
                                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></svg>
                              </button>
                              <button type="button" className="icon-btn" title="Chỉnh sửa" onClick={() => openEdit(item)}>
                                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" /></svg>
                              </button>
                              <button
                                type="button"
                                className="icon-btn icon-btn--danger"
                                title="Xoá"
                                disabled={deletingId === item.id}
                                onClick={() => handleDelete(item)}
                              >
                                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6" /></svg>
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    </article>
                  ))}
                  {filtered.length === 0 && (
                    <p className="empty-note">Không có câu hỏi nào ở trạng thái này.</p>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Sidebar */}
          <aside className="manage-side">
	            {canManageDocuments && (
	              <div className="card side-card">
	                <h3>Tài liệu nguồn</h3>
	                {documentsError && <p className="manage-error">{documentsError}</p>}
	                {documentsLoading ? (
	                  <p className="side-note">Đang tải danh sách tài liệu...</p>
	                ) : (
	                  <div className="doc-list">
	                    {documents.map((d) => (
	                      <div className="doc-item" key={d.id}>
	                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
	                        <div className="doc-info">
	                          <span className="doc-name">{d.title}</span>
	                          <span className="doc-meta">
	                            {d.page_count ? `${d.page_count} trang · ` : ''}{DOC_STATUS_LABEL[d.status] || d.status}
	                          </span>
                            <div className="doc-pipeline" aria-label="Trạng thái pipeline tài liệu">
                              {documentPipelineSteps(d).map((step) => (
                                <span
                                  className={`doc-pipeline-chip doc-pipeline-chip--${pipelineStatusClass(step.status)}`}
                                  key={step.key}
                                >
                                  {step.label}: {JOB_STATUS_LABEL[step.status] || step.status}
                                </span>
                              ))}
                            </div>
                            {documentErrorMessage(d) && (
                              <span className="doc-error">
                                {d.latest_error?.job_type || 'Job'}: {documentErrorMessage(d)}
                              </span>
                            )}
                            {expandedDocumentId === d.id && (
                              <div className="doc-jobs-panel">
                                {documentJobsLoadingId === d.id ? (
                                  <span className="doc-job-note">Đang tải lịch sử job...</span>
                                ) : (
                                  <>
                                    {documentJobsError?.documentId === d.id && (
                                      <span className="doc-job-note doc-job-note--error">{documentJobsError.message}</span>
                                    )}
                                    {(documentJobsById[d.id] || []).map((job) => (
                                      <div className="doc-job-row" key={job.id}>
                                        <div>
                                          <b>{job.job_type} #{job.attempt_no || 1}</b>
                                          <span>{JOB_STATUS_LABEL[job.status] || job.status} · {job.progress ?? 0}%</span>
                                        </div>
                                        <small>{jobErrorMessage(job) || formatDateTime(job.finished_at || job.started_at || job.queued_at)}</small>
                                        <div className="doc-job-actions">
                                          <button
                                            type="button"
                                            className="icon-btn doc-job-action"
                                            title="Retry job"
                                            disabled={!canRetryDocumentJob(job) || Boolean(documentJobActionKey)}
                                            onClick={() => handleRetryDocumentJob(d, job)}
                                          >
                                            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
                                          </button>
                                          <button
                                            type="button"
                                            className="icon-btn icon-btn--danger doc-job-action"
                                            title="Hủy job"
                                            disabled={!canCancelDocumentJob(job) || Boolean(documentJobActionKey)}
                                            onClick={() => handleCancelDocumentJob(d, job)}
                                          >
                                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
                                          </button>
                                        </div>
                                      </div>
                                    ))}
                                    {documentJobsError?.documentId !== d.id && (documentJobsById[d.id] || []).length === 0 && (
                                      <span className="doc-job-note">Chưa có job nào cho tài liệu này.</span>
                                    )}
                                  </>
                                )}
                              </div>
                            )}
                            {expandedDocumentPagesId === d.id && (
                              <div className="doc-pages-panel">
                                {documentPagesLoadingId === d.id ? (
                                  <span className="doc-job-note">Đang tải OCR pages...</span>
                                ) : (
                                  <>
                                    {documentPagesError?.documentId === d.id && (
                                      <span className="doc-job-note doc-job-note--error">{documentPagesError.message}</span>
                                    )}
                                    {(documentPagesById[d.id] || []).map((page) => (
                                      <div className="doc-page-row" key={page.id}>
                                        <b>Trang {page.page_number}</b>
                                        {canEditDocumentOcr(d) ? (
                                          <>
                                            <textarea
                                              value={ocrPageDrafts[page.id] ?? pageTextPreview(page)}
                                              onChange={(event) => handleOcrPageDraftChange(page.id, event.target.value)}
                                              disabled={savingOcrPageKey === `${d.id}:${page.id}`}
                                            />
                                            <button
                                              type="button"
                                              className="doc-page-save-btn"
                                              disabled={
                                                savingOcrPageKey === `${d.id}:${page.id}`
                                                || (ocrPageDrafts[page.id] ?? pageTextPreview(page)) === pageTextPreview(page)
                                              }
                                              onClick={() => handleSaveOcrPage(d, page)}
                                            >
                                              {savingOcrPageKey === `${d.id}:${page.id}` ? 'Đang lưu' : 'Lưu OCR'}
                                            </button>
                                          </>
                                        ) : (
                                          <p>{pageTextPreview(page) || 'Chưa có nội dung OCR.'}</p>
                                        )}
                                        {(page.formula_blocks || []).length > 0 && (
                                          <small>{page.formula_blocks.length} công thức</small>
                                        )}
                                      </div>
                                    ))}
                                    {documentPagesError?.documentId !== d.id && (documentPagesById[d.id] || []).length === 0 && (
                                      <span className="doc-job-note">Chưa có OCR pages cho tài liệu này.</span>
                                    )}
                                  </>
                                )}
                              </div>
                            )}
	                        </div>
                          <button
                            type="button"
                            className="icon-btn doc-jobs-btn"
                            title="Xem lịch sử job"
                            disabled={documentJobsLoadingId === d.id}
                            onClick={() => toggleDocumentJobs(d)}
                          >
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 6h13M8 12h13M8 18h13" /><path d="M3 6h.01M3 12h.01M3 18h.01" /></svg>
                          </button>
                          <button
                            type="button"
                            className="icon-btn doc-pages-btn"
                            title="Xem OCR pages"
                            disabled={documentPagesLoadingId === d.id}
                            onClick={() => toggleDocumentPages(d)}
                          >
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16v16H4z" /><path d="M8 8h8M8 12h8M8 16h5" /></svg>
                          </button>
                          <button
                            type="button"
                            className="icon-btn doc-reindex-btn"
                            title="Re-index"
                            disabled={!canReindexDocument(d) || Boolean(documentJobActionKey)}
                            onClick={() => handleReindexDocument(d)}
                          >
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7" /><path d="M21 3v6h-6" /></svg>
                          </button>
	                        <button
	                          type="button"
	                          className="icon-btn doc-edit-btn"
	                          title="Sửa tài liệu"
	                          onClick={() => openEditDocument(d)}
	                        >
	                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" /></svg>
	                        </button>
	                        <button
	                          type="button"
	                          className="icon-btn icon-btn--danger doc-delete-btn"
	                          title="Xoá tài liệu"
	                          disabled={deletingDocId === d.id}
	                          onClick={() => handleDeleteDocument(d)}
	                        >
	                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6" /></svg>
	                        </button>
	                      </div>
	                    ))}
	                    {documents.length === 0 && (
	                      <p className="empty-note">Chưa có tài liệu nào.</p>
	                    )}
	                  </div>
	                )}
	                <button type="button" className="btn btn--outline doc-upload-btn" onClick={() => navigate('/sinh-cau-hoi')}>
	                  + Tải tài liệu mới
	                </button>
	              </div>
	            )}

            <div className="card side-card workflow-card">
              <h3>Luồng kiểm duyệt</h3>
              {!selectedQuestion ? (
                <p className="side-note">Chọn "Chi tiết" trên một câu hỏi để xem kết quả đánh giá, kiểm duyệt và mô phỏng Moodle.</p>
              ) : (
                <>
                  <div className="workflow-question-code">{selectedQuestion.question_code}</div>
                  <div className="workflow-status-grid">
                    <span>Đánh giá AI</span>
                    <b>{latestEvaluationText(selectedQuestion)}</b>
                    <span>Kiểm duyệt</span>
                    <b>{REVIEW_STATUS_LABEL[selectedQuestion.review_status] || selectedQuestion.review_status}</b>
                    <span>Moodle</span>
                    <b>{PUBLICATION_STATUS_LABEL[selectedQuestion.publication_status] || selectedQuestion.publication_status}</b>
                  </div>
                  {(selectedQuestion.clos || []).length > 0 && (
                    <div className="workflow-clo-list">
                      {selectedQuestion.clos.map((clo) => (
                        <span key={refId(clo.id || clo)}>
                          <b>{clo.code || clo.clo_code || 'CLO'}</b>
                          {clo.description ? ` - ${clo.description}` : ''}
                        </span>
                      ))}
                    </div>
                  )}
                  {workflowMessage && <p className="workflow-message">{workflowMessage}</p>}
                  {historyLoading ? (
                    <p className="side-note">Đang tải lịch sử...</p>
                  ) : (
                    <>
                      <div className="history-block version-history-block">
                        <div className="version-block-head">
                          <h4>Phiên bản</h4>
                          <span>{versionHistory.length} version</span>
                        </div>
                        {versionHistory.length === 0 ? (
                          <span className="history-empty">Chưa có lịch sử phiên bản.</span>
                        ) : (
                          <>
                            <div className="version-list">
                              {versionHistory.slice(0, 5).map((version) => (
                                <div
                                  className={`version-item ${version.version === selectedQuestion.current_version ? 'version-item--current' : ''}`}
                                  key={version.id}
                                >
                                  <div>
                                    <b>Version {version.version}</b>
                                    <span>{version.change_note || version.origin}</span>
                                    <small>{formatDateTime(version.created_at)}</small>
                                  </div>
                                  {canEditQuestions && version.version !== selectedQuestion.current_version && (
                                    <button
                                      type="button"
                                      className="mini-action"
                                      disabled={restoringVersionId === version.id}
                                      onClick={() => handleRestoreVersion(version)}
                                    >
                                      {restoringVersionId === version.id ? 'Đang khôi phục' : 'Khôi phục'}
                                    </button>
                                  )}
                                </div>
                              ))}
                            </div>
                            {versionHistory.length > 1 && (
                              <div className="version-compare">
                                <div className="version-select-row">
                                  <label>
                                    Từ
                                    <select
                                      className="field-select"
                                      value={versionCompare.left}
                                      onChange={(event) => setVersionCompare((current) => ({
                                        ...current,
                                        left: event.target.value,
                                      }))}
                                    >
                                      {versionHistory.map((version) => (
                                        <option key={version.id} value={version.id}>
                                          Version {version.version}
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                  <label>
                                    Đến
                                    <select
                                      className="field-select"
                                      value={versionCompare.right}
                                      onChange={(event) => setVersionCompare((current) => ({
                                        ...current,
                                        right: event.target.value,
                                      }))}
                                    >
                                      {versionHistory.map((version) => (
                                        <option key={version.id} value={version.id}>
                                          Version {version.version}
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                </div>
                                {compareRows.length === 0 ? (
                                  <span className="history-empty">Hai version đang chọn không khác nội dung chính.</span>
                                ) : (
                                  <div className="version-diff-list">
                                    {compareRows.map((row) => (
                                      <div className="version-diff-row" key={row.label}>
                                        <b>{row.label}</b>
                                        <span>Trước</span>
                                        <pre>{row.before}</pre>
                                        <span>Sau</span>
                                        <pre>{row.after}</pre>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                      <div className="history-block">
                        <h4>Đánh giá AI</h4>
                        {evaluationHistory.slice(0, 2).map((item) => (
                          <div className="history-item" key={item.id || item._id}>
                            <b>{formatScore(item.scores?.overall)} · {QUALITY_COLOR_LABEL[item.color] || 'Chưa phân mức'}</b>
                            <span>{item.feedback?.summary || 'Không có nhận xét'}</span>
                          </div>
                        ))}
                        {evaluationHistory.length === 0 && <span className="history-empty">Chưa có kết quả đánh giá.</span>}
                      </div>
                      <div className="history-block">
                        <h4>Kiểm duyệt</h4>
                        {reviewHistory.slice(0, 2).map((item) => (
                          <div className="history-item" key={item.id || item._id}>
                            <b>{REVIEW_STATUS_LABEL[item.decision] || item.decision}</b>
                            <span>{item.note || 'Không có ghi chú'}</span>
                          </div>
                        ))}
                        {reviewHistory.length === 0 && <span className="history-empty">Chưa có lượt kiểm duyệt.</span>}
                      </div>
                      <div className="history-block">
                        <h4>Moodle</h4>
                        {publicationHistory.slice(0, 2).map((item) => (
                          <div className="history-item" key={item.id || item._id}>
                            <b>{PUBLICATION_STATUS_LABEL[item.status] || item.status}</b>
                            <span>{item.moodle_question_ref_id || 'Đã ghi nhận trong hệ thống'}</span>
                          </div>
                        ))}
                        {publicationHistory.length === 0 && <span className="history-empty">Chưa ghi mô phỏng Moodle.</span>}
                      </div>
                    </>
                  )}
                </>
              )}
            </div>

            <div className="card side-card">
              <h3>Trạng thái mô phỏng Moodle</h3>
              <p className="side-note">
                Câu hỏi đã duyệt có thể được ghi mô phỏng Moodle trong môi trường demo.
              </p>
              <div className="moodle-status">
                <span className="moodle-dot" />
                Moodle demo: sẵn sàng ghi nhận
              </div>
            </div>
          </aside>
        </div>
      </section>

      {quickReviewDraft && (
        <div className="modal-overlay" onClick={() => setQuickReviewDraft(null)}>
          <form
            className="modal-card quick-review-modal"
            onClick={(e) => e.stopPropagation()}
            onSubmit={(event) => {
              event.preventDefault();
              submitQuickReview();
            }}
          >
            <h3 className="profile-card-title">
              {REVIEW_STATUS_LABEL[quickReviewDraft.decision] || quickReviewDraft.decision} · {quickReviewDraft.question.question_code}
            </h3>
            <label className="draft-edit-field">
              <span>Ghi chú tổng</span>
              <textarea
                className="field-input"
                rows={4}
                value={quickReviewDraft.note}
                onChange={(event) => setQuickReviewDraft((current) => ({
                  ...current,
                  note: event.target.value,
                }))}
              />
            </label>
            {quickReviewDraft.decision === 'APPROVED' && quickReviewDraft.question.evaluation_status !== 'PASSED' && (
              <label className="draft-edit-field">
                <span>Lý do override</span>
                <textarea
                  className="field-input"
                  rows={3}
                  required
                  value={quickReviewDraft.overrideReason}
                  onChange={(event) => setQuickReviewDraft((current) => ({
                    ...current,
                    overrideReason: event.target.value,
                  }))}
                />
              </label>
            )}
            {quickReviewDraft.decision !== 'APPROVED' && (
              <div className="quick-review-issue">
                <label className="draft-edit-field">
                  <span>Lỗi cần Teacher sửa</span>
                  <input
                    className="field-input"
                    value={quickReviewDraft.issueTitle}
                    onChange={(event) => setQuickReviewDraft((current) => ({
                      ...current,
                      issueTitle: event.target.value,
                    }))}
                    placeholder="Ví dụ: Đáp án chưa khớp nguồn"
                  />
                </label>
                <label className="draft-edit-field">
                  <span>Mức độ</span>
                  <select
                    className="field-select"
                    value={quickReviewDraft.issueSeverity}
                    onChange={(event) => setQuickReviewDraft((current) => ({
                      ...current,
                      issueSeverity: event.target.value,
                    }))}
                  >
                    <option value="LOW">Nhẹ</option>
                    <option value="MEDIUM">Vừa</option>
                    <option value="HIGH">Nghiêm trọng</option>
                  </select>
                </label>
                <label className="draft-edit-field">
                  <span>Chi tiết</span>
                  <textarea
                    className="field-input"
                    rows={3}
                    value={quickReviewDraft.issueDetail}
                    onChange={(event) => setQuickReviewDraft((current) => ({
                      ...current,
                      issueDetail: event.target.value,
                    }))}
                  />
                </label>
              </div>
            )}
            {quickReviewError && <p className="manage-error">{quickReviewError}</p>}
            <div className="modal-actions">
              <button type="button" className="btn btn--outline" onClick={() => setQuickReviewDraft(null)}>
                Hủy
              </button>
              <button type="submit" className="btn btn--primary" disabled={workflowBusyId === quickReviewDraft.question.id}>
                Gửi review
              </button>
            </div>
          </form>
        </div>
      )}

      {bulkEditOpen && (
        <div className="modal-overlay" onClick={closeBulkEdit}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={handleBulkEdit}>
            <h3 className="profile-card-title">Sửa hàng loạt {selectedQuestions.length} câu hỏi</h3>

            <div className="field-group">
              <label className="field-label">Mức Bloom</label>
              <select
                className="field-select"
                value={bulkEditDraft.bloomLevel}
                onChange={(e) => setBulkEditDraft((current) => ({ ...current, bloomLevel: e.target.value }))}
              >
                <option value="">Không đổi Bloom</option>
                {BLOOM_LEVELS.map((bloom) => (
                  <option key={bloom.level} value={String(bloom.level)}>
                    {bloom.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="field-group">
              <label className="field-label">Độ khó</label>
              <select
                className="field-select"
                value={bulkEditDraft.difficulty}
                onChange={(e) => setBulkEditDraft((current) => ({ ...current, difficulty: e.target.value }))}
              >
                <option value="">Không đổi độ khó</option>
                {DIFFICULTIES.map((difficulty) => (
                  <option key={difficulty.value} value={difficulty.value}>{difficulty.label}</option>
                ))}
              </select>
            </div>

            <div className="field-group">
              <label className="clo-option bulk-clo-toggle">
                <input
                  type="checkbox"
                  checked={bulkEditDraft.applyClo}
                  disabled={!bulkCloSubject}
                  onChange={(e) => setBulkEditDraft((current) => ({
                    ...current,
                    applyClo: e.target.checked,
                    cloIds: e.target.checked ? current.cloIds : [],
                  }))}
                />
                <span>
                  <b>Cập nhật CLO</b>
                  {bulkCloSubject
                    ? (bulkCloSubject.subject_name || bulkCloSubject.name || refId(bulkCloSubject))
                    : 'Chỉ khả dụng khi các câu cùng môn'}
                </span>
              </label>
              {bulkEditDraft.applyClo && bulkLearningOutcomes.length > 0 && (
                <div className="clo-option-list">
                  {bulkLearningOutcomes.map((clo) => {
                    const cloId = refId(clo);
                    return (
                      <label className="clo-option" key={cloId}>
                        <input
                          type="checkbox"
                          checked={bulkEditDraft.cloIds.includes(cloId)}
                          onChange={() => toggleBulkClo(cloId)}
                        />
                        <span>
                          <b>{clo.clo_code || clo.code}</b>
                          {clo.description}
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
              {bulkEditDraft.applyClo && bulkLearningOutcomes.length === 0 && (
                <p className="clo-empty">Môn này chưa có CLO trong danh mục.</p>
              )}
            </div>

            <div className="modal-actions">
              <button type="button" className="btn btn--outline" onClick={closeBulkEdit} disabled={bulkActionBusy === 'edit'}>
                Huỷ
              </button>
              <button type="submit" className="btn btn--primary" disabled={bulkActionBusy === 'edit'}>
                {bulkActionBusy === 'edit' ? 'Đang cập nhật...' : 'Cập nhật hàng loạt'}
              </button>
            </div>
          </form>
        </div>
      )}

      {editing && (
        <div className="modal-overlay" onClick={closeEdit}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={handleSaveEdit}>
            <h3 className="profile-card-title">Chỉnh sửa câu hỏi {editing.question_code}</h3>

            <div className="field-group">
              <label className="field-label">Nội dung câu hỏi</label>
              <textarea
                className="field-input"
                rows={3}
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
              />
            </div>

            <div className="field-group">
              <label className="field-label">Lựa chọn và đáp án</label>
              {renderEditAnswerEditor()}
            </div>

            <div className="field-group">
              <label className="field-label">Chuẩn đầu ra (CLO)</label>
              {subjectsError && <p className="manage-error">{subjectsError}</p>}
              {editLearningOutcomes.length > 0 ? (
                <div className="clo-option-list">
                  {editLearningOutcomes.map((clo) => {
                    const cloId = refId(clo);
                    return (
                      <label className="clo-option" key={cloId}>
                        <input
                          type="checkbox"
                          checked={editCloIds.includes(cloId)}
                          onChange={() => toggleEditClo(cloId)}
                        />
                        <span>
                          <b>{clo.clo_code || clo.code}</b>
                          {clo.description}
                        </span>
                      </label>
                    );
                  })}
                </div>
              ) : (
                <p className="clo-empty">Môn hiện tại chưa có CLO trong danh mục.</p>
              )}
            </div>

            <div className="field-group">
              <label className="field-label">Giải thích</label>
              <textarea
                className="field-input"
                rows={2}
                value={editExplanation}
                onChange={(e) => setEditExplanation(e.target.value)}
              />
            </div>

            <div className="field-group">
              <label className="field-label">Ghi chú thay đổi</label>
              <input
                className="field-input"
                placeholder="Question edited"
                value={editChangeNote}
                onChange={(e) => setEditChangeNote(e.target.value)}
              />
            </div>

            <div className="modal-actions">
              <button type="button" className="btn btn--outline" onClick={closeEdit} disabled={saving}>
                Huỷ
              </button>
              <button type="submit" className="btn btn--primary" disabled={saving}>
                {saving ? 'Đang lưu...' : 'Lưu thay đổi'}
              </button>
            </div>
          </form>
        </div>
      )}

      {creatingQuestion && (
        <div className="modal-overlay" onClick={closeCreateQuestion}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={handleCreateQuestion}>
            <h3 className="profile-card-title">Thêm câu hỏi thủ công</h3>

            <div className="field-group">
              <label className="field-label">Loại câu hỏi</label>
              <select
                className="field-select"
                value={newQuestionType}
                onChange={(e) => {
                  setNewQuestionType(e.target.value);
                  setNewRawOptions(null);
                  setNewCorrectAnswer('');
                }}
              >
                {QUESTION_TYPES.map((type) => (
                  <option key={type.backend} value={type.backend}>{type.label}</option>
                ))}
              </select>
            </div>

            <div className="field-group">
              <label className="field-label">Nội dung câu hỏi</label>
              <textarea
                className="field-input"
                rows={3}
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
              />
            </div>

            <div className="field-group">
              <label className="field-label">Lựa chọn và đáp án</label>
              {renderChoiceEditor({
                questionType: newQuestionType,
                rawOptions: newRawOptions,
                correctAnswer: newCorrectAnswer,
                onOptionChange: (key, value) => {
                  const entries = optionEntriesForQuestion({ questionType: newQuestionType, rawOptions: newRawOptions });
                  const nextEntries = entries.map((entry) => (entry.key === key ? { ...entry, value } : entry));
                  setNewRawOptions(entriesToOptions(nextEntries));
                },
                onCorrectAnswerChange: setNewCorrectAnswer,
                onToggleCorrectAnswer: (key) => {
                  const entries = optionEntriesForQuestion({ questionType: newQuestionType, rawOptions: newRawOptions });
                  const currentValues = correctAnswerValues(newCorrectAnswer);
                  const nextValues = currentValues.includes(key)
                    ? currentValues.filter((value) => value !== key)
                    : [...currentValues, key];
                  setNewCorrectAnswer(joinCorrectValues(nextValues, entries));
                },
                keyPrefix: 'new',
              })}
            </div>

            <div className="field-group">
              <label className="field-label">Môn học</label>
              <select
                className="field-select"
                value={newSubjectId}
                onChange={(e) => {
                  setNewSubjectId(e.target.value);
                  setNewCloIds([]);
                }}
              >
                <option value="">Không chọn</option>
                {subjects.map((subject) => (
                  <option key={refId(subject)} value={refId(subject)}>{subject.name || subject.title || refId(subject)}</option>
                ))}
              </select>
            </div>

            {newSubjectId && (
              <div className="field-group">
                <label className="field-label">Chuẩn đầu ra (CLO)</label>
                {newLearningOutcomes.length > 0 ? (
                  <div className="clo-option-list">
                    {newLearningOutcomes.map((clo) => {
                      const cloId = refId(clo);
                      return (
                        <label className="clo-option" key={cloId}>
                          <input
                            type="checkbox"
                            checked={newCloIds.includes(cloId)}
                            onChange={() => toggleNewClo(cloId)}
                          />
                          <span>
                            <b>{clo.clo_code || clo.code}</b>
                            {clo.description}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                ) : (
                  <p className="clo-empty">Môn này chưa có CLO trong danh mục.</p>
                )}
              </div>
            )}

            {canManageDocuments && (
              <div className="field-group">
                <label className="field-label">Tài liệu nguồn (tuỳ chọn)</label>
                <select
                  className="field-select"
                  value={newDocumentId}
                  onChange={(e) => setNewDocumentId(e.target.value)}
                >
                  <option value="">Không chọn</option>
                  {documents.map((doc) => (
                    <option key={doc.id} value={doc.id}>{doc.title}</option>
                  ))}
                </select>
              </div>
            )}

            <div className="field-group">
              <label className="field-label">Giải thích</label>
              <textarea
                className="field-input"
                rows={2}
                value={newExplanation}
                onChange={(e) => setNewExplanation(e.target.value)}
              />
            </div>

            <div className="modal-actions">
              <button type="button" className="btn btn--outline" onClick={closeCreateQuestion} disabled={creatingSaving}>
                Huỷ
              </button>
              <button type="submit" className="btn btn--primary" disabled={creatingSaving}>
                {creatingSaving ? 'Đang tạo...' : 'Tạo câu hỏi'}
              </button>
            </div>
          </form>
        </div>
      )}

      {editingDoc && (
        <div className="modal-overlay" onClick={closeEditDocument}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={handleSaveDocument}>
            <h3 className="profile-card-title">Sửa tài liệu</h3>

            <div className="field-group">
              <label className="field-label">Tên tài liệu</label>
              <input
                className="field-input"
                value={editDocTitle}
                onChange={(e) => setEditDocTitle(e.target.value)}
              />
            </div>

            <div className="field-group">
              <label className="field-label">Môn học</label>
              <select
                className="field-select"
                value={editDocSubjectId}
                onChange={(e) => setEditDocSubjectId(e.target.value)}
              >
                <option value="">Không chọn</option>
                {subjects.map((subject) => (
                  <option key={refId(subject)} value={refId(subject)}>{subject.name || subject.title || refId(subject)}</option>
                ))}
              </select>
            </div>

            <div className="modal-actions">
              <button type="button" className="btn btn--outline" onClick={closeEditDocument} disabled={savingDoc}>
                Huỷ
              </button>
              <button type="submit" className="btn btn--primary" disabled={savingDoc}>
                {savingDoc ? 'Đang lưu...' : 'Lưu thay đổi'}
              </button>
            </div>
          </form>
        </div>
      )}
    </main>
  );
}

export default ManagePage;
