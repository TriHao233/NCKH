import React, { useContext, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  autoEvaluateQuestion,
  createQuestion,
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
import { deleteDocument, listDocuments, updateDocument } from '../api/documents';
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

const SUBMITTABLE_REVIEW_STATUSES = new Set(['DRAFT', 'NEEDS_REVISION']);

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
      const reason = window.prompt('Câu hỏi chưa đạt đánh giá AI. Nhập lý do duyệt thủ công:', '');
      if (!reason?.trim()) return;
      payload.override = {
        applied: true,
        reason: reason.trim(),
      };
      if (typeof item.quality_summary?.overall_score === 'number') {
        payload.override.score = item.quality_summary.overall_score;
      }
      if (item.quality_summary?.color) {
        payload.override.color = item.quality_summary.color;
      }
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

            <div className="card list-card">
              <div className="list-card-header">
                <h3>Danh sách câu hỏi</h3>
                <div className="list-toolbar">
                  {canEditQuestions && (
                    <button type="button" className="btn btn--primary" onClick={openCreateQuestion}>
                      + Thêm câu hỏi
                    </button>
                  )}
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
                                Mô phỏng
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
