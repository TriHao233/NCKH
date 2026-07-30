import React, { useCallback, useEffect, useMemo, useState } from 'react';
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
import { questionTypeLabel } from '../constants/generationEnums';
import '../css/ExamBuilderPage.css';

function refId(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  return value.id || value._id || '';
}

const COGNITIVE_LEVELS = [
  { value: 'nhan_biet', label: 'Nhận biết' },
  { value: 'thong_hieu', label: 'Thông hiểu' },
  { value: 'van_dung', label: 'Vận dụng' },
  { value: 'van_dung_cao', label: 'Vận dụng cao' },
];

const DIFFICULTIES = [
  { value: 'de', label: 'Dễ' },
  { value: 'trung_binh', label: 'Trung bình' },
  { value: 'kho', label: 'Khó' },
];

const COGNITIVE_TO_BLOOM = {
  nhan_biet: 1,
  thong_hieu: 2,
  van_dung: 3,
  van_dung_cao: 4,
};

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

function examStatus(exam) {
  return String(exam?.status || 'DRAFT').toUpperCase();
}

function isExamLocked(exam) {
  return ['FINALIZED', 'ARCHIVED'].includes(examStatus(exam));
}

const STEPS = [
  { id: 'info', label: '1. Thông tin đề thi' },
  { id: 'header', label: '2. Đầu trang' },
  { id: 'matrix', label: '3. Ma trận đề' },
  { id: 'questions', label: '4. Chọn câu hỏi' },
  { id: 'variants', label: '5. Mã đề' },
  { id: 'preview', label: '6. Xem trước' },
  { id: 'export', label: '7. Xuất đề' },
];

function emptyCell() {
  return { chapter_id: '', cognitive_level: 'nhan_biet', difficulty: 'de', count: 1 };
}

