import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  addQuestionsManual,
  autoGenerateQuestions,
  createVariant,
  deleteVariant,
  downloadVariantDocx,
  downloadVariantPdf,
  getExam,
  getMatrixAvailability,
  getVariantPreview,
  listExamQuestionPool,
  listVariants,
  removeQuestion,
  saveMatrix,
  updateExamStatus,
  updateExam,
} from '../api/exams';
import { listSubjects } from '../api/catalog';
import { BLOOM_LEVELS, DIFFICULTIES, questionTypeLabel } from '../constants/generationEnums';
import { EXAM_BLOOM_LEVELS, examBloomLevel, examMatrixError, normalizeExamMatrix } from '../utils/examMatrix';
import '../css/ExamBuilderPage.css';

function refId(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  return value.id || value._id || '';
}

const COGNITIVE_LEVELS = EXAM_BLOOM_LEVELS;

const EXAM_STATUS_LABEL = {
  DRAFT: 'Nháp',
  READY: 'Sẵn sàng',
  FINALIZED: 'Đã chốt',
  ARCHIVED: 'Lưu trữ',
};

const QUESTION_POOL_PAGE_SIZE = 20;

const EXPORT_VARIANT_TYPES = [
  { value: 'de', label: 'Đề thi' },
  { value: 'dapan', label: 'Đáp án' },
  { value: 'de_dapan', label: 'Đề + Đáp án' },
];

const EXPORT_FORMATS = [
  { value: 'pdf', label: 'PDF' },
  { value: 'docx', label: 'DOCX' },
];

const MAX_VARIANTS = 4;
const DEFAULT_VARIANT_CODES = ['132', '209', '357', '485'];

function examStatus(exam) {
  return String(exam?.status || 'DRAFT').toUpperCase();
}

function isExamLocked(exam) {
  return ['FINALIZED', 'ARCHIVED'].includes(examStatus(exam));
}

const STEPS = [
  {
    id: 'info',
    label: 'Thông tin đề',
    desc: 'Tên đề, kỳ thi, số câu và đầu trang',
  },
  {
    id: 'content',
    label: 'Nội dung đề',
    desc: 'Ma trận theo mức nhận thức và chọn câu hỏi',
  },
  {
    id: 'export',
    label: 'Xuất đề',
    desc: 'Tạo mã đề, xem trước và xuất PDF/DOCX',
  },
];

function emptyCell() {
  return { chapter_id: '', cognitive_level: 'nho', difficulty: '', count: 1 };
}

