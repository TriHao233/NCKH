import React, { useEffect, useRef, useState } from 'react';
import { chunkDocument } from '../api/chunk';
import { listDocuments } from '../api/documents';
import { enqueueGenerateQuestions, getGenerateStatus } from '../api/generate';
import { getOcrStatus, uploadOcrPdf } from '../api/ocr';
import { deleteQuestion, updateQuestion } from '../api/questions';
import {
  BLOOM_LEVELS,
  QUESTION_TYPES,
  bloomLevelLabel,
  questionTypeLabel,
  toBackendBloomLevel,
  toBackendQuestionType,
} from '../constants/generationEnums';
import { pollJob } from '../hooks/useJobPoll';
import { formatChoices, mapGeneratedQuestions } from '../utils/mapGeneratedQuestion';
import {
  SINGLE_CHOICE_TYPES,
  MULTI_CHOICE_TYPES,
  correctAnswerValues,
  entriesToOptions,
  joinCorrectValues,
  optionEntriesForQuestion as optionEntriesForDraft,
  validateQuestionAnswer,
} from '../utils/questionOptions';
import '../css/GeneratePage.css';

const PHASE_LABELS = {
  idle: 'Sẵn sàng',
  uploading: 'Đang tải tài liệu lên...',
  ocr_queued: 'OCR đã vào hàng đợi',
  ocr_processing: 'Đang OCR tài liệu...',
  chunking: 'Đang index / chunk tài liệu...',
  generate_queued: 'Sinh câu hỏi đã vào hàng đợi',
  generate_processing: 'Đang sinh câu hỏi bằng AI...',
  completed: 'Hoàn tất',
  failed: 'Thất bại',
};

const MAX_TOTAL_QUESTIONS = 20;

function shortId(id) {
  if (!id) return '';
  return id.length > 8 ? `${id.slice(0, 8)}...` : id;
}

function shortCode(code) {
  if (!code) return 'Q';
  return code.length > 18 ? `${code.slice(0, 12)}...${code.slice(-4)}` : code;
}

function normalizeCount(value) {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) return 1;
  return Math.min(10, Math.max(1, Math.trunc(parsed)));
}