function ExamBuilderPage() {
  const { examId } = useParams();
  const navigate = useNavigate();
  const [exam, setExam] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [step, setStep] = useState('info');
  const [subjects, setSubjects] = useState([]);
  const [notice, setNotice] = useState(null);
  const [statusAction, setStatusAction] = useState(null);
  const [statusSaving, setStatusSaving] = useState(false);

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

  const notify = useCallback((message, tone = 'error') => {
    setNotice({ message, tone });
  }, []);

  useEffect(() => {
    if (!statusAction) return undefined;
    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !statusSaving) setStatusAction(null);
    };
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [statusAction, statusSaving]);

  const applyStatusChange = async (targetStatus) => {
    setStatusSaving(true);
    try {
      const updated = await updateExamStatus(exam.id, targetStatus);
      setExam(updated);
      notify(
        targetStatus === 'FINALIZED'
          ? 'Đã chốt đề thi.'
          : targetStatus === 'ARCHIVED'
            ? 'Đã lưu trữ đề thi.'
            : 'Đã cập nhật trạng thái.',
        'success',
      );
    } catch (err) {
      notify(`Không thể cập nhật trạng thái: ${err.message}`);
    } finally {
      setStatusSaving(false);
    }
  };

  const handleStatusChange = (targetStatus) => {
    if (targetStatus === 'FINALIZED') {
      setStatusAction({
        targetStatus,
        title: 'Chốt đề thi?',
        message: 'Ma trận và danh sách câu hỏi sẽ bị khóa.',
        confirmLabel: 'Chốt đề',
      });
      return;
    }
    if (targetStatus === 'ARCHIVED') {
      setStatusAction({
        targetStatus,
        title: 'Lưu trữ đề thi?',
        message: 'Đề thi sẽ được chuyển khỏi nhóm đang làm việc.',
        confirmLabel: 'Lưu trữ',
      });
      return;
    }
    applyStatusChange(targetStatus);
  };

  const confirmStatusChange = async () => {
    if (!statusAction) return;
    const { targetStatus } = statusAction;
    await applyStatusChange(targetStatus);
    setStatusAction(null);
  };

  if (loading) return <main className="exam-builder-page"><p className="empty-note">Đang tải đề thi...</p></main>;
  if (error) return <main className="exam-builder-page"><p className="exam-error">{error}</p></main>;
  if (!exam) return null;

  return (
    <main className="exam-builder-page">
      <section className="builder-hero">
        <div className="container">
          <button type="button" className="btn btn--outline" onClick={() => navigate('/lam-de-thi')}>
            ← Danh sách đề thi
          </button>
          <h1 className="page-hero-title">{exam.name}</h1>
          <p className="page-hero-desc">{exam.exam_title}</p>
        </div>
      </section>

      <section className="builder-body">
        <div className="container builder-grid">
          <nav className="builder-steps">
            {STEPS.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`builder-step ${step === s.id ? 'builder-step--active' : ''}`}
                onClick={() => setStep(s.id)}
              >
                {s.label}
              </button>
            ))}
          </nav>

          <div className="builder-content card">
            <LifecycleBar
              exam={exam}
              status={statusValue}
              onStatusChange={handleStatusChange}
              busy={statusSaving}
            />
            {notice && (
              <div
                className={`builder-notice builder-notice--${notice.tone}`}
                role={notice.tone === 'error' ? 'alert' : 'status'}
              >
                <span>{notice.message}</span>
                <button type="button" onClick={() => setNotice(null)} aria-label="Đóng thông báo">×</button>
              </div>
            )}
            {locked && (
              <p className="locked-note">
                Đề thi đã {statusValue === 'ARCHIVED' ? 'lưu trữ' : 'chốt'}; thông tin, ma trận và danh sách câu hỏi đang được khóa.
              </p>
            )}
            {step === 'info' && <InfoStep exam={exam} onSaved={setExam} readOnly={locked} onNotify={notify} />}
            {step === 'header' && <HeaderStep exam={exam} onSaved={setExam} readOnly={locked} onNotify={notify} />}
            {step === 'matrix' && <MatrixStep exam={exam} chapters={chapters} onSaved={setExam} readOnly={locked} onNotify={notify} />}
            {step === 'questions' && <QuestionsStep exam={exam} chapters={chapters} onSaved={setExam} readOnly={locked} onNotify={notify} />}
            {step === 'variants' && <VariantsStep exam={exam} onNotify={notify} />}
            {step === 'preview' && <PreviewStep exam={exam} onNotify={notify} />}
            {step === 'export' && <ExportStep exam={exam} onNotify={notify} />}
          </div>
        </div>
      </section>

      {statusAction && (
        <div
          className="exam-dialog-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !statusSaving) setStatusAction(null);
          }}
        >
          <section className="exam-dialog" role="dialog" aria-modal="true" aria-labelledby="exam-status-dialog-title">
            <span className="exam-dialog__eyebrow">Trạng thái đề thi</span>
            <h2 id="exam-status-dialog-title">{statusAction.title}</h2>
            <p>{statusAction.message}</p>
            <div className="exam-dialog__actions">
              <button type="button" className="btn btn--outline" onClick={() => setStatusAction(null)} disabled={statusSaving}>
                Hủy
              </button>
              <button type="button" className="btn btn--primary" onClick={confirmStatusChange} disabled={statusSaving}>
                {statusSaving ? 'Đang cập nhật...' : statusAction.confirmLabel}
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}

