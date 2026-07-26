import React, { useContext, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  autoEvaluateQuestion,
  deleteQuestion,
  listQuestionEvaluations,
  listQuestionMoodlePublications,
  listQuestionReviews,
  listQuestions,
  publishQuestionToMoodle,
  reviewQuestion,
  submitQuestionForReview,
  updateQuestion,
} from '../api/questions';
import { deleteDocument, listDocuments } from '../api/documents';
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

const EVALUATION_STATUS_LABEL = {
  NOT_STARTED: 'Chưa đánh giá',
  PROCESSING: 'Đang đánh giá',
  PASSED: 'Đạt',
  FAILED: 'Không đạt',
};

const PUBLICATION_STATUS_LABEL = {
  NOT_PUBLISHED: 'Chưa xuất',
  PUBLISHED: 'Đã xuất Moodle',
  STALE: 'Cần xuất lại',
  FAILED: 'Xuất lỗi',
};

const QUALITY_COLOR_CLASS = {
  GREEN: 'quality--green',
  YELLOW: 'quality--yellow',
  RED: 'quality--red',
};

const SUBMITTABLE_REVIEW_STATUSES = new Set(['DRAFT', 'NEEDS_REVISION']);

function formatScore(value) {
  return typeof value === 'number' ? value.toFixed(2) : '—';
}