function createPlanItem(overrides = {}) {
  const fallbackId = `plan-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return {
    id: globalThis.crypto?.randomUUID?.() || fallbackId,
    questionTypeId: 'mcq',
    bloomId: 'understand',
    count: 1,
    ...overrides,
  };
}

function createInitialPlan() {
  return [createPlanItem({ count: 5 })];
}

function documentPipeline(document) {
  return document?.pipeline_summary || {};
}

function normalizeStatus(status) {
  return String(status || '').toUpperCase();
}

function isUnavailableDocument(document) {
  const pipeline = documentPipeline(document);
  const blockedStatuses = new Set(['FAILED', 'CANCELLED', 'ARCHIVED']);
  return (
    blockedStatuses.has(normalizeStatus(document?.status))
    || blockedStatuses.has(normalizeStatus(pipeline.ocr_status))
    || blockedStatuses.has(normalizeStatus(pipeline.chunk_status))
    || blockedStatuses.has(normalizeStatus(pipeline.index_status))
  );
}

function isDocumentOcrReady(document) {
  if (isUnavailableDocument(document)) return false;
  const pipeline = documentPipeline(document);
  return (
    normalizeStatus(document?.status) === 'READY' ||
    normalizeStatus(pipeline.ocr_status) === 'COMPLETED' ||
    Boolean(document?.current_processing?.ocr_job_id && Number(document?.page_count) > 0)
  );
}

function isDocumentIndexed(document) {
  if (isUnavailableDocument(document)) return false;
  const pipeline = documentPipeline(document);
  return (
    normalizeStatus(document?.status) === 'READY' ||
    (normalizeStatus(pipeline.chunk_status) === 'COMPLETED' && normalizeStatus(pipeline.index_status) === 'COMPLETED')
  );
}

function reusableDocumentLabel(document) {
  const pages = document.page_count ? `${document.page_count} trang` : 'chưa rõ số trang';
  const pipeline = documentPipeline(document);
  const state = isDocumentIndexed(document)
    ? 'đã index'
    : normalizeStatus(pipeline.ocr_status) === 'COMPLETED'
      ? 'đã OCR'
      : document.status;
  return `${document.title} (${pages}, ${state})`;
}

function validateDraftBeforeSave(draft) {
  return validateQuestionAnswer({
    questionType: draft.questionType,
    rawOptions: draft.rawOptions,
    correctAnswer: draft.correctAnswer,
  });
}

function mergeUpdatedDraft(draft, updatedQuestion) {
  const questionData = updatedQuestion.question_data || {};
  const rawOptions = questionData.options ?? draft.rawOptions;
  const correctAnswer = questionData.correct_answer ?? draft.correctAnswer;

  return {
    ...draft,
    persistedId: updatedQuestion.id || draft.persistedId,
    questionCode: updatedQuestion.question_code || draft.questionCode,
    currentVersion: updatedQuestion.current_version || draft.currentVersion,
    currentVersionId: updatedQuestion.current_version_id || draft.currentVersionId,
    text: updatedQuestion.content || draft.text,
    rawOptions,
    correctAnswer,
    choices: formatChoices(rawOptions, correctAnswer),
    explanation: questionData.explanation ?? draft.explanation,
    sourceContext: questionData.model_source_context ?? draft.sourceContext,
  };
}

function GeneratePage() {
  const abortRef = useRef(null);
  const [phase, setPhase] = useState('idle');
  const [error, setError] = useState('');
  const [statusDetail, setStatusDetail] = useState('');
  const [sourceMode, setSourceMode] = useState('upload');
  const [file, setFile] = useState(null);
  const [fileName, setFileName] = useState('');
  const [documents, setDocuments] = useState([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState('');
  const [selectedDocumentId, setSelectedDocumentId] = useState('');
  const [planItems, setPlanItems] = useState(createInitialPlan);
  const [teacherInstruction, setTeacherInstruction] = useState('');
  const [documentId, setDocumentId] = useState(null);
  const [activeJobId, setActiveJobId] = useState('');
  const [drafts, setDrafts] = useState([]);
  const [generationSummary, setGenerationSummary] = useState([]);
  const [chunkReady, setChunkReady] = useState(false);
  const [editingDraftId, setEditingDraftId] = useState(null);
  const [draftEditSnapshot, setDraftEditSnapshot] = useState(null);
  const [savingDraftId, setSavingDraftId] = useState(null);
  const [removingDraftId, setRemovingDraftId] = useState(null);

  const isBusy = !['idle', 'completed', 'failed'].includes(phase);
  const questionPlan = planItems
    .map((item) => ({
      question_type: toBackendQuestionType(item.questionTypeId),
      bloom_level: toBackendBloomLevel(item.bloomId),
      num_questions: normalizeCount(item.count),
    }))
    .filter((item) => item.question_type && item.bloom_level && item.num_questions > 0);
  const totalQuestions = questionPlan.reduce((total, item) => total + item.num_questions, 0);
  const reusableDocuments = documents.filter(isDocumentOcrReady);
  const selectedDocument = reusableDocuments.find((item) => item.id === selectedDocumentId);
  const generationShortfalls = generationSummary.filter((item) => (
    item.skipped_count > 0 || item.duplicate_count > 0 || (item.warnings || []).length > 0
  ));

  useEffect(() => () => abortRef.current?.abort(), []);

  const resetPoll = () => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    return abortRef.current;
  };

  const fetchReusableDocuments = async () => {
    setDocumentsLoading(true);
    setDocumentsError('');
    try {
      const result = await listDocuments({ page: 1, pageSize: 100 });
      setDocuments(result.items || []);
    } catch (err) {
      setDocumentsError(err.message || 'Không tải được danh sách tài liệu đã OCR');
    } finally {
      setDocumentsLoading(false);
    }
  };

  useEffect(() => {
    fetchReusableDocuments();
  }, []);

  const validateForm = () => {
    if (sourceMode === 'upload') {
      if (!file) return 'Vui lòng chọn file PDF';
      if (!file.name.toLowerCase().endsWith('.pdf')) return 'Chỉ hỗ trợ file PDF';
    } else {
      if (!selectedDocumentId) return 'Vui lòng chọn tài liệu đã OCR';
      if (!selectedDocument) return 'Không tìm thấy tài liệu đã chọn';
      if (!isDocumentOcrReady(selectedDocument)) return 'Tài liệu này chưa OCR xong';
    }
    if (questionPlan.length === 0) return 'Vui lòng thêm ít nhất một dòng cấu hình câu hỏi';
    if (totalQuestions < 1 || totalQuestions > MAX_TOTAL_QUESTIONS) {
      return `Tổng số câu hỏi phải từ 1 đến ${MAX_TOTAL_QUESTIONS}`;
    }
    return null;
  };

  const updatePlanItem = (itemId, patch) => {
    setPlanItems((current) => current.map((item) => (
      item.id === itemId ? { ...item, ...patch } : item
    )));
  };

  const addPlanItem = () => {
    setPlanItems((current) => [...current, createPlanItem()]);
  };

  const removePlanItem = (itemId) => {
    setPlanItems((current) => {
      if (current.length === 1) return current;
      return current.filter((item) => item.id !== itemId);
    });
  };

  const updateDraft = (draftId, patch) => {
    setDrafts((current) => current.map((draft) => {
      if (draft.id !== draftId) return draft;
      const nextDraft = { ...draft, ...patch };
      if ('correctAnswer' in patch || 'rawOptions' in patch) {
        nextDraft.choices = formatChoices(nextDraft.rawOptions, nextDraft.correctAnswer);
      }
      return nextDraft;
    }));
  };

  const startEditDraft = (draft) => {
    setError('');
    setDraftEditSnapshot(draft);
    setEditingDraftId(draft.id);
  };

  const cancelEditDraft = () => {
    if (savingDraftId || removingDraftId) return;
    if (draftEditSnapshot) {
      setDrafts((current) => current.map((draft) => (
        draft.id === draftEditSnapshot.id ? draftEditSnapshot : draft
      )));
    }
    setDraftEditSnapshot(null);
    setEditingDraftId(null);
  };

  const handleSaveDraft = async (draft) => {
    if (!draft.persistedId) {
      alert('Câu hỏi này chưa có ID trong ngân hàng, vui lòng sinh lại.');
      return;
    }
    if (!draft.text.trim()) {
      alert('Nội dung câu hỏi không được để trống.');
      return;
    }
    const draftValidationError = validateDraftBeforeSave(draft);
    if (draftValidationError) {
      alert(draftValidationError);
      return;
    }

    setSavingDraftId(draft.id);
    try {
      const updatedQuestion = await updateQuestion(draft.persistedId, {
        expected_version: draft.currentVersion || 1,
        content: draft.text.trim(),
        question_data: {
          options: draft.rawOptions ?? null,
          correct_answer: draft.correctAnswer,
          explanation: draft.explanation,
          model_source_context: draft.sourceContext,
        },
        change_note: 'Teacher edited generated draft',
      });
      setDrafts((current) => current.map((item) => (
        item.id === draft.id ? mergeUpdatedDraft(item, updatedQuestion) : item
      )));
      setDraftEditSnapshot(null);
      setEditingDraftId(null);
      setStatusDetail(`Đã lưu ${draft.questionCode || 'câu hỏi nháp'}`);
    } catch (err) {
      alert(`Lưu câu hỏi thất bại: ${err.message}`);
    } finally {
      setSavingDraftId(null);
    }
  };

  const handleRemoveDraft = async (draft) => {
    const label = draft.questionCode || draft.id;
    if (!window.confirm(`Bỏ câu hỏi "${label}" khỏi danh sách nháp?`)) {
      return;
    }

    setRemovingDraftId(draft.id);
    try {
      if (draft.persistedId) {
        await deleteQuestion(draft.persistedId);
      }
      setDrafts((current) => current.filter((item) => item.id !== draft.id));
      if (editingDraftId === draft.id) {
        setDraftEditSnapshot(null);
        setEditingDraftId(null);
      }
      setStatusDetail(`Đã bỏ ${label}`);
    } catch (err) {
      alert(`Bỏ câu hỏi thất bại: ${err.message}`);
    } finally {
      setRemovingDraftId(null);
    }
  };

  const updateDraftOption = (draft, optionKey, optionValue) => {
    const entries = optionEntriesForDraft(draft);
    const nextEntries = entries.map((entry) => (
      entry.key === optionKey ? { ...entry, value: optionValue } : entry
    ));
    updateDraft(draft.id, { rawOptions: entriesToOptions(nextEntries) });
  };

  const toggleDraftCorrectAnswer = (draft, optionKey) => {
    const entries = optionEntriesForDraft(draft);
    const currentValues = correctAnswerValues(draft.correctAnswer);
    const hasValue = currentValues.includes(optionKey);
    const nextValues = hasValue
      ? currentValues.filter((value) => value !== optionKey)
      : [...currentValues, optionKey];
    updateDraft(draft.id, { correctAnswer: joinCorrectValues(nextValues, entries) });
  };

  const renderDraftAnswerEditor = (question, disabled) => {
    const entries = optionEntriesForDraft(question);

    if (SINGLE_CHOICE_TYPES.has(question.questionType)) {
      return (
        <div className="draft-option-editor">
          {entries.map((entry) => (
            <label className="draft-option-row" key={entry.key}>
              <input
                type="radio"
                name={`answer-${question.id}`}
                checked={question.correctAnswer === entry.key}
                disabled={disabled}
                onChange={() => updateDraft(question.id, { correctAnswer: entry.key })}
              />
              <span className="draft-option-key">{entry.key}</span>
              <input
                className="field-input"
                value={entry.value}
                disabled={disabled}
                onChange={(e) => updateDraftOption(question, entry.key, e.target.value)}
              />
            </label>
          ))}
        </div>
      );
    }

    if (MULTI_CHOICE_TYPES.has(question.questionType)) {
      const selectedAnswers = correctAnswerValues(question.correctAnswer);
      return (
        <div className="draft-option-editor">
          {entries.map((entry) => (
            <label className="draft-option-row" key={entry.key}>
              <input
                type="checkbox"
                checked={selectedAnswers.includes(entry.key)}
                disabled={disabled}
                onChange={() => toggleDraftCorrectAnswer(question, entry.key)}
              />
              <span className="draft-option-key">{entry.key}</span>
              <input
                className="field-input"
                value={entry.value}
                disabled={disabled}
                onChange={(e) => updateDraftOption(question, entry.key, e.target.value)}
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
                disabled={disabled}
                onChange={(e) => updateDraftOption(question, entry.key, e.target.value)}
              />
            </label>
          ))}
          <label className="draft-edit-field">
            <span>Đáp án đúng</span>
            <input
              className="field-input"
              value={question.correctAnswer || ''}
              disabled={disabled}
              onChange={(e) => updateDraft(question.id, { correctAnswer: e.target.value })}
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
          value={question.correctAnswer || ''}
          disabled={disabled}
          onChange={(e) => updateDraft(question.id, { correctAnswer: e.target.value })}
        />
      </label>
    );
  };

  const selectSourceMode = (mode) => {
    if (isBusy) return;
    setSourceMode(mode);
    setError('');
    setStatusDetail('');
    setDrafts([]);
    setGenerationSummary([]);
    setEditingDraftId(null);
    setDraftEditSnapshot(null);
    setSavingDraftId(null);
    setRemovingDraftId(null);
    setActiveJobId('');
    if (mode === 'upload') {
      setSelectedDocumentId('');
      setDocumentId(null);
      setChunkReady(false);
    } else {
      setFile(null);
      setFileName('');
    }
  };

  const handleSelectExistingDocument = (docId) => {
    const nextDocument = documents.find((item) => item.id === docId);
    setSelectedDocumentId(docId);
    setDocumentId(docId || null);
    setChunkReady(Boolean(nextDocument && isDocumentIndexed(nextDocument)));
    setDrafts([]);
    setGenerationSummary([]);
    setEditingDraftId(null);
    setDraftEditSnapshot(null);
    setSavingDraftId(null);
    setRemovingDraftId(null);
    setActiveJobId('');
  };

  const runOcrPipeline = async (pdfFile, signal) => {
    setPhase('uploading');
    setStatusDetail('Đang upload file PDF...');
    const uploadResult = await uploadOcrPdf(pdfFile);
    const ocrJobId = uploadResult.job_id;
    const docId = uploadResult.document_id;
    setActiveJobId(ocrJobId);
    setDocumentId(docId);

    const ocrResult = await pollJob(getOcrStatus, ocrJobId, {
      signal,
      timeoutMs: 45 * 60 * 1000,
      onUpdate: (status) => {
        if (status.status === 'queued') setPhase('ocr_queued');
        if (status.status === 'processing') setPhase('ocr_processing');
        setStatusDetail(`OCR: ${status.status}`);
      },
    });

    if (ocrResult.status === 'failed') {
      throw new Error(ocrResult.error_message || 'OCR thất bại');
    }

    return docId;
  };

  const runChunk = async (docId) => {
    setPhase('chunking');
    setStatusDetail('Đang chunk và lưu vector...');
    await chunkDocument(docId);
    setChunkReady(true);
  };

  const runGenerate = async (docId, signal) => {
    setPhase('generate_queued');
    setStatusDetail('Đang đưa yêu cầu sinh câu hỏi vào hàng đợi...');

    const payload = {
      document_id: docId,
      collection_name: 'chunks',
      bloom_level: questionPlan[0].bloom_level,
      question_type: questionPlan[0].question_type,
      num_questions: questionPlan[0].num_questions,
      question_plan: questionPlan,
      instruction: teacherInstruction.trim() || undefined,
    };

    const enqueueResult = await enqueueGenerateQuestions(payload);
    const genJobId = enqueueResult.job_id;
    setActiveJobId(genJobId);

    const genResult = await pollJob(getGenerateStatus, genJobId, {
      signal,
      timeoutMs: 20 * 60 * 1000,
      onUpdate: (status) => {
        if (status.status === 'queued') setPhase('generate_queued');
        if (status.status === 'processing') setPhase('generate_processing');
        setStatusDetail(`Generate: ${status.status}`);
      },
    });

    if (genResult.status === 'failed') {
      throw new Error(genResult.error_message || 'Sinh câu hỏi thất bại');
    }

    setEditingDraftId(null);
    setDraftEditSnapshot(null);
    setGenerationSummary(genResult.summary || []);
    setDrafts(mapGeneratedQuestions(genResult.data || []));
    setPhase('completed');
    setStatusDetail(`Đã sinh ${(genResult.data || []).length}/${totalQuestions} câu hỏi`);
  };

  const runPipeline = async ({ fromGenerateOnly = false } = {}) => {
    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }

    setError('');
    if (!fromGenerateOnly) {
      setDrafts([]);
      setGenerationSummary([]);
      setEditingDraftId(null);
      setDraftEditSnapshot(null);
    }

    const signal = resetPoll().signal;

    try {
      let docId = documentId;

      if (fromGenerateOnly) {
        if (!docId || !chunkReady) {
          throw new Error('Tài liệu chưa sẵn sàng để sinh câu hỏi lại');
        }
      } else if (sourceMode === 'upload') {
        docId = await runOcrPipeline(file, signal);
        await runChunk(docId);
        await fetchReusableDocuments();
      } else {
        if (!selectedDocument) {
          throw new Error('Vui lòng chọn tài liệu đã OCR');
        }
        docId = selectedDocument.id;
        setDocumentId(docId);
        if (isDocumentIndexed(selectedDocument)) {
          setChunkReady(true);
          setStatusDetail('Sử dụng tài liệu đã OCR và index trước đó');
        } else {
          await runChunk(docId);
          await fetchReusableDocuments();
        }
      }

      await runGenerate(docId, signal);
    } catch (err) {
      if (err.name === 'AbortError') return;
      setPhase('failed');
      setError(err.message || 'Đã xảy ra lỗi');
      setStatusDetail('');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    await runPipeline({ fromGenerateOnly: false });
  };

  const handleRetry = async () => {
    if (chunkReady && documentId) {
      await runPipeline({ fromGenerateOnly: true });
      return;
    }
    await runPipeline({ fromGenerateOnly: false });
  };

  const handleReset = () => {
    abortRef.current?.abort();
    setPhase('idle');
    setError('');
    setStatusDetail('');
    setSourceMode('upload');
    setFile(null);
    setFileName('');
    setSelectedDocumentId('');
    setPlanItems(createInitialPlan());
    setTeacherInstruction('');
    setDocumentId(null);
    setActiveJobId('');
    setDrafts([]);
    setGenerationSummary([]);
    setEditingDraftId(null);
    setDraftEditSnapshot(null);
    setSavingDraftId(null);
    setRemovingDraftId(null);
    setChunkReady(false);
  };

  const step1Active = ['uploading', 'ocr_queued', 'ocr_processing', 'chunking'].includes(phase);
  const step2Active = ['generate_queued', 'generate_processing'].includes(phase);
  const step3Active = phase === 'completed';
  const step1Done = ['generate_queued', 'generate_processing', 'completed'].includes(phase) || chunkReady;
  const step2Done = phase === 'completed';

  return (
    <main className="generate-page">
      <section className="page-hero">
        <div className="container">
          <div className="page-hero-badge">AI Pipeline · RAG</div>
          <h1 className="page-hero-title">Trình sinh câu hỏi bằng AI</h1>
          <p className="page-hero-desc">
            Tải lên tài liệu học phần, cấu hình loại câu hỏi và cấp độ tư duy theo thang Bloom — hệ thống sẽ dùng
            mô hình ngôn ngữ lớn kết hợp kỹ thuật RAG để sinh câu hỏi nháp từ đúng nội dung tài liệu.
          </p>
        </div>
      </section>

      <section className="gen-steps">
        <div className="container gen-steps-row">
          <div className={`gen-step ${step1Active || step1Done ? 'gen-step--active' : ''}`}>
            <span className="gen-step-num">1</span>
            <span className="gen-step-label">Tải tài liệu</span>
          </div>
          <div className="gen-step-line" />
          <div className={`gen-step ${step2Active || step2Done ? 'gen-step--active' : ''}`}>
            <span className="gen-step-num">2</span>
            <span className="gen-step-label">Cấu hình sinh câu hỏi</span>
          </div>
          <div className="gen-step-line" />
          <div className={`gen-step ${step3Active ? 'gen-step--active' : ''}`}>
            <span className="gen-step-num">3</span>
            <span className="gen-step-label">Xem trước &amp; duyệt</span>
          </div>
        </div>
      </section>

      <section className="gen-body">
        <div className="container gen-grid">
          <form className="gen-form-card" onSubmit={handleSubmit}>
            <h3 className="gen-card-title">Cấu hình sinh câu hỏi</h3>

            {phase !== 'idle' && phase !== 'failed' && (
              <div className={`gen-status gen-status--${phase === 'completed' ? 'done' : 'running'}`}>
                {phase !== 'completed' && <span className="gen-status-spinner" aria-hidden="true" />}
                <div className="gen-status-text">
                  <strong>{PHASE_LABELS[phase] || phase}</strong>
                  {statusDetail && <span>{statusDetail}</span>}
                  {activeJobId && (
                    <span className="job-badge">Job: {shortId(activeJobId)}</span>
                  )}
                </div>
              </div>
            )}

            {error && (
              <div className="gen-error">
                <p>{error}</p>
                <div className="gen-error-actions">
                  <button type="button" className="btn btn--secondary" onClick={handleRetry}>
                    Thử lại
                  </button>
                  <button type="button" className="btn btn--ghost" onClick={handleReset}>
                    Bắt đầu lại
                  </button>
                </div>
              </div>
            )}

            <div className="field-group">
              <label className="field-label">Tài liệu nguồn</label>
              <div className="source-mode-switch">
                <button
                  type="button"
                  className={`source-mode-btn ${sourceMode === 'upload' ? 'source-mode-btn--active' : ''}`}
                  disabled={isBusy}
                  onClick={() => selectSourceMode('upload')}
                >
                  Tải PDF mới
                </button>
                <button
                  type="button"
                  className={`source-mode-btn ${sourceMode === 'existing' ? 'source-mode-btn--active' : ''}`}
                  disabled={isBusy}
                  onClick={() => selectSourceMode('existing')}
                >
                  Chọn tài liệu đã OCR
                </button>
              </div>

              {sourceMode === 'upload' ? (
                <label className={`upload-drop ${isBusy ? 'upload-drop--disabled' : ''}`}>
                  <input
                    type="file"
                    accept=".pdf"
                    disabled={isBusy}
                    onChange={(e) => {
                      const nextFile = e.target.files?.[0] || null;
                      setFile(nextFile);
                      setFileName(nextFile?.name || '');
                      setSelectedDocumentId('');
                      setDocumentId(null);
                      setDrafts([]);
                      setGenerationSummary([]);
                      setEditingDraftId(null);
                      setDraftEditSnapshot(null);
                      setChunkReady(false);
                    }}
                    hidden
                  />
                  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="17 8 12 3 7 8" />
                    <line x1="12" y1="3" x2="12" y2="15" />
                  </svg>
                  <span>{fileName || 'Kéo thả hoặc chọn file PDF'}</span>
                  <span className="upload-hint">Chỉ hỗ trợ PDF · Tự động OCR với file scan</span>
                </label>
              ) : (
                <div className="existing-doc-panel">
                  <div className="existing-doc-row">
                    <select
                      className="field-select existing-doc-select"
                      value={selectedDocumentId}
                      disabled={isBusy || documentsLoading}
                      onChange={(e) => handleSelectExistingDocument(e.target.value)}
                    >
                      <option value="">
                        {documentsLoading ? 'Đang tải tài liệu...' : 'Chọn tài liệu đã OCR'}
                      </option>
                      {reusableDocuments.map((doc) => (
                        <option
                          key={doc.id}
                          value={doc.id}
                        >
                          {reusableDocumentLabel(doc)}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="btn btn--ghost existing-doc-refresh"
                      disabled={isBusy || documentsLoading}
                      onClick={fetchReusableDocuments}
                    >
                      Tải lại
                    </button>
                  </div>
                  {documentsError && <p className="source-note source-note--error">{documentsError}</p>}
                  {!documentsLoading && reusableDocuments.length === 0 && !documentsError && (
                    <p className="source-note">Chưa có tài liệu OCR sẵn sàng. Hãy tải PDF mới trước.</p>
                  )}
                  {selectedDocument && (
                    <p className="source-note">
                      {isDocumentIndexed(selectedDocument)
                        ? 'Tài liệu đã index, có thể sinh câu hỏi ngay.'
                        : 'Tài liệu đã OCR; hệ thống sẽ chunk/index trước khi sinh câu hỏi.'}
                    </p>
                  )}
                </div>
              )}
            </div>

            <div className="field-group">
              <label className="field-label">Học phần</label>
              <select className="field-select" defaultValue="ctdl" disabled={isBusy}>
                <option value="ctdl">Cấu trúc dữ liệu</option>
                <option value="soon" disabled>Học phần khác (sắp ra mắt)</option>
              </select>
            </div>

            <div className="field-group">
              <div className="field-label-row">
                <label className="field-label">Ma trận sinh câu hỏi</label>
                <span className={`plan-total ${totalQuestions > MAX_TOTAL_QUESTIONS ? 'plan-total--error' : ''}`}>
                  {totalQuestions}/{MAX_TOTAL_QUESTIONS}
                </span>
              </div>
              <div className="plan-builder-list">
                {planItems.map((item, index) => {
                  const count = normalizeCount(item.count);
                  const selectedBloomMeta = BLOOM_LEVELS.find((bloom) => bloom.id === item.bloomId);
                  return (
                    <div className="plan-builder-row" key={item.id}>
                      <div className="plan-row-header">
                        <span className="plan-row-index">Dòng {index + 1}</span>
                        <button
                          type="button"
                          className="plan-remove-btn"
                          title="Xóa dòng"
                          disabled={isBusy || planItems.length === 1}
                          onClick={() => removePlanItem(item.id)}
                        >
                          Xóa
                        </button>
                      </div>
                      <div className="plan-builder-fields">
                        <label className="plan-field">
                          <span>Dạng câu hỏi</span>
                          <select
                            className="field-select plan-select"
                            value={item.questionTypeId}
                            disabled={isBusy}
                            onChange={(e) => updatePlanItem(item.id, { questionTypeId: e.target.value })}
                          >
                            {QUESTION_TYPES.map((type) => (
                              <option key={type.id} value={type.id}>{type.label}</option>
                            ))}
                          </select>
                        </label>
                        <label className="plan-field plan-field--wide">
                          <span>Mức Bloom</span>
                          <select
                            className="field-select plan-select"
                            value={item.bloomId}
                            disabled={isBusy}
                            onChange={(e) => updatePlanItem(item.id, { bloomId: e.target.value })}
                          >
                            {BLOOM_LEVELS.map((bloom) => (
                              <option key={bloom.id} value={bloom.id}>
                                {bloom.level}. {bloom.label}
                              </option>
                            ))}
                          </select>
                          {selectedBloomMeta && (
                            <small>{selectedBloomMeta.caption}</small>
                          )}
                        </label>
                        <label className="plan-field plan-field--count">
                          <span>Số câu</span>
                          <input
                            className="field-input plan-count-input"
                            type="number"
                            min="1"
                            max="10"
                            value={count}
                            disabled={isBusy}
                            onFocus={(e) => e.target.select()}
                            onChange={(e) => updatePlanItem(item.id, { count: normalizeCount(e.target.value) })}
                          />
                        </label>
                      </div>
                    </div>
                  );
                })}
              </div>
              <button
                type="button"
                className="btn btn--secondary plan-add-btn"
                disabled={isBusy || totalQuestions >= MAX_TOTAL_QUESTIONS}
                onClick={addPlanItem}
              >
                + Thêm dòng
              </button>
            </div>

            <div className="field-group">
              <label className="field-label">Yêu cầu sinh câu hỏi</label>
              <textarea
                className="field-textarea"
                rows="4"
                maxLength="1200"
                value={teacherInstruction}
                disabled={isBusy}
                onChange={(e) => setTeacherInstruction(e.target.value)}
              />
            </div>

            <button className="btn btn--primary gen-submit" type="submit" disabled={isBusy}>
              {isBusy ? (
                <>
                  <span className="gen-status-spinner gen-status-spinner--inline" aria-hidden="true" />
                  Đang xử lý...
                </>
              ) : (
                <>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5" /><path d="M2 12l10 5 10-5" />
                  </svg>
                  Sinh câu hỏi bằng AI
                </>
              )}
            </button>
            <p className="gen-form-note">
              Toàn bộ câu hỏi sinh ra sẽ ở trạng thái nháp để giảng viên rà soát trước khi gửi kiểm duyệt.
            </p>
          </form>

          <div className="gen-preview-card">
            <div className="gen-card-title-row">
              <h3 className="gen-card-title">Xem trước câu hỏi nháp</h3>
              <span className="gen-preview-count">{drafts.length} câu hỏi</span>
            </div>

            {generationSummary.length > 0 && (
              <div className={`gen-summary-list ${generationShortfalls.length ? 'gen-summary-list--warning' : ''}`}>
                {generationSummary.map((item) => (
                  <div className="gen-summary-item" key={`${item.plan_index}-${item.question_type}-${item.bloom_level}`}>
                    <strong>Dòng {item.plan_index}</strong>
                    <span>
                      {questionTypeLabel(item.question_type)} · {bloomLevelLabel(item.bloom_level)} · {item.saved_count}/{item.requested_count}
                    </span>
                    {(item.warnings || []).length > 0 && <small>{item.warnings[0]}</small>}
                  </div>
                ))}
              </div>
            )}

            {drafts.length === 0 ? (
              <div className="gen-preview-empty">
                <p>Chưa có câu hỏi nháp.</p>
                <span>Tải PDF, cấu hình và bấm sinh câu hỏi để xem kết quả tại đây.</span>
              </div>
            ) : (
              <div className="draft-list">
                {drafts.map((question) => {
                  const isEditing = editingDraftId === question.id;
                  const isSaving = savingDraftId === question.id;
                  const isRemoving = removingDraftId === question.id;
                  const actionBusy = Boolean(savingDraftId || removingDraftId || editingDraftId);

                  return (
                    <article className={`draft-item ${isEditing ? 'draft-item--editing' : ''}`} key={question.id}>
                      <div className="draft-item-meta">
                        <span className="q-tag">{question.type}</span>
                        <span className="bloom-tag">{question.bloom}</span>
                        <span className="draft-status" title={question.questionCode}>
                          {shortCode(question.questionCode)} · v{question.currentVersion || 1} · Nháp
                        </span>
                      </div>

                      {isEditing ? (
                        <div className="draft-edit-form">
                          <label className="draft-edit-field">
                            <span>Nội dung câu hỏi</span>
                            <textarea
                              className="field-textarea draft-edit-textarea"
                              rows="4"
                              value={question.text}
                              disabled={isSaving || isRemoving}
                              onChange={(e) => updateDraft(question.id, { text: e.target.value })}
                            />
                          </label>
                          {renderDraftAnswerEditor(question, isSaving || isRemoving)}
                          <label className="draft-edit-field">
                            <span>Giải thích</span>
                            <textarea
                              className="field-textarea draft-edit-textarea"
                              rows="3"
                              value={question.explanation || ''}
                              disabled={isSaving || isRemoving}
                              onChange={(e) => updateDraft(question.id, { explanation: e.target.value })}
                            />
                          </label>
                        </div>
                      ) : (
                        <>
                          <p className="draft-item-text">{question.text}</p>
                          {question.explanation && (
                            <p className="draft-item-explanation">{question.explanation}</p>
                          )}
                        </>
                      )}

                      <div className="draft-item-choices">
                        {question.choices.map((choice) => (
                          <span
                            key={choice.text}
                            className={`choice ${choice.isCorrect ? 'choice--correct' : ''}`}
                          >
                            {choice.text}
                          </span>
                        ))}
                      </div>

                      <div className="draft-item-actions">
                        {isEditing ? (
                          <>
                            <button
                              type="button"
                              className="icon-btn icon-btn--approve"
                              disabled={isSaving || isRemoving}
                              onClick={() => handleSaveDraft(question)}
                            >
                              {isSaving ? 'Đang lưu...' : 'Lưu chỉnh sửa'}
                            </button>
                            <button
                              type="button"
                              className="icon-btn"
                              disabled={isSaving || isRemoving}
                              onClick={cancelEditDraft}
                            >
                              Hủy
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              className="icon-btn"
                              disabled={actionBusy}
                              onClick={() => startEditDraft(question)}
                            >
                              Sửa
                            </button>
                            <button
                              type="button"
                              className="icon-btn icon-btn--reject"
                              disabled={actionBusy}
                              onClick={() => handleRemoveDraft(question)}
                            >
                              {isRemoving ? 'Đang bỏ...' : 'Bỏ câu'}
                            </button>
                          </>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}

export default GeneratePage;
