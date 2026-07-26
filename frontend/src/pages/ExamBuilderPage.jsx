import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  addQuestionsManual,
  autoGenerateQuestions,
  createVariant,
  deleteVariant,
  downloadVariantPdf,
  getExam,
  getMatrixAvailability,
  getVariantPreview,
  listVariants,
  removeQuestion,
  saveMatrix,
  updateExam,
} from '../api/exams';
import { listQuestions } from '../api/questions';
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

const STEPS = [
  { id: 'info', label: '1. Thông tin đề thi' },
  { id: 'header', label: '2. Đầu trang' },
  { id: 'matrix', label: '3. Ma trận đề' },
  { id: 'questions', label: '4. Chọn câu hỏi' },
  { id: 'variants', label: '5. Mã đề' },
  { id: 'preview', label: '6. Xem trước' },
  { id: 'export', label: '7. Xuất PDF' },
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
            {step === 'info' && <InfoStep exam={exam} onSaved={setExam} />}
            {step === 'header' && <HeaderStep exam={exam} onSaved={setExam} />}
            {step === 'matrix' && <MatrixStep exam={exam} chapters={chapters} onSaved={setExam} />}
            {step === 'questions' && <QuestionsStep exam={exam} onSaved={setExam} />}
            {step === 'variants' && <VariantsStep exam={exam} />}
            {step === 'preview' && <PreviewStep exam={exam} />}
            {step === 'export' && <ExportStep exam={exam} />}
          </div>
        </div>
      </section>
    </main>
  );
}

function InfoStep({ exam, onSaved }) {
  const [name, setName] = useState(exam.name);
  const [examTitle, setExamTitle] = useState(exam.exam_title);
  const [questionCount, setQuestionCount] = useState(exam.question_count);
  const [saving, setSaving] = useState(false);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await updateExam(exam.id, {
        name: name.trim(),
        exam_title: examTitle.trim(),
        question_count: Number(questionCount),
      });
      onSaved(updated);
    } catch (err) {
      alert('Lưu thất bại: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSave}>
      <h3 className="step-title">Thông tin đề thi</h3>
      <div className="field-group">
        <label className="field-label">Tên đề thi</label>
        <input className="field-input" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="field-group">
        <label className="field-label">Tên kỳ thi</label>
        <input className="field-input" value={examTitle} onChange={(e) => setExamTitle(e.target.value)} />
      </div>
      <div className="field-group">
        <label className="field-label">Số lượng câu hỏi</label>
        <input type="number" min={1} max={200} className="field-input" value={questionCount} onChange={(e) => setQuestionCount(e.target.value)} />
      </div>
      <button type="submit" className="btn btn--primary" disabled={saving}>{saving ? 'Đang lưu...' : 'Lưu'}</button>
    </form>
  );
}

function HeaderStep({ exam, onSaved }) {
  const [header, setHeader] = useState({ ...exam.header });
  const [saving, setSaving] = useState(false);

  const setField = (key, value) => setHeader((h) => ({ ...h, [key]: value }));

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await updateExam(exam.id, { header });
      onSaved(updated);
    } catch (err) {
      alert('Lưu thất bại: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSave}>
      <h3 className="step-title">Cấu hình đầu trang đề thi</h3>
      <div className="field-group">
        <label className="field-label">Tên Trường/Đại học</label>
        <input className="field-input" value={header.school_name || ''} onChange={(e) => setField('school_name', e.target.value)} />
      </div>
      <div className="field-group">
        <label className="field-label">Tên Khoa/Bộ môn</label>
        <input className="field-input" value={header.faculty_name || ''} onChange={(e) => setField('faculty_name', e.target.value)} />
      </div>
      <div className="field-group">
        <label className="field-label">Tên kỳ thi (hiển thị trên đầu trang)</label>
        <input className="field-input" value={header.exam_name || ''} onChange={(e) => setField('exam_name', e.target.value)} />
      </div>
      <div className="field-group">
        <label className="field-label">Tên môn học/học phần</label>
        <input className="field-input" value={header.subject_name || ''} onChange={(e) => setField('subject_name', e.target.value)} />
      </div>
      <div className="field-group">
        <label className="field-label">Thời gian làm bài (phút)</label>
        <input type="number" min={1} className="field-input" value={header.duration_minutes || 60} onChange={(e) => setField('duration_minutes', Number(e.target.value))} />
      </div>
      <div className="field-group">
        <label className="field-label">Lớp (tuỳ chọn)</label>
        <input className="field-input" value={header.class_name || ''} onChange={(e) => setField('class_name', e.target.value)} />
      </div>
      <div className="field-group">
        <label className="field-label">Phòng thi (tuỳ chọn)</label>
        <input className="field-input" value={header.room || ''} onChange={(e) => setField('room', e.target.value)} />
      </div>
      <div className="field-group">
        <label className="field-label">Ngày thi (tuỳ chọn)</label>
        <input className="field-input" value={header.exam_date || ''} onChange={(e) => setField('exam_date', e.target.value)} placeholder="dd/mm/yyyy" />
      </div>
      <button type="submit" className="btn btn--primary" disabled={saving}>{saving ? 'Đang lưu...' : 'Lưu đầu trang'}</button>
    </form>
  );
}