function ExamBuilderPage() {
  const { examId } = useParams();
  const navigate = useNavigate();
  const [exam, setExam] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [step, setStep] = useState('info');
  const [subjects, setSubjects] = useState([]);

  const fetchExam = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getExam(examId);
      setExam(data);
    } catch (err) {
      setError(err.message || 'Không tải được đề thi');
    } finally {
      setLoading(false);
    }
  }, [examId]);

  useEffect(() => {
    fetchExam();
    listSubjects().then(setSubjects).catch(() => {});
  }, [fetchExam]);

  const subject = useMemo(
    () => subjects.find((s) => refId(s) === exam?.subject_id),
    [subjects, exam],
  );
  const chapters = subject?.chapters || [];
  const statusValue = examStatus(exam);
  const locked = isExamLocked(exam);

  const handleStatusChange = async (targetStatus) => {
    if (targetStatus === 'FINALIZED' && !window.confirm('Chốt đề thi và khóa ma trận/danh sách câu hỏi?')) {
      return;
    }
    if (targetStatus === 'ARCHIVED' && !window.confirm('Lưu trữ đề thi này?')) {
      return;
    }
    try {
      const updated = await updateExamStatus(exam.id, targetStatus);
      setExam(updated);
    } catch (err) {
      alert('Cập nhật trạng thái đề thi thất bại: ' + err.message);
    }
  };

  if (loading) return <main className="exam-builder-page"><p className="empty-note">Đang tải đề thi...</p></main>;
  if (error) return <main className="exam-builder-page"><p className="exam-error">{error}</p></main>;
  if (!exam) return null;

  const selectedCount = exam.questions?.length || 0;
  const targetCount = Number(exam.question_count) || 0;
  const currentStepIndex = STEPS.findIndex((s) => s.id === step);

  return (
    <main className="exam-builder-page">
      <section className="builder-hero">
        <div className="container">
          <button type="button" className="btn btn--ghost" onClick={() => navigate('/lam-de-thi')}>
            ← Danh sách đề thi
          </button>
          <div className="hero-main">
            <div>
              <div className="hero-eyebrow">Soạn đề thi giấy</div>
              <h1 className="page-hero-title">{exam.name}</h1>
              <p className="page-hero-desc">{exam.exam_title}</p>
            </div>
            <div className="hero-meta">
              <span className={`exam-status-pill exam-status-pill--${statusValue.toLowerCase()}`}>
                {EXAM_STATUS_LABEL[statusValue] || statusValue}
              </span>
              <div className="hero-counts">
                <div><b>{selectedCount}</b>/{targetCount}</div>
                <small>câu hỏi</small>
              </div>
              <div className="hero-counts">
                <div><b>{exam.variant_count || 0}</b>/4</div>
                <small>mã đề</small>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="builder-body">
        <div className="container">
          <ol className="step-progress">
            {STEPS.map((s, index) => {
              const active = step === s.id;
              const done = index < currentStepIndex;
              return (
                <li
                  key={s.id}
                  className={`step-progress-item ${active ? 'is-active' : ''} ${done ? 'is-done' : ''}`}
                >
                  <button type="button" onClick={() => setStep(s.id)}>
                    <span className="step-progress-num">{done ? '✓' : index + 1}</span>
                    <span className="step-progress-text">
                      <b>{s.label}</b>
                      <small>{s.desc}</small>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>

          <div className="builder-content card">
            <LifecycleBar
              exam={exam}
              status={statusValue}
              onStatusChange={handleStatusChange}
            />
            {locked && (
              <p className="locked-note">
                Đề thi đã {statusValue === 'ARCHIVED' ? 'lưu trữ' : 'chốt'}; thông tin, ma trận và danh sách câu hỏi đang được khóa.
              </p>
            )}

            <div hidden={step !== 'info'}>
              <InfoSection exam={exam} onSaved={setExam} readOnly={locked} />
            </div>
            <div hidden={step !== 'content'}>
              <ContentSection exam={exam} chapters={chapters} onSaved={setExam} readOnly={locked} />
            </div>
            <div hidden={step !== 'export'}>
              <ExportSection exam={exam} onSaved={setExam} onStatusChange={handleStatusChange} />
            </div>

            <div className="step-nav">
              {currentStepIndex > 0 && (
                <button
                  type="button"
                  className="btn btn--outline"
                  onClick={() => setStep(STEPS[currentStepIndex - 1].id)}
                >
                  ← {STEPS[currentStepIndex - 1].label}
                </button>
              )}
              <span className="step-nav-spacer" />
              {currentStepIndex < STEPS.length - 1 && (
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => setStep(STEPS[currentStepIndex + 1].id)}
                >
                  {STEPS[currentStepIndex + 1].label} →
                </button>
              )}
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

function LifecycleBar({ exam, status, onStatusChange }) {
  const selectedCount = exam.questions?.length || 0;
  const target = Number(exam.question_count) || 0;
  const hasExactQuestionCount = selectedCount === target;
  const canReady = status === 'DRAFT' && hasExactQuestionCount;
  const canFinalize = status === 'READY' && hasExactQuestionCount;
  const canArchive = status === 'FINALIZED';
  const diffMessage = !hasExactQuestionCount
    ? (selectedCount < target
      ? `Còn thiếu ${target - selectedCount} câu để chuyển sẵn sàng hoặc chốt đề.`
      : `Đang dư ${selectedCount - target} câu, cần bỏ bớt để chuyển sẵn sàng hoặc chốt đề.`)
    : '';

  return (
    <section className="lifecycle-bar">
      <div>
        {diffMessage ? (
          <small className="lifecycle-note">{diffMessage}</small>
        ) : (
          <small className="lifecycle-note lifecycle-note--ok">Đã đủ câu, có thể chốt đề.</small>
        )}
      </div>
      <div className="lifecycle-actions">
        {status === 'READY' && (
          <button type="button" className="btn btn--outline" onClick={() => onStatusChange('DRAFT')}>
            Mở chỉnh
          </button>
        )}
        {status === 'DRAFT' && (
          <button type="button" className="btn btn--outline" disabled={!canReady} onClick={() => onStatusChange('READY')}>
            Đánh dấu sẵn sàng
          </button>
        )}
        {status === 'READY' && (
          <button type="button" className="btn btn--primary" disabled={!canFinalize} onClick={() => onStatusChange('FINALIZED')}>
            Chốt đề
          </button>
        )}
        {canArchive && (
          <button type="button" className="btn btn--outline" onClick={() => onStatusChange('ARCHIVED')}>
            Lưu trữ
          </button>
        )}
      </div>
    </section>
  );
}

// ======================== STEP 1: THÔNG TIN ========================
function InfoSection({ exam, onSaved, readOnly }) {
  const [form, setForm] = useState({
    name: exam.name,
    exam_title: exam.exam_title,
    question_count: exam.question_count,
    header: { ...exam.header },
  });
  const [saving, setSaving] = useState(false);

  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }));
  const setHeader = (key, value) => setForm((f) => ({ ...f, header: { ...f.header, [key]: value } }));

  const handleSave = async (e) => {
    e.preventDefault();
    if (readOnly || saving) return;
    if (!form.name.trim() || !form.exam_title.trim()) {
      alert('Vui lòng nhập tên đề thi và tên kỳ thi.');
      return;
    }
    setSaving(true);
    try {
      const updated = await updateExam(exam.id, {
        name: form.name.trim(),
        exam_title: form.exam_title.trim(),
        question_count: Number(form.question_count),
        header: { ...form.header, duration_minutes: Number(form.header.duration_minutes) },
      });
      onSaved(updated);
      alert('Đã lưu thông tin đề thi.');
    } catch (err) {
      alert('Lưu thất bại: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSave} className="section-form">
      <div className="section-block">
        <h3 className="step-title">1. Thông tin cơ bản</h3>
        <p className="step-desc">Nhập tên đề thi, kỳ thi và số câu dự kiến.</p>
        <div className="field-grid field-grid--2">
          <div className="field-group">
            <label className="field-label">Tên đề thi</label>
            <input required maxLength={300} className="field-input" value={form.name} onChange={(e) => setField('name', e.target.value)} disabled={readOnly || saving} />
          </div>
          <div className="field-group">
            <label className="field-label">Tên kỳ thi</label>
            <input required maxLength={300} className="field-input" value={form.exam_title} onChange={(e) => setField('exam_title', e.target.value)} disabled={readOnly || saving} />
          </div>
          <div className="field-group">
            <label className="field-label">Số lượng câu hỏi</label>
            <input required type="number" min={1} max={200} step={1} className="field-input" value={form.question_count} onChange={(e) => setField('question_count', e.target.value)} disabled={readOnly || saving} />
          </div>
        </div>
      </div>

      <div className="section-block">
        <h3 className="step-title">2. Đầu trang đề thi</h3>
        <p className="step-desc">Thông tin hiển thị trên đầu đề thi khi in giấy.</p>
        <div className="field-grid field-grid--2">
          <div className="field-group">
            <label className="field-label">Trường / Đại học</label>
            <input className="field-input" value={form.header.school_name || ''} onChange={(e) => setHeader('school_name', e.target.value)} disabled={readOnly} />
          </div>
          <div className="field-group">
            <label className="field-label">Khoa / Bộ môn</label>
            <input className="field-input" value={form.header.faculty_name || ''} onChange={(e) => setHeader('faculty_name', e.target.value)} disabled={readOnly} />
          </div>
          <div className="field-group">
            <label className="field-label">Tên kỳ thi (in trên đầu trang)</label>
            <input className="field-input" value={form.header.exam_name || ''} onChange={(e) => setHeader('exam_name', e.target.value)} disabled={readOnly} />
          </div>
          <div className="field-group">
            <label className="field-label">Môn học / học phần</label>
            <input className="field-input" value={form.header.subject_name || ''} onChange={(e) => setHeader('subject_name', e.target.value)} disabled={readOnly} />
          </div>
          <div className="field-group">
            <label className="field-label">Thời gian làm bài (phút)</label>
            <input required type="number" min={1} max={600} className="field-input" value={form.header.duration_minutes ?? 60} onChange={(e) => setHeader('duration_minutes', e.target.value)} disabled={readOnly || saving} />
          </div>
          <div className="field-group">
            <label className="field-label">Lớp</label>
            <input className="field-input" value={form.header.class_name || ''} onChange={(e) => setHeader('class_name', e.target.value)} disabled={readOnly} placeholder="Tuỳ chọn" />
          </div>
          <div className="field-group">
            <label className="field-label">Phòng thi</label>
            <input className="field-input" value={form.header.room || ''} onChange={(e) => setHeader('room', e.target.value)} disabled={readOnly} placeholder="Tuỳ chọn" />
          </div>
          <div className="field-group">
            <label className="field-label">Ngày thi</label>
            <input className="field-input" value={form.header.exam_date || ''} onChange={(e) => setHeader('exam_date', e.target.value)} disabled={readOnly} placeholder="dd/mm/yyyy" />
          </div>
        </div>
      </div>

      <div className="section-actions">
        <button type="submit" className="btn btn--primary" disabled={saving || readOnly}>
          {saving ? 'Đang lưu...' : 'Lưu thông tin đề'}
        </button>
      </div>
    </form>
  );
}

// ======================== STEP 2: NỘI DUNG ĐỀ ========================
function ContentSection({ exam, chapters, onSaved, readOnly }) {
  const [matrixDirty, setMatrixDirty] = useState(false);
  const [matrixBusy, setMatrixBusy] = useState(false);
  const [questionBusy, setQuestionBusy] = useState(false);
  return (
    <div className="section-form">
      <MatrixBlock exam={exam} chapters={chapters} onSaved={onSaved} readOnly={readOnly || questionBusy} onDirtyChange={setMatrixDirty} onBusyChange={setMatrixBusy} />
      <QuestionsBlock exam={exam} chapters={chapters} onSaved={onSaved} readOnly={readOnly || matrixBusy} matrixDirty={matrixDirty} onBusyChange={setQuestionBusy} />
    </div>
  );
}

function MatrixBlock({ exam, chapters, onSaved, readOnly, onDirtyChange, onBusyChange }) {
  const [cells, setCells] = useState(exam.matrix?.length ? normalizeExamMatrix(exam.matrix) : [emptyCell()]);
  const [saving, setSaving] = useState(false);
  const [availability, setAvailability] = useState(null);
  const [checking, setChecking] = useState(false);
  useEffect(() => { onBusyChange(saving || checking); }, [saving, checking, onBusyChange]);
  const dirty = JSON.stringify(normalizeExamMatrix(cells)) !== JSON.stringify(normalizeExamMatrix(exam.matrix));
  useEffect(() => {
    onDirtyChange(dirty || saving);
    setAvailability(null);
  }, [dirty, saving, cells, onDirtyChange]);

  const updateCell = (index, patch) => {
    setCells((current) => current.map((cell, i) => (i === index ? { ...cell, ...patch } : cell)));
  };
  const addRow = () => setCells((current) => [...current, emptyCell()]);
  const removeRow = (index) => setCells((current) => (
    current.length <= 1 ? current : current.filter((_, i) => i !== index)
  ));

  const totalCount = cells.reduce((sum, cell) => sum + Number(cell.count || 0), 0);
  const targetCount = Number(exam.question_count) || 0;
  const matrixOver = targetCount > 0 && totalCount > targetCount;
  const matrixUnder = targetCount > 0 && totalCount < targetCount;
  const matrixOk = targetCount > 0 && totalCount === targetCount;

  const handleSave = async () => {
    if (readOnly || saving || checking) return;
    const normalizedCells = normalizeExamMatrix(cells);
    const validationError = examMatrixError(cells, targetCount);
    if (validationError) {
      alert(validationError);
      return;
    }
    setSaving(true);
    try {
      const updated = await saveMatrix(exam.id, normalizedCells);
      onSaved(updated);
      setAvailability(null);
    } catch (err) {
      alert('Lưu ma trận thất bại: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleCheck = async () => {
    if (dirty || saving || !exam.matrix?.length) return;
    setChecking(true);
    try {
      const result = await getMatrixAvailability(exam.id);
      setAvailability(result);
    } catch (err) {
      alert('Kiểm tra thất bại: ' + err.message);
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="section-block">
      <h3 className="step-title">1. Ma trận đề thi</h3>
      <p className="step-desc">
        Tổng: <b>{totalCount}</b> / {targetCount} câu
        {matrixOk && <span className="matrix-ok"> — Khớp số câu</span>}
        {matrixOver && <span className="matrix-warning"> — Vượt quá số câu đã khai báo</span>}
        {matrixUnder && <span className="matrix-warning"> — Thiếu {targetCount - totalCount} câu</span>}
      </p>
      <div className="matrix-table-wrap">
        <table className="matrix-table">
          <thead>
            <tr>
              <th>Chương</th>
              <th>Mức nhận thức Bloom</th>
              <th>Độ khó</th>
              <th>Số câu</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {cells.map((cell, index) => (
              <tr key={index}>
                <td>
                  <select className="field-select" value={cell.chapter_id || ''} onChange={(e) => updateCell(index, { chapter_id: e.target.value })} disabled={readOnly || saving || checking}>
                    <option value="">Tất cả chương</option>
                    {chapters.map((chapter) => (
                      <option key={chapter._id || chapter.id} value={chapter._id || chapter.id}>
                        {chapter.chapter_name}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <select className="field-select" value={cell.cognitive_level} onChange={(e) => updateCell(index, { cognitive_level: e.target.value })} disabled={readOnly || saving || checking}>
                    {COGNITIVE_LEVELS.map((lvl) => <option key={lvl.value} value={lvl.value}>{lvl.label}</option>)}
                  </select>
                </td>
                <td>
                  <select className="field-select" value={cell.difficulty || ''} onChange={(e) => updateCell(index, { difficulty: e.target.value })} disabled={readOnly || saving || checking}>
                    <option value="">Tất cả độ khó</option>
                    {DIFFICULTIES.map((difficulty) => <option key={difficulty.id} value={difficulty.id}>{difficulty.label}</option>)}
                  </select>
                </td>
                <td>
                  <input type="number" min={1} max={200} step={1} className="field-input matrix-count" value={cell.count} onChange={(e) => updateCell(index, { count: e.target.value })} disabled={readOnly || saving || checking} />
                </td>
                <td>
                  <button
                    type="button"
                    className="icon-btn icon-btn--danger"
                    onClick={() => removeRow(index)}
                    disabled={readOnly || saving || checking || cells.length <= 1}
                    title={cells.length <= 1 ? 'Cần giữ ít nhất một dòng' : 'Xoá dòng'}
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="section-actions section-actions--inline">
        <button type="button" className="btn btn--outline" onClick={addRow} disabled={readOnly || saving || checking}>+ Thêm nhóm</button>
        <button type="button" className="btn btn--outline" onClick={handleCheck} disabled={checking || saving || dirty || !exam.matrix?.length}>
          {checking ? 'Đang kiểm tra...' : 'Kiểm tra có đủ câu hỏi'}
        </button>
        <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving || checking || readOnly}>
          {saving ? 'Đang lưu...' : 'Lưu ma trận'}
        </button>
      </div>
      {dirty && <p className="matrix-save-note">Lưu ma trận trước khi kiểm tra hoặc tự chọn câu hỏi.</p>}
      {availability && (
        <div className="availability-list">
          {availability.map((item, index) => (
            <div key={index} className={`availability-item ${item.sufficient ? 'availability-ok' : 'availability-warn'}`}>
              {chapters.find((chapter) => refId(chapter) === item.chapter_id)?.chapter_name || 'Tất cả chương'} · {examBloomLevel(item.cognitive_level)?.label}:
              {' '}{item.available}/{item.requested} câu {item.sufficient ? '(đủ)' : '(thiếu)'}
              {!item.sufficient && item.available >= item.requested && ' — Câu hỏi trùng với nhóm khác, cần thêm câu hoặc điều chỉnh ma trận.'}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function QuestionsBlock({ exam, chapters, onSaved, readOnly, matrixDirty, onBusyChange }) {
  const [mode, setMode] = useState('auto');
  const [busy, setBusy] = useState(false);
  const [poolItems, setPoolItems] = useState([]);
  const [poolTotal, setPoolTotal] = useState(0);
  const [selectedIds, setSelectedIds] = useState([]);
  const [loadingApproved, setLoadingApproved] = useState(false);
  const [poolPage, setPoolPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [chapterFilter, setChapterFilter] = useState('');
  const [cognitiveFilter, setCognitiveFilter] = useState('');
  const poolRequest = useRef(0);
  useEffect(() => { onBusyChange(busy); }, [busy, onBusyChange]);

  const poolIds = new Set((exam.questions || []).map((q) => q.question_id));
  const poolPages = Math.max(1, Math.ceil(poolTotal / QUESTION_POOL_PAGE_SIZE));
  const visiblePoolItems = poolItems.filter((q) => !poolIds.has(q.id) && !q.in_exam);
  const hiddenInPage = poolItems.length - visiblePoolItems.length;

  useEffect(() => {
    const handle = setTimeout(() => {
      setSearchTerm(searchInput.trim());
      setPoolPage(1);
      setSelectedIds([]);
    }, 350);
    return () => clearTimeout(handle);
  }, [searchInput]);

  const loadApproved = useCallback(async () => {
    if (mode !== 'manual') return;
    const request = ++poolRequest.current;
    setLoadingApproved(true);
    try {
      const result = await listExamQuestionPool(exam.id, {
        page: poolPage,
        pageSize: QUESTION_POOL_PAGE_SIZE,
        search: searchTerm || undefined,
        chapterId: chapterFilter || undefined,
        bloomLevel: examBloomLevel(cognitiveFilter)?.level,
      });
      if (request !== poolRequest.current) return;
      setPoolItems(result.items || []);
      setPoolTotal(result.total || 0);
    } catch (err) {
      if (request !== poolRequest.current) return;
      alert('Tải câu hỏi thất bại: ' + err.message);
      setPoolItems([]);
      setPoolTotal(0);
    } finally {
      if (request === poolRequest.current) setLoadingApproved(false);
    }
  }, [chapterFilter, cognitiveFilter, exam.id, mode, poolPage, searchTerm]);

  useEffect(() => {
    loadApproved();
    return () => { poolRequest.current += 1; };
  }, [loadApproved]);

  useEffect(() => {
    setPoolPage(1);
    setSelectedIds([]);
  }, [chapterFilter, cognitiveFilter]);

  const handleAutoGenerate = async () => {
    if (readOnly || busy || matrixDirty) return;
    setBusy(true);
    try {
      const updated = await autoGenerateQuestions(exam.id);
      onSaved(updated);
      alert('Đã tự sinh đề theo ma trận.');
    } catch (err) {
      alert('Tự sinh đề thất bại: ' + err.message);
    } finally {
      setBusy(false);
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds((current) => (current.includes(id) ? current.filter((v) => v !== id) : [...current, id]));
  };

  const handleAddManual = async () => {
    if (readOnly || busy || selectedIds.length === 0) return;
    if (selectedIds.length + (exam.questions || []).length > Number(exam.question_count)) {
      alert('Số câu chọn vượt quá số câu còn thiếu trong đề.');
      return;
    }
    setBusy(true);
    try {
      const updated = await addQuestionsManual(exam.id, selectedIds);
      onSaved(updated);
      setSelectedIds([]);
      await loadApproved();
    } catch (err) {
      alert('Thêm câu hỏi thất bại: ' + err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (questionId) => {
    if (readOnly || busy) return;
    setBusy(true);
    try {
      const updated = await removeQuestion(exam.id, questionId);
      onSaved(updated);
      await loadApproved();
    } catch (err) {
      alert('Xoá câu hỏi thất bại: ' + err.message);
    } finally {
      setBusy(false);
    }
  };

  const currentCount = (exam.questions || []).length;
  const targetCount = Number(exam.question_count) || 0;
  const progressPct = targetCount > 0 ? Math.min(100, Math.round((currentCount / targetCount) * 100)) : 0;

  const getCognitiveLabel = (q) => {
    const bloom = q.classification?.bloom?.level;
    return BLOOM_LEVELS.find((level) => level.level === Number(bloom))?.label || null;
  };
  const getCognitiveClass = (q) => {
    const bloom = q.classification?.bloom?.level;
    const map = { 1: 'cog-blue', 2: 'cog-teal', 3: 'cog-orange', 4: 'cog-purple', 5: 'cog-teal', 6: 'cog-purple' };
    return map[bloom] || 'cog-gray';
  };
  const getChapterName = (q) => {
    const chapterId = q.classification?.chapter?.id || q.classification?.chapter_id;
    if (!chapterId) return null;
    const chap = chapters.find((c) => (c._id || c.id) === chapterId);
    return chap?.chapter_name || null;
  };

  return (
    <div className="section-block">
      <div className="pool-header">
        <h3 className="step-title">
          2. Chọn câu hỏi cho đề
          <span className="step-count">{currentCount}/{targetCount}</span>
        </h3>
        <div className="progress-bar" aria-label={`Đã chọn ${currentCount}/${targetCount}`}>
          <div className="progress-bar-fill" style={{ width: `${progressPct}%` }} />
        </div>
      </div>

      <div className="step-tabs">
        <button type="button" className={`step-tab ${mode === 'auto' ? 'step-tab--active' : ''}`} onClick={() => setMode('auto')}>
          Tự động theo ma trận
        </button>
        <button type="button" className={`step-tab ${mode === 'manual' ? 'step-tab--active' : ''}`} onClick={() => setMode('manual')}>
          Chọn thủ công
        </button>
      </div>

      {mode === 'auto' && (
        <div className="auto-note">
          <div className="auto-note-text">
            <b>Tự sinh câu hỏi theo ma trận</b>
            <p>Hệ thống sẽ bốc ngẫu nhiên các câu hỏi đã duyệt khớp với từng dòng trong ma trận.
            Nếu chạy nhiều lần, danh sách câu hỏi hiện tại sẽ bị thay thế.</p>
          </div>
          <button type="button" className="btn btn--primary btn--lg" onClick={handleAutoGenerate} disabled={busy || readOnly || matrixDirty || !exam.matrix?.length || exam.matrix.reduce((sum, cell) => sum + Number(cell.count), 0) !== targetCount}>
            {busy ? 'Đang sinh...' : 'Tự sinh câu hỏi'}
          </button>
        </div>
      )}

      {mode === 'manual' && (
        <div className="manual-wrap">
          <div className="pool-toolbar">
            <input
              className="field-input"
              placeholder="Tìm nội dung câu hỏi..."
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
            />
            <select className="field-select" value={chapterFilter} onChange={(event) => setChapterFilter(event.target.value)}>
              <option value="">Tất cả chương</option>
              {chapters.map((chapter) => (
                <option key={chapter._id || chapter.id} value={chapter._id || chapter.id}>
                  {chapter.chapter_name}
                </option>
              ))}
            </select>
            <select className="field-select" value={cognitiveFilter} onChange={(event) => setCognitiveFilter(event.target.value)}>
              <option value="">Tất cả mức</option>
              {COGNITIVE_LEVELS.map((level) => (
                <option key={level.value} value={level.value}>{level.label}</option>
              ))}
            </select>
          </div>

          {loadingApproved ? (
            <p className="empty-note">Đang tải câu hỏi đã duyệt...</p>
          ) : visiblePoolItems.length === 0 ? (
            <div className="empty-pool">
              <p>Không có câu hỏi đã duyệt phù hợp với bộ lọc.</p>
              <small>Thử thay đổi chương hoặc mức nhận thức ở trên.</small>
            </div>
          ) : (
            <div className="question-pick-list">
              {visiblePoolItems.map((q, idx) => {
                const checked = selectedIds.includes(q.id);
                const cogLabel = getCognitiveLabel(q);
                const cogClass = getCognitiveClass(q);
                const chapterName = getChapterName(q);
                return (
                  <label className={`question-pick-item ${checked ? 'is-checked' : ''}`} key={q.id}>
                    <input type="checkbox" checked={checked} onChange={() => toggleSelect(q.id)} disabled={readOnly || busy || (!checked && selectedIds.length >= targetCount - currentCount)} />
                    <div className="qpi-body">
                      <div className="qpi-meta">
                        <span className="qpi-num">#{(poolPage - 1) * QUESTION_POOL_PAGE_SIZE + idx + 1}</span>
                        {cogLabel && <span className={`qpi-tag qpi-tag--${cogClass}`}>{cogLabel}</span>}
                        {chapterName && <span className="qpi-tag qpi-tag--chapter">{chapterName}</span>}
                        <span className="qpi-tag qpi-tag--type">{questionTypeLabel((q.classification?.assessment_type || '').toLowerCase()) || 'Trắc nghiệm'}</span>
                      </div>
                      <div className="qpi-content">{q.content}</div>
                    </div>
                  </label>
                );
              })}
            </div>
          )}

          <div className="pool-footer">
            <div className="pool-pagination">
              <button type="button" className="btn btn--outline btn--sm" disabled={poolPage <= 1 || loadingApproved} onClick={() => setPoolPage((page) => Math.max(1, page - 1))}>
                ← Trước
              </button>
              <span>Trang {poolPage}/{poolPages} · {poolTotal} câu{hiddenInPage > 0 ? ` (${hiddenInPage} đã trong đề)` : ''}</span>
              <button type="button" className="btn btn--outline btn--sm" disabled={poolPage >= poolPages || loadingApproved} onClick={() => setPoolPage((page) => Math.min(poolPages, page + 1))}>
                Sau →
              </button>
            </div>

            <button type="button" className="btn btn--primary" onClick={handleAddManual} disabled={busy || readOnly || selectedIds.length === 0}>
              {busy
                ? 'Đang thêm...'
                : selectedIds.length === 0
                  ? 'Chọn câu để thêm'
                  : `+ Thêm ${selectedIds.length} câu vào đề`}
            </button>
          </div>
        </div>
      )}

      <h4 className="pool-title">
        Câu hỏi hiện có trong đề
        <span className="step-count">{currentCount}/{targetCount}</span>
      </h4>
      <div className="question-pool-list">
        {(exam.questions || []).map((ref, index) => (
          <div className="question-pool-item" key={ref.question_id}>
            <span className="qpl-num">Câu {index + 1}</span>
            <span className="qpl-content">{ref.content_snapshot?.content}</span>
            <button type="button" className="icon-btn icon-btn--danger" onClick={() => handleRemove(ref.question_id)} disabled={readOnly || busy} title="Xoá câu khỏi đề">×</button>
          </div>
        ))}
        {(exam.questions || []).length === 0 && <p className="empty-note">Chưa có câu hỏi nào trong đề.</p>}
      </div>
    </div>
  );
}

// ======================== STEP 3: XUẤT ĐỀ ========================
function ExportSection({ exam, onSaved, onStatusChange }) {
  const [variants, setVariants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [desiredCount, setDesiredCount] = useState(1);
  const [codeDrafts, setCodeDrafts] = useState([DEFAULT_VARIANT_CODES[0]]);
  const [shuffle, setShuffle] = useState(true);
  const [busy, setBusy] = useState(false);
  const [previewId, setPreviewId] = useState('');
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [exportBusy, setExportBusy] = useState('');

  const status = examStatus(exam);
  const finalized = status === 'FINALIZED';
  const selectedCount = exam.questions?.length || 0;
  const targetCount = Number(exam.question_count) || 0;
  const remainingSlots = Math.max(0, MAX_VARIANTS - variants.length);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await listVariants(exam.id);
      setVariants(result || []);
      setPreviewId((current) => result?.some((variant) => variant.id === current) ? current : result?.[0]?.id || '');
      onSaved((current) => ({ ...current, variant_count: result?.length || 0 }));
    } catch (err) {
      alert('Tải mã đề thất bại: ' + err.message);
    } finally {
      setLoading(false);
    }
  }, [exam.id, onSaved]);

  useEffect(() => {
    load();
  }, [load]);

  // Chỉnh lại số lượng mã đề cần tạo và các input mã khi remainingSlots thay đổi
  useEffect(() => {
    const existingCodes = new Set(variants.map((v) => (v.exam_code || '').trim()));
    const safeCount = Math.min(Math.max(1, desiredCount), Math.max(1, remainingSlots || 1));
    setCodeDrafts((prev) => {
      const next = [];
      let suggestIdx = 0;
      for (let i = 0; i < safeCount; i += 1) {
        if (prev[i] && !existingCodes.has(prev[i].trim())) {
          next.push(prev[i]);
        } else {
          // gợi ý mã đề mặc định chưa trùng
          let candidate = '';
          while (suggestIdx < DEFAULT_VARIANT_CODES.length && !candidate) {
            const c = DEFAULT_VARIANT_CODES[suggestIdx];
            suggestIdx += 1;
            if (!existingCodes.has(c)) candidate = c;
          }
          next.push(candidate);
        }
      }
      return next;
    });
  }, [desiredCount, remainingSlots, variants]);

  useEffect(() => {
    let active = true;
    setPreview(null);
    if (!previewId) {
      setPreviewLoading(false);
      return;
    }
    setPreviewLoading(true);
    getVariantPreview(exam.id, previewId)
      .then((result) => { if (active) setPreview(result); })
      .catch((err) => { if (active) alert('Xem trước thất bại: ' + err.message); })
      .finally(() => { if (active) setPreviewLoading(false); });
    return () => { active = false; };
  }, [exam.id, previewId]);

  const updateDraft = (index, value) => {
    setCodeDrafts((current) => current.map((c, i) => (i === index ? value : c)));
  };

  const handleCreateBatch = async (e) => {
    e.preventDefault();
    if (!finalized) return;
    const existingCodes = new Set(variants.map((v) => (v.exam_code || '').trim()));
    const codes = codeDrafts.map((c) => (c || '').trim()).slice(0, remainingSlots);
    const invalid = codes.findIndex((c) => !c);
    if (invalid >= 0) {
      alert(`Mã đề thứ ${invalid + 1} chưa được nhập.`);
      return;
    }
    const dupInBatch = codes.findIndex((c, i) => codes.indexOf(c) !== i);
    if (dupInBatch >= 0) {
      alert(`Mã đề "${codes[dupInBatch]}" bị lặp trong danh sách sắp tạo.`);
      return;
    }
    const dupExisting = codes.findIndex((c) => existingCodes.has(c));
    if (dupExisting >= 0) {
      alert(`Mã đề "${codes[dupExisting]}" đã tồn tại.`);
      return;
    }
    setBusy(true);
    try {
      for (const code of codes) {
        await createVariant(exam.id, code, shuffle);
      }
      setCodeDrafts([]);
      setDesiredCount(1);
      await load();
    } catch (err) {
      alert('Tạo mã đề thất bại: ' + err.message);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (variantId) => {
    if (!window.confirm('Xoá mã đề này?')) return;
    setBusy(true);
    try {
      await deleteVariant(exam.id, variantId);
      if (previewId === variantId) setPreviewId('');
      await load();
    } catch (err) {
      alert('Xoá mã đề thất bại: ' + err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleExport = async (variantId, type, format) => {
    const key = `${variantId}-${type}-${format}`;
    setExportBusy(key);
    try {
      if (format === 'docx') {
        await downloadVariantDocx(exam.id, variantId, type);
      } else {
        await downloadVariantPdf(exam.id, variantId, type);
      }
    } catch (err) {
      alert(`Xuất ${format.toUpperCase()} thất bại: ${err.message}`);
    } finally {
      setExportBusy('');
    }
  };

  return (
    <div className="section-form">
      <div className="section-block">
        <h3 className="step-title">
          1. Mã đề
          <span className="step-count">{variants.length}/{MAX_VARIANTS}</span>
        </h3>
        <p className="step-desc">
          Mỗi mã đề là một bản của cùng đề thi — có thể giữ nguyên thứ tự hoặc xáo trộn câu hỏi/đáp án.
          Tối đa <b>{MAX_VARIANTS}</b> mã đề cho một kỳ thi.
        </p>

        {!finalized && (
          <div className="locked-note export-status-note">
            {status === 'ARCHIVED' ? (
              <span>Đề đã lưu trữ. Bạn vẫn có thể xem trước và xuất các mã đề đã tạo.</span>
            ) : (
              <>
                <span>
                  {selectedCount !== targetCount
                    ? `Cần chọn đủ ${targetCount} câu hỏi trước khi tạo mã đề (hiện có ${selectedCount}).`
                    : status === 'READY'
                      ? 'Chốt đề để bật nút tạo mã đề.'
                      : 'Đánh dấu sẵn sàng, sau đó chốt đề để bật nút tạo mã đề.'}
                </span>
                {selectedCount === targetCount && status === 'DRAFT' && (
                  <button type="button" className="btn btn--outline" onClick={() => onStatusChange('READY')}>Đánh dấu sẵn sàng</button>
                )}
                {selectedCount === targetCount && status === 'READY' && (
                  <button type="button" className="btn btn--primary" onClick={() => onStatusChange('FINALIZED')}>Chốt đề</button>
                )}
              </>
            )}
          </div>
        )}

        {loading ? (
          <p className="empty-note">Đang tải...</p>
        ) : variants.length > 0 ? (
          <div className="variant-grid">
            {variants.map((variant) => (
              <div className={`variant-card ${previewId === variant.id ? 'is-active' : ''}`} key={variant.id}>
                <button type="button" className="variant-card-select" onClick={() => setPreviewId(variant.id)}>
                  <span className="variant-card-code">Mã đề</span>
                  <span className="variant-card-value">{variant.exam_code}</span>
                  <span className="variant-card-meta">{(variant.questions || []).length} câu</span>
                </button>
                <button type="button" className="icon-btn icon-btn--danger" onClick={() => handleDelete(variant.id)} disabled={busy} title="Xoá mã đề">×</button>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-note">Chưa có mã đề nào. Nhập mã bên dưới và bấm "Tạo mã đề".</p>
        )}

        {remainingSlots > 0 && (
          <form className="variant-builder" onSubmit={handleCreateBatch}>
            <div className="variant-builder-head">
              <label className="field-label">Số mã đề muốn tạo thêm</label>
              <div className="count-stepper">
                <button type="button" className="count-stepper-btn" onClick={() => setDesiredCount((v) => Math.max(1, v - 1))} disabled={!finalized || desiredCount <= 1 || busy}>−</button>
                <span className="count-stepper-value">{Math.min(desiredCount, remainingSlots)}</span>
                <button type="button" className="count-stepper-btn" onClick={() => setDesiredCount((v) => Math.min(remainingSlots, v + 1))} disabled={!finalized || desiredCount >= remainingSlots || busy}>+</button>
                <small>còn tối đa {remainingSlots} slot</small>
              </div>
            </div>

            <div className="variant-code-list">
              {codeDrafts.map((code, index) => (
                <div className="variant-code-row" key={index}>
                  <span className="variant-code-label">Mã đề #{index + 1}</span>
                  <input
                    className="field-input"
                    placeholder={DEFAULT_VARIANT_CODES[index] || 'VD: 132'}
                    value={code}
                    onChange={(e) => updateDraft(index, e.target.value)}
                    disabled={!finalized || busy}
                    maxLength={40}
                  />
                </div>
              ))}
            </div>

            <div className="variant-builder-foot">
              <label className="variant-shuffle-check">
                <input type="checkbox" checked={shuffle} onChange={(e) => setShuffle(e.target.checked)} disabled={!finalized || busy} />
                Xáo trộn thứ tự câu hỏi & đáp án giữa các mã đề
              </label>
              <button type="submit" className="btn btn--primary" disabled={!finalized || busy || loading}>
                {busy ? 'Đang tạo...' : `Tạo ${codeDrafts.length} mã đề`}
              </button>
            </div>
          </form>
        )}

        {finalized && remainingSlots === 0 && (
          <p className="empty-note">Đã đạt tối đa {MAX_VARIANTS} mã đề. Xoá bớt mã cũ nếu muốn tạo mới.</p>
        )}
      </div>

      <div className="section-block">
        <h3 className="step-title">2. Xem trước & Xuất đề</h3>
        {variants.length === 0 ? (
          <p className="empty-note">Hãy tạo ít nhất một mã đề để xem trước và xuất file.</p>
        ) : (
          <>
            <div className="field-group">
              <label className="field-label">Chọn mã đề để xem trước và xuất</label>
              <select className="field-select" value={previewId} onChange={(e) => setPreviewId(e.target.value)}>
                {variants.map((v) => <option key={v.id} value={v.id}>Mã đề {v.exam_code}</option>)}
              </select>
            </div>

            <div className="export-grid">
              {EXPORT_VARIANT_TYPES.map((exportType) => (
                <div className="export-card" key={exportType.value}>
                  <span className="export-card-label">{exportType.label}</span>
                  <div className="export-card-actions">
                    {EXPORT_FORMATS.map((format) => {
                      const key = `${previewId}-${exportType.value}-${format.value}`;
                      return (
                        <button
                          type="button"
                          className="btn btn--outline"
                          disabled={!previewId || Boolean(exportBusy) || busy}
                          onClick={() => handleExport(previewId, exportType.value, format.value)}
                          key={format.value}
                        >
                          {exportBusy === key ? 'Đang xuất...' : format.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            {previewLoading && <p className="empty-note">Đang tải preview...</p>}
            {preview && (
              <div className="exam-preview">
                <div className="preview-header">
                  <div>
                    <b>{preview.header.school_name}</b>
                    <div>{preview.header.faculty_name}</div>
                  </div>
                  <div className="preview-header-right">
                    <div>{preview.header.exam_name}</div>
                    <div>Thời gian: {preview.header.duration_minutes} phút</div>
                    <div>Mã đề: {preview.exam_code}</div>
                  </div>
                </div>
                <h4 className="preview-title">Môn: {preview.header.subject_name}</h4>
                {preview.questions.map((q) => (
                  <div className="preview-question" key={q.number}>
                    <p><b>Câu {q.number}.</b> {q.content}</p>
                    {q.options.map((opt) => (
                      <div className="preview-option" key={opt.label}>{opt.label}. {opt.text}</div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default ExamBuilderPage;
