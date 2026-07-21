import React, { useEffect, useRef, useState } from 'react';
import { chunkDocument } from '../api/chunk';
import { enqueueGenerateQuestions, getGenerateStatus } from '../api/generate';
import { getOcrStatus, uploadOcrPdf } from '../api/ocr';
import {
  BLOOM_LEVELS,
  QUESTION_TYPES,
  toBackendBloomLevel,
  toBackendQuestionType,
} from '../constants/generationEnums';
import { pollJob } from '../hooks/useJobPoll';
import { mapGeneratedQuestions } from '../utils/mapGeneratedQuestion';
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

function shortId(id) {
  if (!id) return '';
  return id.length > 8 ? `${id.slice(0, 8)}...` : id;
}

function GeneratePage() {
  const abortRef = useRef(null);
  const [phase, setPhase] = useState('idle');
  const [error, setError] = useState('');
  const [statusDetail, setStatusDetail] = useState('');
  const [file, setFile] = useState(null);
  const [fileName, setFileName] = useState('');
  const [selectedType, setSelectedType] = useState('mcq');
  const [selectedBloom, setSelectedBloom] = useState('understand');
  const [numQuestions, setNumQuestions] = useState(5);
  const [documentId, setDocumentId] = useState(null);
  const [activeJobId, setActiveJobId] = useState('');
  const [drafts, setDrafts] = useState([]);
  const [chunkReady, setChunkReady] = useState(false);

  const isBusy = !['idle', 'completed', 'failed'].includes(phase);

  useEffect(() => () => abortRef.current?.abort(), []);

  const resetPoll = () => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    return abortRef.current;
  };

  const validateForm = () => {
    if (!file) return 'Vui lòng chọn file PDF';
    if (!file.name.toLowerCase().endsWith('.pdf')) return 'Chỉ hỗ trợ file PDF';
    if (!selectedType) return 'Vui lòng chọn loại câu hỏi';
    if (!selectedBloom) return 'Vui lòng chọn cấp độ Bloom';
    if (numQuestions < 1 || numQuestions > 10) return 'Số câu hỏi phải từ 1 đến 10';
    return null;
  };

  const runOcrPipeline = async (pdfFile, signal) => {
    setPhase('uploading');
    setStatusDetail('Đang upload file PDF...');
    const uploadResult = await uploadOcrPdf(pdfFile);
    const ocrJobId = uploadResult.job_id;
    setActiveJobId(ocrJobId);
    setDocumentId(ocrJobId);

    const ocrResult = await pollJob(getOcrStatus, ocrJobId, {
      signal,
      onUpdate: (status) => {
        if (status.status === 'queued') setPhase('ocr_queued');
        if (status.status === 'processing') setPhase('ocr_processing');
        setStatusDetail(`OCR: ${status.status}`);
      },
    });

    if (ocrResult.status === 'failed') {
      throw new Error(ocrResult.error_message || 'OCR thất bại');
    }

    return ocrJobId;
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
      bloom_level: toBackendBloomLevel(selectedBloom),
      question_type: toBackendQuestionType(selectedType),
      num_questions: Number(numQuestions),
    };

    const enqueueResult = await enqueueGenerateQuestions(payload);
    const genJobId = enqueueResult.job_id;
    setActiveJobId(genJobId);

    const genResult = await pollJob(getGenerateStatus, genJobId, {
      signal,
      onUpdate: (status) => {
        if (status.status === 'queued') setPhase('generate_queued');
        if (status.status === 'processing') setPhase('generate_processing');
        setStatusDetail(`Generate: ${status.status}`);
      },
    });

    if (genResult.status === 'failed') {
      throw new Error(genResult.error_message || 'Sinh câu hỏi thất bại');
    }

    setDrafts(mapGeneratedQuestions(genResult.data || []));
    setPhase('completed');
    setStatusDetail('Đã sinh câu hỏi thành công');
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
    }

    const signal = resetPoll().signal;

    try {
      let docId = documentId;

      if (!fromGenerateOnly) {
        docId = await runOcrPipeline(file, signal);
        await runChunk(docId);
      } else if (!docId || !chunkReady) {
        throw new Error('Tài liệu chưa sẵn sàng để sinh câu hỏi lại');
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
    setFile(null);
    setFileName('');
    setDocumentId(null);
    setActiveJobId('');
    setDrafts([]);
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
              <label className={`upload-drop ${isBusy ? 'upload-drop--disabled' : ''}`}>
                <input
                  type="file"
                  accept=".pdf"
                  disabled={isBusy}
                  onChange={(e) => {
                    const nextFile = e.target.files?.[0] || null;
                    setFile(nextFile);
                    setFileName(nextFile?.name || '');
                    setDocumentId(null);
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
            </div>

            <div className="field-group">
              <label className="field-label">Học phần</label>
              <select className="field-select" defaultValue="ctdl" disabled={isBusy}>
                <option value="ctdl">Cấu trúc dữ liệu</option>
                <option value="soon" disabled>Học phần khác (sắp ra mắt)</option>
              </select>
            </div>

            <div className="field-group">
              <label className="field-label">Loại câu hỏi</label>
              <div className="chip-group">
                {QUESTION_TYPES.map((type) => (
                  <button
                    type="button"
                    key={type.id}
                    className={`chip ${selectedType === type.id ? 'chip--active' : ''}`}
                    disabled={isBusy}
                    onClick={() => setSelectedType(type.id)}
                  >
                    {type.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="field-group">
              <label className="field-label">Cấp độ tư duy (Bloom)</label>
              <div className="chip-group">
                {BLOOM_LEVELS.map((bloom) => (
                  <button
                    type="button"
                    key={bloom.id}
                    className={`chip chip--bloom ${selectedBloom === bloom.id ? 'chip--active' : ''}`}
                    disabled={isBusy}
                    onClick={() => setSelectedBloom(bloom.id)}
                  >
                    {bloom.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="field-row">
              <div className="field-group">
                <label className="field-label">Số lượng câu hỏi</label>
                <input
                  className="field-input"
                  type="number"
                  min="1"
                  max="10"
                  value={numQuestions}
                  disabled={isBusy}
                  onChange={(e) => setNumQuestions(Number(e.target.value))}
                />
              </div>
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
              Toàn bộ câu hỏi sinh ra sẽ ở trạng thái nháp và cần giảng viên xác nhận trước khi lưu vào ngân hàng câu hỏi.
            </p>
          </form>

          <div className="gen-preview-card">
            <div className="gen-card-title-row">
              <h3 className="gen-card-title">Xem trước câu hỏi nháp</h3>
              <span className="gen-preview-count">{drafts.length} câu hỏi</span>
            </div>

            {drafts.length === 0 ? (
              <div className="gen-preview-empty">
                <p>Chưa có câu hỏi nháp.</p>
                <span>Tải PDF, cấu hình và bấm sinh câu hỏi để xem kết quả tại đây.</span>
              </div>
            ) : (
              <div className="draft-list">
                {drafts.map((question) => (
                  <article className="draft-item" key={question.id}>
                    <div className="draft-item-meta">
                      <span className="q-tag">{question.type}</span>
                      <span className="bloom-tag">{question.bloom}</span>
                      <span className="draft-status">Nháp · Chờ duyệt</span>
                    </div>
                    <p className="draft-item-text">{question.text}</p>
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
                    {question.explanation && (
                      <p className="draft-item-explanation">{question.explanation}</p>
                    )}
                    <div className="draft-item-actions">
                      <button type="button" className="icon-btn" title="Chỉnh sửa" disabled>
                        Sửa
                      </button>
                      <button type="button" className="icon-btn icon-btn--approve" title="Duyệt" disabled>
                        Duyệt
                      </button>
                      <button type="button" className="icon-btn icon-btn--reject" title="Từ chối" disabled>
                        Từ chối
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}

export default GeneratePage;
