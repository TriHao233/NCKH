import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createExam, deleteExam, duplicateExam, listExams } from '../api/exams';
import { listSubjects } from '../api/catalog';
import '../css/ExamListPage.css';

function refId(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  return value.id || value._id || '';
}

const STATUS_LABEL = {
  DRAFT: 'Nháp',
  READY: 'Sẵn sàng',
  FINALIZED: 'Đã chốt',
  ARCHIVED: 'Lưu trữ',
  draft: 'Nháp',
  ready: 'Sẵn sàng',
  finalized: 'Hoàn tất',
  archived: 'Lưu trữ',
};

function statusClass(status) {
  return String(status || 'DRAFT').toLowerCase();
}

function ExamListPage() {
  const navigate = useNavigate();
  const [exams, setExams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [subjects, setSubjects] = useState([]);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [duplicatingId, setDuplicatingId] = useState(null);

  const [name, setName] = useState('');
  const [examTitle, setExamTitle] = useState('');
  const [subjectId, setSubjectId] = useState('');
  const [questionCount, setQuestionCount] = useState(25);

  const fetchExams = async () => {
    setLoading(true);
    setError('');
    try {
      const result = await listExams({ page: 1, pageSize: 100 });
      setExams(result.items || []);
    } catch (err) {
      setError(err.message || 'Không tải được danh sách đề thi');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchExams();
    listSubjects().then(setSubjects).catch(() => {});
  }, []);

  const openCreate = () => {
    setName('');
    setExamTitle('');
    setSubjectId('');
    setQuestionCount(25);
    setCreating(true);
  };

  const closeCreate = () => {
    if (saving) return;
    setCreating(false);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim() || !examTitle.trim() || !subjectId) {
      alert('Vui lòng nhập đầy đủ tên đề thi, tên kỳ thi và môn học.');
      return;
    }
    setSaving(true);
    try {
      const exam = await createExam({
        name: name.trim(),
        exam_title: examTitle.trim(),
        subject_id: subjectId,
        question_count: Number(questionCount),
        header: {},
      });
      setCreating(false);
      navigate(`/lam-de-thi/${exam.id}`);
    } catch (err) {
      alert('Tạo đề thi thất bại: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (exam) => {
    if (!window.confirm(`Xoá đề thi "${exam.name}"?`)) return;
    setDeletingId(exam.id);
    try {
      await deleteExam(exam.id);
      await fetchExams();
    } catch (err) {
      alert('Xoá đề thi thất bại: ' + err.message);
    } finally {
      setDeletingId(null);
    }
  };

  const handleDuplicate = async (exam) => {
    setDuplicatingId(exam.id);
    try {
      const duplicate = await duplicateExam(exam.id);
      navigate(`/lam-de-thi/${duplicate.id}`);
    } catch (err) {
      alert('Nhân bản đề thi thất bại: ' + err.message);
    } finally {
      setDuplicatingId(null);
    }
  };

  return (
    <main className="exam-list-page">
      <section className="page-hero">
        <div className="container exam-hero-row">
          <div>
            <div className="page-hero-badge">Làm đề thi</div>
            <h1 className="page-hero-title">Danh sách đề thi</h1>
            <p className="page-hero-desc">Tạo, cấu hình và xuất đề thi.</p>
          </div>
          <button type="button" className="btn btn--primary" onClick={openCreate}>
            + Tạo đề thi mới
          </button>
        </div>
      </section>

      <section className="exam-list-body">
        <div className="container">
          {error && <p className="exam-error">{error}</p>}
          {loading ? (
            <p className="empty-note">Đang tải danh sách đề thi...</p>
          ) : (
            <div className="exam-grid">
              {exams.map((exam) => (
                <div className="card exam-card" key={exam.id}>
                  <div className="exam-card-header">
                    <h3>{exam.name}</h3>
                    <span className={`status-badge status--${statusClass(exam.status)}`}>
                      {STATUS_LABEL[exam.status] || exam.status}
                    </span>
                  </div>
                  <p className="exam-card-meta">{exam.exam_title}</p>
                  <div className="exam-card-stats">
                    <span>{exam.questions.length}/{exam.question_count} câu hỏi</span>
                    <span>{exam.variant_count}/4 mã đề</span>
                  </div>
                  <div className="exam-card-actions">
	                    <button type="button" className="btn btn--outline" onClick={() => navigate(`/lam-de-thi/${exam.id}`)}>
	                      Mở đề thi
	                    </button>
	                    <button
	                      type="button"
	                      className="icon-btn"
	                      title="Nhân bản"
	                      disabled={duplicatingId === exam.id}
	                      onClick={() => handleDuplicate(exam)}
	                    >
	                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></svg>
	                    </button>
	                    <button
	                      type="button"
	                      className="icon-btn icon-btn--danger"
                      title="Xoá"
                      disabled={deletingId === exam.id}
                      onClick={() => handleDelete(exam)}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6" /></svg>
                    </button>
                  </div>
                </div>
              ))}
              {exams.length === 0 && (
                <p className="empty-note">Chưa có đề thi. Tạo đề mới để bắt đầu.</p>
              )}
            </div>
          )}
        </div>
      </section>

      {creating && (
        <div className="modal-overlay" onClick={closeCreate}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={handleCreate}>
            <h3 className="profile-card-title">Tạo đề thi mới</h3>

            <div className="field-group">
              <label className="field-label">Tên đề thi</label>
              <input className="field-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Đề thi cuối kỳ - Cấu trúc dữ liệu" />
            </div>

            <div className="field-group">
              <label className="field-label">Tên kỳ thi</label>
              <input className="field-input" value={examTitle} onChange={(e) => setExamTitle(e.target.value)} placeholder="Thi cuối học kỳ I 2025-2026" />
            </div>

            <div className="field-group">
              <label className="field-label">Môn học/học phần</label>
              <select className="field-select" value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
                <option value="">Chọn môn học</option>
                {subjects.map((subject) => (
                  <option key={refId(subject)} value={refId(subject)}>
                    {subject.subject_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="field-group">
              <label className="field-label">Số lượng câu hỏi</label>
              <input
                type="number"
                min={1}
                max={200}
                className="field-input"
                value={questionCount}
                onChange={(e) => setQuestionCount(e.target.value)}
              />
            </div>

            <div className="modal-actions">
              <button type="button" className="btn btn--outline" onClick={closeCreate} disabled={saving}>Huỷ</button>
              <button type="submit" className="btn btn--primary" disabled={saving}>
                {saving ? 'Đang tạo...' : 'Tạo đề thi'}
              </button>
            </div>
          </form>
        </div>
      )}
    </main>
  );
}

export default ExamListPage;