function LifecycleBar({ exam, status, onStatusChange, busy }) {
  const selectedCount = exam.questions?.length || 0;
  const hasExactQuestionCount = selectedCount === exam.question_count;
  const canReady = status === 'DRAFT' && hasExactQuestionCount;
  const canFinalize = status === 'READY' && hasExactQuestionCount;
  const canArchive = status === 'FINALIZED';

  return (
    <section className="lifecycle-bar">
      <div>
        <span className={`exam-status-pill exam-status-pill--${status.toLowerCase()}`}>
          {EXAM_STATUS_LABEL[status] || status}
        </span>
        <b>{selectedCount}/{exam.question_count} câu</b>
        {!hasExactQuestionCount && (
          <small>Cần đủ đúng số câu để chuyển sẵn sàng hoặc chốt đề.</small>
        )}
      </div>
      <div className="lifecycle-actions">
        {status === 'READY' && (
          <button type="button" className="btn btn--outline" onClick={() => onStatusChange('DRAFT')} disabled={busy}>
            Mở chỉnh
          </button>
        )}
        {status === 'DRAFT' && (
          <button type="button" className="btn btn--outline" disabled={!canReady || busy} onClick={() => onStatusChange('READY')}>
            Đánh dấu sẵn sàng
          </button>
        )}
        {status === 'READY' && (
          <button type="button" className="btn btn--primary" disabled={!canFinalize || busy} onClick={() => onStatusChange('FINALIZED')}>
            Chốt đề
          </button>
        )}
        {canArchive && (
          <button type="button" className="btn btn--outline" onClick={() => onStatusChange('ARCHIVED')} disabled={busy}>
            Lưu trữ
          </button>
        )}
      </div>
    </section>
  );
}