function MatrixStep({ exam, chapters, onSaved }) {
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
    } catch (err) {
      alert('Lưu ma trận thất bại: ' + err.message);
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
      alert('Kiểm tra thất bại: ' + err.message);
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
                <select className="field-select" value={cell.chapter_id || ''} onChange={(e) => updateCell(index, { chapter_id: e.target.value })}>
                  <option value="">Tất cả chương</option>
                  {chapters.map((chapter) => (
                    <option key={chapter._id || chapter.id} value={chapter._id || chapter.id}>
                      {chapter.chapter_name}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <select className="field-select" value={cell.cognitive_level} onChange={(e) => updateCell(index, { cognitive_level: e.target.value })}>
                  {COGNITIVE_LEVELS.map((lvl) => <option key={lvl.value} value={lvl.value}>{lvl.label}</option>)}
                </select>
              </td>
              <td>
                <select className="field-select" value={cell.difficulty} onChange={(e) => updateCell(index, { difficulty: e.target.value })}>
                  {DIFFICULTIES.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </select>
              </td>
              <td>
                <input type="number" min={1} className="field-input matrix-count" value={cell.count} onChange={(e) => updateCell(index, { count: e.target.value })} />
              </td>
              <td>
                <button type="button" className="icon-btn icon-btn--danger" onClick={() => removeRow(index)}>×</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="step-actions">
        <button type="button" className="btn btn--outline" onClick={addRow}>+ Thêm nhóm</button>
        <button type="button" className="btn btn--outline" onClick={handleCheck} disabled={checking}>
          {checking ? 'Đang kiểm tra...' : 'Kiểm tra đủ câu hỏi'}
        </button>
        <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
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

function QuestionsStep({ exam, onSaved }) {
  const [mode, setMode] = useState('auto');
  const [busy, setBusy] = useState(false);
  const [approved, setApproved] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [loadingApproved, setLoadingApproved] = useState(false);

  const poolIds = new Set((exam.questions || []).map((q) => q.question_id));

  const loadApproved = async () => {
    setLoadingApproved(true);
    try {
      const result = await listQuestions({
        page: 1,
        pageSize: 200,
        reviewStatus: 'APPROVED',
      });
      setApproved((result.items || []).filter((q) => refIdOf(q.classification?.subject?.id) === exam.subject_id || !q.classification?.subject?.id));
    } catch (err) {
      alert('Tải câu hỏi thất bại: ' + err.message);
    } finally {
      setLoadingApproved(false);
    }
  };

  function refIdOf(value) {
    if (!value) return '';
    if (typeof value === 'string') return value;
    return value.id || value._id || '';
  }

  useEffect(() => {
    if (mode === 'manual') loadApproved();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  const handleAutoGenerate = async () => {
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
    if (selectedIds.length === 0) return;
    setBusy(true);
    try {
      const updated = await addQuestionsManual(exam.id, selectedIds);
      onSaved(updated);
      setSelectedIds([]);
    } catch (err) {
      alert('Thêm câu hỏi thất bại: ' + err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (questionId) => {
    setBusy(true);
    try {
      const updated = await removeQuestion(exam.id, questionId);
      onSaved(updated);
    } catch (err) {
      alert('Xoá câu hỏi thất bại: ' + err.message);
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
          <button type="button" className="btn btn--primary" onClick={handleAutoGenerate} disabled={busy}>
            {busy ? 'Đang sinh đề...' : 'Tự sinh câu hỏi theo ma trận'}
          </button>
        </div>
      )}

      {mode === 'manual' && (
        <div>
          {loadingApproved ? (
            <p className="empty-note">Đang tải câu hỏi đã duyệt...</p>
          ) : (
            <div className="question-pick-list">
              {approved.filter((q) => !poolIds.has(q.id)).map((q) => (
                <label className="question-pick-item" key={q.id}>
                  <input type="checkbox" checked={selectedIds.includes(q.id)} onChange={() => toggleSelect(q.id)} />
                  <span>
                    <b>{questionTypeLabel((q.classification?.assessment_type || '').toLowerCase())}</b> — {q.content}
                  </span>
                </label>
              ))}
              {approved.length === 0 && <p className="empty-note">Không có câu hỏi đã duyệt phù hợp.</p>}
            </div>
          )}
          <div className="step-actions">
            <button type="button" className="btn btn--primary" onClick={handleAddManual} disabled={busy || selectedIds.length === 0}>
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
            <button type="button" className="icon-btn icon-btn--danger" onClick={() => handleRemove(ref.question_id)}>×</button>
          </div>
        ))}
        {exam.questions.length === 0 && <p className="empty-note">Chưa có câu hỏi nào trong đề.</p>}
      </div>
    </div>
  );
}

function VariantsStep({ exam }) {
  const [variants, setVariants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [examCode, setExamCode] = useState('');
  const [shuffle, setShuffle] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const result = await listVariants(exam.id);
      setVariants(result || []);
    } catch (err) {
      alert('Tải mã đề thất bại: ' + err.message);
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
    if (!examCode.trim()) return;
    setBusy(true);
    try {
      await createVariant(exam.id, examCode.trim(), shuffle);
      setExamCode('');
      await load();
    } catch (err) {
      alert('Tạo mã đề thất bại: ' + err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (variantId) => {
    if (!window.confirm('Xoá mã đề này?')) return;
    setBusy(true);
    try {
      await deleteVariant(exam.id, variantId);
      await load();
    } catch (err) {
      alert('Xoá mã đề thất bại: ' + err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h3 className="step-title">Quản lý mã đề (tối đa 4 mã đề / kỳ thi)</h3>
      {loading ? (
        <p className="empty-note">Đang tải...</p>
      ) : (
        <div className="variant-list">
          {variants.map((variant) => (
            <div className="variant-item" key={variant.id}>
              <span>Mã đề <b>{variant.exam_code}</b> — {variant.questions.length} câu</span>
              <button type="button" className="icon-btn icon-btn--danger" onClick={() => handleDelete(variant.id)} disabled={busy}>×</button>
            </div>
          ))}
          {variants.length === 0 && <p className="empty-note">Chưa có mã đề nào.</p>}
        </div>
      )}
      {variants.length < 4 ? (
        <form className="variant-form" onSubmit={handleCreate}>
          <input className="field-input" placeholder="Mã đề (VD: 132)" value={examCode} onChange={(e) => setExamCode(e.target.value)} />
          <label className="variant-shuffle-check">
            <input type="checkbox" checked={shuffle} onChange={(e) => setShuffle(e.target.checked)} />
            Xáo trộn thứ tự câu hỏi/đáp án
          </label>
          <button type="submit" className="btn btn--primary" disabled={busy}>Tạo mã đề</button>
        </form>
      ) : (
        <p className="matrix-warning">Đã đạt tối đa 4 mã đề cho kỳ thi này.</p>
      )}
    </div>
  );
}

function PreviewStep({ exam }) {
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
      .catch((err) => alert('Xem trước thất bại: ' + err.message))
      .finally(() => setLoading(false));
  }, [exam.id, variantId]);

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

function ExportStep({ exam }) {
  const [variants, setVariants] = useState([]);
  const [busy, setBusy] = useState('');

  useEffect(() => {
    listVariants(exam.id).then((result) => setVariants(result || [])).catch(() => {});
  }, [exam.id]);

  const handleExport = async (variantId, type) => {
    const key = `${variantId}-${type}`;
    setBusy(key);
    try {
      await downloadVariantPdf(exam.id, variantId, type);
    } catch (err) {
      alert('Xuất PDF thất bại: ' + err.message);
    } finally {
      setBusy('');
    }
  };

  return (
    <div>
      <h3 className="step-title">Xuất PDF</h3>
      {variants.length === 0 && <p className="empty-note">Chưa có mã đề nào, hãy tạo mã đề ở bước trước.</p>}
      <div className="export-list">
        {variants.map((variant) => (
          <div className="export-item" key={variant.id}>
            <span>Mã đề <b>{variant.exam_code}</b></span>
            <div className="export-actions">
              <button type="button" className="btn btn--outline" disabled={busy === `${variant.id}-de` || variant.questions.length === 0} onClick={() => handleExport(variant.id, 'de')}>
                Đề thi
              </button>
              <button type="button" className="btn btn--outline" disabled={busy === `${variant.id}-dapan` || variant.questions.length === 0} onClick={() => handleExport(variant.id, 'dapan')}>
                Đáp án
              </button>
              <button type="button" className="btn btn--outline" disabled={busy === `${variant.id}-de_dapan` || variant.questions.length === 0} onClick={() => handleExport(variant.id, 'de_dapan')}>
                Đề + Đáp án
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ExamBuilderPage;