function latestEvaluationText(item) {
  const quality = item.quality_summary || {};
  if (!quality.overall_score && quality.overall_score !== 0) {
    return EVALUATION_STATUS_LABEL[item.evaluation_status] || item.evaluation_status;
  }
  return `${formatScore(quality.overall_score)} · ${quality.color || 'N/A'}`;
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

function ManagePage() {
  const navigate = useNavigate();
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
  const [subjects, setSubjects] = useState([]);
  const [subjectsError, setSubjectsError] = useState('');

  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all-type');
  const [documentFilter, setDocumentFilter] = useState('all-documents');
  const [bloomFilter, setBloomFilter] = useState('all-bloom');
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  const [editing, setEditing] = useState(null);
  const [editContent, setEditContent] = useState('');
  const [editRawOptions, setEditRawOptions] = useState(null);
  const [editCorrectAnswer, setEditCorrectAnswer] = useState('');
  const [editExplanation, setEditExplanation] = useState('');
  const [editCloIds, setEditCloIds] = useState([]);
  const [editChangeNote, setEditChangeNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [deletingDocId, setDeletingDocId] = useState(null);
  const [workflowBusyId, setWorkflowBusyId] = useState(null);
  const [selectedQuestion, setSelectedQuestion] = useState(null);
  const [evaluationHistory, setEvaluationHistory] = useState([]);
  const [reviewHistory, setReviewHistory] = useState([]);
  const [publicationHistory, setPublicationHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [workflowMessage, setWorkflowMessage] = useState('');

  useEffect(() => {
    const handle = setTimeout(() => setSearchTerm(searchInput.trim()), 400);
    return () => clearTimeout(handle);
  }, [searchInput]);

  const fetchQuestions = async (search) => {
    setQuestionsLoading(true);
    setQuestionsError('');
    try {
      const result = await listQuestions({ page: 1, pageSize: 100, search: search || undefined });
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
    try {
      const [evaluations, reviews, publications] = await Promise.all([
        listQuestionEvaluations(question.id),
        listQuestionReviews(question.id),
        listQuestionMoodlePublications(question.id),
      ]);
      setSelectedQuestion(question);
      setEvaluationHistory(evaluations.items || []);
      setReviewHistory(reviews.items || []);
      setPublicationHistory(publications.items || []);
    } catch (error) {
      setWorkflowMessage(error.message || 'Không tải được lịch sử kiểm duyệt');
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    fetchQuestions(searchTerm);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchTerm]);

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

  const editSubject = editing ? subjectById.get(questionSubjectId(editing)) : null;
  const editLearningOutcomes = (editSubject?.learning_outcomes || []).filter((clo) => clo.is_active !== false);

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

  const handleSubmitForReview = async (item) => {
    if (!SUBMITTABLE_REVIEW_STATUSES.has(item.review_status)) {
      alert('Câu hỏi này không còn ở trạng thái có thể gửi duyệt.');
      return;
    }
    setWorkflowBusyId(item.id);
    try {
      await submitQuestionForReview(item.id);
      await refreshAfterWorkflow('Đã gửi câu hỏi sang hàng đợi duyệt.', item);
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
      });
      await refreshAfterWorkflow('Đã chạy AI evaluation cho câu hỏi.', item);
    } catch (error) {
      alert('AI evaluation thất bại: ' + error.message);
    } finally {
      setWorkflowBusyId(null);
    }
  };

  const handleReview = async (item, decision) => {
    const labels = {
      APPROVED: 'duyệt',
      NEEDS_REVISION: 'yêu cầu sửa',
      REJECTED: 'từ chối',
    };
    const note = window.prompt(`Ghi chú ${labels[decision]} câu hỏi ${item.question_code}:`, '');
    if (note === null) return;
    const payload = {
      expected_version: item.current_version,
      decision,
      note,
    };
    if (decision === 'APPROVED' && item.evaluation_status !== 'PASSED') {
      const reason = window.prompt('Câu hỏi chưa đạt AI evaluation. Nhập lý do override để vẫn duyệt:', '');
      if (!reason?.trim()) return;
      payload.override = {
        applied: true,
        score: item.quality_summary?.overall_score ?? 0.8,
        color: item.quality_summary?.color || 'YELLOW',
        reason: reason.trim(),
      };
    }
    setWorkflowBusyId(item.id);
    try {
      await reviewQuestion(item.id, payload);
      await refreshAfterWorkflow('Đã cập nhật trạng thái kiểm duyệt.', item);
    } catch (error) {
      alert('Kiểm duyệt thất bại: ' + error.message);
    } finally {
      setWorkflowBusyId(null);
    }
  };

  const handlePublishMoodle = async (item) => {
    if (item.review_status !== 'APPROVED') {
      alert('Chỉ câu hỏi đã duyệt mới được đồng bộ Moodle.');
      return;
    }
    if (!window.confirm(`Ghi nhận đồng bộ Moodle cho ${item.question_code}?`)) {
      return;
    }
    setWorkflowBusyId(item.id);
    try {
      await publishQuestionToMoodle(item.id, {
        expected_version: item.current_version,
        mock: true,
      });
      await refreshAfterWorkflow('Đã ghi nhận mock Moodle publication.', item);
    } catch (error) {
      alert('Đồng bộ Moodle thất bại: ' + error.message);
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
    const questionType = questionAssessmentType(editing);
    const entries = optionEntriesForQuestion({
      questionType,
      rawOptions: editRawOptions,
    });

    if (SINGLE_CHOICE_TYPES.has(questionType)) {
      return (
        <div className="draft-option-editor">
          {entries.map((entry) => (
            <label className="draft-option-row" key={entry.key}>
              <input
                type="radio"
                name={`edit-answer-${editing.id}`}
                checked={editCorrectAnswer === entry.key}
                onChange={() => setEditCorrectAnswer(entry.key)}
              />
              <span className="draft-option-key">{entry.key}</span>
              <input
                className="field-input"
                value={entry.value}
                onChange={(event) => updateEditOption(entry.key, event.target.value)}
              />
            </label>
          ))}
        </div>
      );
    }

    if (MULTI_CHOICE_TYPES.has(questionType)) {
      const selectedAnswers = correctAnswerValues(editCorrectAnswer);
      return (
        <div className="draft-option-editor">
          {entries.map((entry) => (
            <label className="draft-option-row" key={entry.key}>
              <input
                type="checkbox"
                checked={selectedAnswers.includes(entry.key)}
                onChange={() => toggleEditCorrectAnswer(entry.key)}
              />
              <span className="draft-option-key">{entry.key}</span>
              <input
                className="field-input"
                value={entry.value}
                onChange={(event) => updateEditOption(entry.key, event.target.value)}
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
                onChange={(event) => updateEditOption(entry.key, event.target.value)}
              />
            </label>
          ))}
          <label className="draft-edit-field">
            <span>Đáp án đúng</span>
            <input
              className="field-input"
              value={editCorrectAnswer}
              onChange={(event) => setEditCorrectAnswer(event.target.value)}
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
          value={editCorrectAnswer}
          onChange={(event) => setEditCorrectAnswer(event.target.value)}
        />
      </label>
    );
  };

  return (
    <main className="manage-page">
      <section className="page-hero">
        <div className="container manage-hero-row">
          <div>
            <div className="page-hero-badge">Admin Dashboard</div>
            <h1 className="page-hero-title">Quản lý ngân hàng câu hỏi</h1>
            <p className="page-hero-desc">
              Theo dõi, chỉnh sửa và phê duyệt câu hỏi trước khi đồng bộ vào ngân hàng đề thi trên Moodle.
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
              Đồng bộ Moodle
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

            <div className="card list-card">
              <div className="list-card-header">
                <h3>Danh sách câu hỏi</h3>
                <div className="list-toolbar">
                  <select className="field-select" defaultValue="ctdl">
                    <option value="ctdl">Cấu trúc dữ liệu</option>
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
                  <input
                    className="field-input search-input"
                    placeholder="Tìm câu hỏi..."
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                  />
                </div>
              </div>

              {questionsError && <p className="manage-error">{questionsError}</p>}

              {questionsLoading ? (
                <p className="empty-note">Đang tải danh sách câu hỏi...</p>
              ) : (
                <div className="question-list">
                  {filtered.map((item) => (
                    <article key={item.id} className="question-item">
                      <div className="question-main">
                        <div className="question-meta-row">
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
                          <span className="source-tag">v{item.current_version}</span>
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
                                disabled={workflowBusyId === item.id}
                                onClick={() => handleAutoEvaluate(item)}
                              >
                                AI đánh giá
                              </button>
                              <button
                                type="button"
                                className="mini-action mini-action--approve"
                                disabled={workflowBusyId === item.id}
                                onClick={() => handleReview(item, 'APPROVED')}
                              >
                                Duyệt
                              </button>
                              <button
                                type="button"
                                className="mini-action"
                                disabled={workflowBusyId === item.id}
                                onClick={() => handleReview(item, 'NEEDS_REVISION')}
                              >
                                Cần sửa
                              </button>
                              <button
                                type="button"
                                className="mini-action mini-action--danger"
                                disabled={workflowBusyId === item.id}
                                onClick={() => handleReview(item, 'REJECTED')}
                              >
                                Từ chối
                              </button>
                              <button
                                type="button"
                                className="mini-action"
                                disabled={workflowBusyId === item.id || item.review_status !== 'APPROVED' || item.publication_status === 'PUBLISHED'}
                                onClick={() => handlePublishMoodle(item)}
                              >
                                Moodle
                              </button>
                            </>
                          )}
                          {canEditQuestions && (
                            <>
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
	                        </div>
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
                <p className="side-note">Chọn "Chi tiết" trên một câu hỏi để xem evaluation, review và Moodle publication.</p>
              ) : (
                <>
                  <div className="workflow-question-code">{selectedQuestion.question_code}</div>
                  <div className="workflow-status-grid">
                    <span>AI</span>
                    <b>{latestEvaluationText(selectedQuestion)}</b>
                    <span>Review</span>
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
                      <div className="history-block">
                        <h4>AI evaluation</h4>
                        {evaluationHistory.slice(0, 2).map((item) => (
                          <div className="history-item" key={item.id || item._id}>
                            <b>{formatScore(item.scores?.overall)} · {item.color}</b>
                            <span>{item.feedback?.summary || 'Không có nhận xét'}</span>
                          </div>
                        ))}
                        {evaluationHistory.length === 0 && <span className="history-empty">Chưa có evaluation.</span>}
                      </div>
                      <div className="history-block">
                        <h4>Reviewer</h4>
                        {reviewHistory.slice(0, 2).map((item) => (
                          <div className="history-item" key={item.id || item._id}>
                            <b>{REVIEW_STATUS_LABEL[item.decision] || item.decision}</b>
                            <span>{item.note || 'Không có ghi chú'}</span>
                          </div>
                        ))}
                        {reviewHistory.length === 0 && <span className="history-empty">Chưa có review.</span>}
                      </div>
                      <div className="history-block">
                        <h4>Moodle</h4>
                        {publicationHistory.slice(0, 2).map((item) => (
                          <div className="history-item" key={item.id || item._id}>
                            <b>{item.status}</b>
                            <span>{item.moodle_question_ref_id || item.idempotency_key}</span>
                          </div>
                        ))}
                        {publicationHistory.length === 0 && <span className="history-empty">Chưa xuất Moodle.</span>}
                      </div>
                    </>
                  )}
                </>
              )}
            </div>

            <div className="card side-card">
              <h3>Trạng thái Moodle</h3>
              <p className="side-note">
                Câu hỏi đã duyệt có thể được ghi nhận publication mock vào `moodle_publications` để demo luồng xuất bản.
              </p>
              <div className="moodle-status">
                <span className="moodle-dot" />
                Mock Moodle: sẵn sàng ghi nhận
              </div>
            </div>
          </aside>
        </div>
      </section>

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
    </main>
  );
}

export default ManagePage;