function InfoStep({ exam, onSaved, readOnly, onNotify }) {
  const [name, setName] = useState(exam.name);
  const [examTitle, setExamTitle] = useState(exam.exam_title);
  const [questionCount, setQuestionCount] = useState(exam.question_count);
  const [saving, setSaving] = useState(false);

  const handleSave = async (e) => {
    e.preventDefault();
    if (readOnly) return;
    setSaving(true);
    try {
      const updated = await updateExam(exam.id, {
        name: name.trim(),
        exam_title: examTitle.trim(),
        question_count: Number(questionCount),
      });
      onSaved(updated);
      onNotify('Đã lưu thông tin đề thi.', 'success');
    } catch (err) {
      onNotify(`Không thể lưu thông tin: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSave}>
      <h3 className="step-title">Thông tin đề thi</h3>
      <div className="field-group">
        <label className="field-label">Tên đề thi</label>
        <input className="field-input" value={name} onChange={(e) => setName(e.target.value)} disabled={readOnly} />
      </div>
      <div className="field-group">
        <label className="field-label">Tên kỳ thi</label>
        <input className="field-input" value={examTitle} onChange={(e) => setExamTitle(e.target.value)} disabled={readOnly} />
      </div>
      <div className="field-group">
        <label className="field-label">Số lượng câu hỏi</label>
        <input type="number" min={1} max={200} className="field-input" value={questionCount} onChange={(e) => setQuestionCount(e.target.value)} disabled={readOnly} />
      </div>
      <button type="submit" className="btn btn--primary" disabled={saving || readOnly}>{saving ? 'Đang lưu...' : 'Lưu'}</button>
    </form>
  );
}

function HeaderStep({ exam, onSaved, readOnly, onNotify }) {
  const [header, setHeader] = useState({ ...exam.header });
  const [saving, setSaving] = useState(false);

  const setField = (key, value) => setHeader((h) => ({ ...h, [key]: value }));

  const handleSave = async (e) => {
    e.preventDefault();
    if (readOnly) return;
    setSaving(true);
    try {
      const updated = await updateExam(exam.id, { header });
      onSaved(updated);
      onNotify('Đã lưu đầu trang.', 'success');
    } catch (err) {
      onNotify(`Không thể lưu đầu trang: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSave}>
      <h3 className="step-title">Cấu hình đầu trang đề thi</h3>
      <div className="field-group">
        <label className="field-label">Tên Trường/Đại học</label>
        <input className="field-input" value={header.school_name || ''} onChange={(e) => setField('school_name', e.target.value)} disabled={readOnly} />
      </div>
      <div className="field-group">
        <label className="field-label">Tên Khoa/Bộ môn</label>
        <input className="field-input" value={header.faculty_name || ''} onChange={(e) => setField('faculty_name', e.target.value)} disabled={readOnly} />
      </div>
      <div className="field-group">
        <label className="field-label">Tên kỳ thi (hiển thị trên đầu trang)</label>
        <input className="field-input" value={header.exam_name || ''} onChange={(e) => setField('exam_name', e.target.value)} disabled={readOnly} />
      </div>
      <div className="field-group">
        <label className="field-label">Tên môn học/học phần</label>
        <input className="field-input" value={header.subject_name || ''} onChange={(e) => setField('subject_name', e.target.value)} disabled={readOnly} />
      </div>
      <div className="field-group">
        <label className="field-label">Thời gian làm bài (phút)</label>
        <input type="number" min={1} className="field-input" value={header.duration_minutes || 60} onChange={(e) => setField('duration_minutes', Number(e.target.value))} disabled={readOnly} />
      </div>
      <div className="field-group">
        <label className="field-label">Lớp (tuỳ chọn)</label>
        <input className="field-input" value={header.class_name || ''} onChange={(e) => setField('class_name', e.target.value)} disabled={readOnly} />
      </div>
      <div className="field-group">
        <label className="field-label">Phòng thi (tuỳ chọn)</label>
        <input className="field-input" value={header.room || ''} onChange={(e) => setField('room', e.target.value)} disabled={readOnly} />
      </div>
      <div className="field-group">
        <label className="field-label">Ngày thi (tuỳ chọn)</label>
        <input className="field-input" value={header.exam_date || ''} onChange={(e) => setField('exam_date', e.target.value)} placeholder="dd/mm/yyyy" disabled={readOnly} />
      </div>
      <button type="submit" className="btn btn--primary" disabled={saving || readOnly}>{saving ? 'Đang lưu...' : 'Lưu đầu trang'}</button>
    </form>
  );
}

function MatrixStep({ exam, chapters, onSaved, readOnly, onNotify }) {
  const [cells, setCells] = useState(exam.matrix?.length ? exam.matrix : [emptyCell()]);
  const [saving, setSaving] = useState(false);
  const [availability, setAvailability] = useState(null);
  const [checking, setChecking] = useState(false);

  const updateCell = (index, patch) => {
    setCells((current) => current.map((cell, i) => (i === index ? { ...cell, ...patch } : cell)));
  };
  const addRow = () => setCells((current) => [...current, emptyCell()]);
  const removeRow = (index) => setCells((current) => current.filter((_, i) => i !== index));

  const totalCount = cells.reduce((sum, cell) => sum + Number(cell.count || 0), 0);

  const handleSave = async () => {
    if (readOnly) return;
    setSaving(true);
    try {
      const payload = cells.map((cell) => ({
        ...cell,
        chapter_id: cell.chapter_id || null,
        count: Number(cell.count),
      }));
      const updated = await saveMatrix(exam.id, payload);
      onSaved(updated);
      setAvailability(null);
      onNotify('Đã lưu ma trận.', 'success');
    } catch (err) {
      onNotify(`Không thể lưu ma trận: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleCheck = async () => {
    setChecking(true);
    try {
      const result = await getMatrixAvailability(exam.id);
      setAvailability(result);
    } catch (err) {
      onNotify(`Không thể kiểm tra ngân hàng: ${err.message}`);
    } finally {
      setChecking(false);
    }
  };

  return (
    <div>
      <h3 className="step-title">Ma trận đề thi</h3>
      <p className="step-desc">
        Tổng số câu trong ma trận: <b>{totalCount}</b> / Số câu đề thi yêu cầu: <b>{exam.question_count}</b>
        {totalCount > exam.question_count && (
          <span className="matrix-warning"> — Vượt quá số câu đã khai báo!</span>
        )}
      </p>
      <table className="matrix-table">
        <thead>
          <tr>
            <th>Chương</th>
            <th>Mức nhận thức</th>
            <th>Độ khó</th>
            <th>Số câu</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {cells.map((cell, index) => (
            <tr key={index}>
              <td>
                <select className="field-select" value={cell.chapter_id || ''} onChange={(e) => updateCell(index, { chapter_id: e.target.value })} disabled={readOnly}>
                  <option value="">Tất cả chương</option>
                  {chapters.map((chapter) => (
                    <option key={chapter._id || chapter.id} value={chapter._id || chapter.id}>
                      {chapter.chapter_name}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <select className="field-select" value={cell.cognitive_level} onChange={(e) => updateCell(index, { cognitive_level: e.target.value })} disabled={readOnly}>
                  {COGNITIVE_LEVELS.map((lvl) => <option key={lvl.value} value={lvl.value}>{lvl.label}</option>)}
                </select>
              </td>
              <td>
                <select className="field-select" value={cell.difficulty} onChange={(e) => updateCell(index, { difficulty: e.target.value })} disabled={readOnly}>
                  {DIFFICULTIES.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </select>
              </td>
              <td>
                <input type="number" min={1} className="field-input matrix-count" value={cell.count} onChange={(e) => updateCell(index, { count: e.target.value })} disabled={readOnly} />
              </td>
              <td>
                <button type="button" className="icon-btn icon-btn--danger" onClick={() => removeRow(index)} disabled={readOnly}>×</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="step-actions">
        <button type="button" className="btn btn--outline" onClick={addRow} disabled={readOnly}>+ Thêm nhóm</button>
        <button type="button" className="btn btn--outline" onClick={handleCheck} disabled={checking}>
          {checking ? 'Đang kiểm tra...' : 'Kiểm tra đủ câu hỏi'}
        </button>
        <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving || readOnly}>
          {saving ? 'Đang lưu...' : 'Lưu ma trận'}
        </button>
      </div>
      {availability && (
        <div className="availability-list">
          {availability.map((item, index) => (
            <div key={index} className={`availability-item ${item.sufficient ? 'availability-ok' : 'availability-warn'}`}>
              {COGNITIVE_LEVELS.find((l) => l.value === item.cognitive_level)?.label} · {DIFFICULTIES.find((d) => d.value === item.difficulty)?.label}:
              {' '}{item.available}/{item.requested} câu {item.sufficient ? '(đủ)' : '(thiếu)'}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function QuestionsStep({ exam, chapters, onSaved, readOnly, onNotify }) {
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
  const [difficultyFilter, setDifficultyFilter] = useState('');

  const poolIds = new Set((exam.questions || []).map((q) => q.question_id));
  const poolPages = Math.max(1, Math.ceil(poolTotal / QUESTION_POOL_PAGE_SIZE));
  const visiblePoolItems = poolItems.filter((q) => !poolIds.has(q.id) && !q.in_exam);

  useEffect(() => {
    const handle = setTimeout(() => {
      setSearchTerm(searchInput.trim());
      setPoolPage(1);
    }, 350);
    return () => clearTimeout(handle);
  }, [searchInput]);

  const loadApproved = useCallback(async () => {
    if (mode !== 'manual') return;
    setLoadingApproved(true);
    try {
      const result = await listExamQuestionPool(exam.id, {
        page: poolPage,
        pageSize: QUESTION_POOL_PAGE_SIZE,
        search: searchTerm || undefined,
        chapterId: chapterFilter || undefined,
        bloomLevel: cognitiveFilter ? COGNITIVE_TO_BLOOM[cognitiveFilter] : undefined,
        difficulty: difficultyFilter || undefined,
      });
      setPoolItems(result.items || []);
      setPoolTotal(result.total || 0);
    } catch (err) {
      onNotify(`Không thể tải câu hỏi: ${err.message}`);
      setPoolItems([]);
      setPoolTotal(0);
    } finally {
      setLoadingApproved(false);
    }
  }, [chapterFilter, cognitiveFilter, difficultyFilter, exam.id, mode, onNotify, poolPage, searchTerm]);

  useEffect(() => {
    loadApproved();
  }, [loadApproved]);

  useEffect(() => {
    setPoolPage(1);
    setSelectedIds([]);
  }, [chapterFilter, cognitiveFilter, difficultyFilter]);

  const handleAutoGenerate = async () => {
    if (readOnly) return;
    setBusy(true);
    try {
      const updated = await autoGenerateQuestions(exam.id);
      onSaved(updated);
      onNotify('Đã chọn câu hỏi theo ma trận.', 'success');
    } catch (err) {
      onNotify(`Không thể chọn câu hỏi: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds((current) => (current.includes(id) ? current.filter((v) => v !== id) : [...current, id]));
  };

  const handleAddManual = async () => {
    if (readOnly || selectedIds.length === 0) return;
    setBusy(true);
    try {
      const updated = await addQuestionsManual(exam.id, selectedIds);
      onSaved(updated);
      setSelectedIds([]);
      await loadApproved();
      onNotify(`Đã thêm ${selectedIds.length} câu hỏi.`, 'success');
    } catch (err) {
      onNotify(`Không thể thêm câu hỏi: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (questionId) => {
    if (readOnly) return;
    setBusy(true);
    try {
      const updated = await removeQuestion(exam.id, questionId);
      onSaved(updated);
      onNotify('Đã bỏ câu hỏi khỏi đề.', 'success');
    } catch (err) {
      onNotify(`Không thể bỏ câu hỏi: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h3 className="step-title">Chọn câu hỏi từ ngân hàng đã duyệt</h3>
      <div className="step-tabs">
        <button type="button" className={`step-tab ${mode === 'auto' ? 'step-tab--active' : ''}`} onClick={() => setMode('auto')}>Tự sinh theo ma trận</button>
        <button type="button" className={`step-tab ${mode === 'manual' ? 'step-tab--active' : ''}`} onClick={() => setMode('manual')}>Chọn thủ công</button>
      </div>

      {mode === 'auto' && (
        <div className="step-actions">
          <button type="button" className="btn btn--primary" onClick={handleAutoGenerate} disabled={busy || readOnly}>
            {busy ? 'Đang sinh đề...' : 'Tự sinh câu hỏi theo ma trận'}
          </button>
        </div>
      )}

      {mode === 'manual' && (
        <div>
          <div className="pool-toolbar">
            <input
              className="field-input"
              placeholder="Tìm câu hỏi..."
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
            <select className="field-select" value={difficultyFilter} onChange={(event) => setDifficultyFilter(event.target.value)}>
              <option value="">Tất cả độ khó</option>
              {DIFFICULTIES.map((difficulty) => (
                <option key={difficulty.value} value={difficulty.value}>{difficulty.label}</option>
              ))}
            </select>
          </div>
          {loadingApproved ? (
            <p className="empty-note">Đang tải câu hỏi đã duyệt...</p>
          ) : (
            <div className="question-pick-list">
              {visiblePoolItems.map((q) => (
                <label className="question-pick-item" key={q.id}>
                  <input type="checkbox" checked={selectedIds.includes(q.id)} onChange={() => toggleSelect(q.id)} disabled={readOnly} />
                  <span>
                    <b>{questionTypeLabel((q.classification?.assessment_type || '').toLowerCase())}</b> — {q.content}
                  </span>
                </label>
              ))}
              {visiblePoolItems.length === 0 && <p className="empty-note">Không có câu hỏi đã duyệt phù hợp.</p>}
            </div>
          )}
          <div className="pool-pagination">
            <span>{poolTotal} câu phù hợp · Trang {poolPage}/{poolPages}</span>
            <div>
              <button type="button" className="btn btn--outline" disabled={poolPage <= 1 || loadingApproved} onClick={() => setPoolPage((page) => Math.max(1, page - 1))}>
                Trước
              </button>
              <button type="button" className="btn btn--outline" disabled={poolPage >= poolPages || loadingApproved} onClick={() => setPoolPage((page) => Math.min(poolPages, page + 1))}>
                Sau
              </button>
            </div>
          </div>
          <div className="step-actions">
            <button type="button" className="btn btn--primary" onClick={handleAddManual} disabled={busy || readOnly || selectedIds.length === 0}>
              Thêm {selectedIds.length > 0 ? `(${selectedIds.length})` : ''} vào đề thi
            </button>
          </div>
        </div>
      )}

      <h4 className="pool-title">Câu hỏi trong đề ({exam.questions.length}/{exam.question_count})</h4>
      <div className="question-pool-list">
        {exam.questions.map((ref, index) => (
          <div className="question-pool-item" key={ref.question_id}>
            <span>Câu {index + 1}. {ref.content_snapshot?.content}</span>
            <button type="button" className="icon-btn icon-btn--danger" onClick={() => handleRemove(ref.question_id)} disabled={readOnly}>×</button>
          </div>
        ))}
        {exam.questions.length === 0 && <p className="empty-note">Chưa có câu hỏi nào trong đề.</p>}
      </div>
    </div>
  );
}

function VariantsStep({ exam, onNotify }) {
  const [variants, setVariants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [examCode, setExamCode] = useState('');
  const [shuffle, setShuffle] = useState(true);
  const [busy, setBusy] = useState(false);
  const [deleteCandidate, setDeleteCandidate] = useState(null);
  const finalized = examStatus(exam) === 'FINALIZED';

  const load = async () => {
    setLoading(true);
    try {
      const result = await listVariants(exam.id);
      setVariants(result || []);
    } catch (err) {
      onNotify(`Không thể tải mã đề: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exam.id]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!finalized || !examCode.trim()) return;
    setBusy(true);
    try {
      await createVariant(exam.id, examCode.trim(), shuffle);
      setExamCode('');
      await load();
      onNotify('Đã tạo mã đề.', 'success');
    } catch (err) {
      onNotify(`Không thể tạo mã đề: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!deleteCandidate) return undefined;
    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !busy) setDeleteCandidate(null);
    };
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [busy, deleteCandidate]);

  const confirmDelete = async () => {
    if (!deleteCandidate) return;
    setBusy(true);
    try {
      await deleteVariant(exam.id, deleteCandidate.id);
      await load();
      setDeleteCandidate(null);
      onNotify('Đã xóa mã đề.', 'success');
    } catch (err) {
      onNotify(`Không thể xóa mã đề: ${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h3 className="step-title">Quản lý mã đề (tối đa 4 mã đề / kỳ thi)</h3>
      {!finalized && (
        <p className="locked-note">Cần chốt đề trước khi tạo mã đề để khóa snapshot câu hỏi.</p>
      )}
      {loading ? (
        <p className="empty-note">Đang tải...</p>
      ) : (
        <div className="variant-list">
          {variants.map((variant) => (
            <div className="variant-item" key={variant.id}>
              <span>Mã đề <b>{variant.exam_code}</b> — {variant.questions.length} câu</span>
              <button
                type="button"
                className="icon-btn icon-btn--danger"
                onClick={() => setDeleteCandidate(variant)}
                disabled={busy}
                aria-label={`Xóa mã đề ${variant.exam_code}`}
              >
                ×
              </button>
            </div>
          ))}
          {variants.length === 0 && <p className="empty-note">Chưa có mã đề nào.</p>}
        </div>
      )}
      {variants.length < 4 ? (
        <form className="variant-form" onSubmit={handleCreate}>
          <input className="field-input" placeholder="Mã đề (VD: 132)" value={examCode} onChange={(e) => setExamCode(e.target.value)} disabled={!finalized} />
          <label className="variant-shuffle-check">
            <input type="checkbox" checked={shuffle} onChange={(e) => setShuffle(e.target.checked)} disabled={!finalized} />
            Xáo trộn thứ tự câu hỏi/đáp án
          </label>
          <button type="submit" className="btn btn--primary" disabled={busy || !finalized}>Tạo mã đề</button>
        </form>
      ) : (
        <p className="matrix-warning">Đã đạt tối đa 4 mã đề cho kỳ thi này.</p>
      )}

      {deleteCandidate && (
        <div
          className="exam-dialog-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !busy) setDeleteCandidate(null);
          }}
        >
          <section className="exam-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-variant-dialog-title">
            <span className="exam-dialog__eyebrow">Mã đề {deleteCandidate.exam_code}</span>
            <h2 id="delete-variant-dialog-title">Xóa mã đề?</h2>
            <p>Bản xuất của mã đề này sẽ không còn dùng được.</p>
            <div className="exam-dialog__actions">
              <button type="button" className="btn btn--outline" onClick={() => setDeleteCandidate(null)} disabled={busy}>
                Hủy
              </button>
              <button type="button" className="btn btn--danger" onClick={confirmDelete} disabled={busy}>
                {busy ? 'Đang xóa...' : 'Xóa mã đề'}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function PreviewStep({ exam, onNotify }) {
  const [variants, setVariants] = useState([]);
  const [variantId, setVariantId] = useState('');
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listVariants(exam.id).then((result) => {
      setVariants(result || []);
      if (result?.length) setVariantId(result[0].id);
    }).catch(() => {});
  }, [exam.id]);

  useEffect(() => {
    if (!variantId) return;
    setLoading(true);
    getVariantPreview(exam.id, variantId)
      .then(setPreview)
      .catch((err) => onNotify(`Không thể xem trước: ${err.message}`))
      .finally(() => setLoading(false));
  }, [exam.id, onNotify, variantId]);

  return (
    <div>
      <h3 className="step-title">Xem trước đề thi</h3>
      <div className="field-group">
        <label className="field-label">Chọn mã đề</label>
        <select className="field-select" value={variantId} onChange={(e) => setVariantId(e.target.value)}>
          {variants.map((v) => <option key={v.id} value={v.id}>{v.exam_code}</option>)}
        </select>
      </div>
      {loading && <p className="empty-note">Đang tải...</p>}
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
    </div>
  );
}

function ExportStep({ exam, onNotify }) {
  const [variants, setVariants] = useState([]);
  const [busy, setBusy] = useState('');

  useEffect(() => {
    listVariants(exam.id).then((result) => setVariants(result || [])).catch(() => {});
  }, [exam.id]);

  const handleExport = async (variantId, type, format) => {
    const key = `${variantId}-${type}-${format}`;
    setBusy(key);
    try {
      if (format === 'docx') {
        await downloadVariantDocx(exam.id, variantId, type);
      } else {
        await downloadVariantPdf(exam.id, variantId, type);
      }
    } catch (err) {
      onNotify(`Không thể xuất ${format.toUpperCase()}: ${err.message}`);
    } finally {
      setBusy('');
    }
  };

  return (
    <div>
      <h3 className="step-title">Xuất đề thi</h3>
      {variants.length === 0 && <p className="empty-note">Chưa có mã đề nào, hãy tạo mã đề ở bước trước.</p>}
      <div className="export-list">
        {variants.map((variant) => (
          <div className="export-item" key={variant.id}>
            <span>Mã đề <b>{variant.exam_code}</b></span>
            <div className="export-actions">
              {EXPORT_VARIANT_TYPES.map((exportType) => (
                <div className="export-action-group" key={exportType.value}>
                  <span>{exportType.label}</span>
                  <div>
                    {EXPORT_FORMATS.map((format) => {
                      const key = `${variant.id}-${exportType.value}-${format.value}`;
                      return (
                        <button
                          type="button"
                          className="btn btn--outline"
                          disabled={busy === key || variant.questions.length === 0}
                          onClick={() => handleExport(variant.id, exportType.value, format.value)}
                          key={format.value}
                        >
                          {busy === key ? 'Đang xuất' : format.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ExamBuilderPage;
