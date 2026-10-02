import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faClone, faTrashCan } from '@fortawesome/free-solid-svg-icons';
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
};

function statusKey(status) {
  return String(status || 'DRAFT').toUpperCase();
}

function statusClass(status) {
  return statusKey(status).toLowerCase();
}

function ExamListPage() {
  const navigate = useNavigate();
  const [exams, setExams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [subjects, setSubjects] = useState([]);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [createError, setCreateError] = useState('');
  const [deletingId, setDeletingId] = useState(null);
  const [duplicatingId, setDuplicatingId] = useState(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const [name, setName] = useState('');
  const [examTitle, setExamTitle] = useState('');
  const [subjectId, setSubjectId] = useState('');
  const [questionCount, setQuestionCount] = useState(25);

  const fetchExams = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await listExams({ page, pageSize: 20 });
      setExams(result.items || []);
      setTotal(result.total || 0);
      const lastPage = Math.max(1, Math.ceil((result.total || 0) / 20));
      if (page > lastPage) setPage(lastPage);
    } catch (err) {
      setError(err.message || 'Không tải được danh sách đề thi');
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchExams();
  }, [fetchExams]);

  useEffect(() => {
    listSubjects().then(setSubjects).catch(() => {});
  }, []);

  const openCreate = () => {
    setCreateError('');
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
    setCreateError('');
    if (!name.trim() || !examTitle.trim() || !subjectId) {
      setCreateError('Vui lòng nhập đầy đủ tên đề thi, tên kỳ thi và môn học.');
      return;
    }
    const questionCountNumber = Number(questionCount);
    if (!Number.isInteger(questionCountNumber) || questionCountNumber < 1 || questionCountNumber > 200) {
      setCreateError('Số lượng câu hỏi phải là số nguyên từ 1 đến 200.');
      return;
    }
    setSaving(true);
    try {
      const exam = await createExam({
        name: name.trim(),
        exam_title: examTitle.trim(),
        subject_id: subjectId,
        question_count: questionCountNumber,
        header: {},
      });
      setCreating(false);
      navigate(`/lam-de-thi/${exam.id}`);
    } catch (err) {
      setCreateError('Tạo đề thi thất bại: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (exam) => {
    const variantCount = exam.variant_count || 0;
    const message = variantCount
      ? `Xoá đề thi "${exam.name}" và ${variantCount} mã đề đi kèm? Hành động này không thể hoàn tác.`
      : `Xoá đề thi "${exam.name}"? Hành động này không thể hoàn tác.`;
    if (!window.confirm(message)) return;
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
            <p className="page-hero-desc">
              Tạo đề thi trắc nghiệm hoàn chỉnh từ ngân hàng câu hỏi đã được duyệt, cấu hình ma trận đề
              và xuất PDF/DOCX theo chuẩn đề thi giấy.
            </p>
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
                      {STATUS_LABEL[statusKey(exam.status)] || exam.status}
                    </span>
                  </div>
                  <p className="exam-card-meta">{exam.exam_title}</p>
                  <div className="exam-card-stats">
                    <span>{exam.question_selected_count ?? exam.questions?.length ?? 0}/{exam.question_count} câu hỏi</span>
                    <span>{exam.variant_count ?? 0}/4 mã đề</span>
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
	                      <FontAwesomeIcon icon={faClone} />
	                    </button>
	                    <button
	                      type="button"
	                      className="icon-btn icon-btn--danger"
                      title="Xoá đề thi"
                      disabled={deletingId === exam.id}
                      onClick={() => handleDelete(exam)}
                    >
                      <FontAwesomeIcon icon={faTrashCan} />
                    </button>
                  </div>
                </div>
              ))}
              {exams.length === 0 && (
                <p className="empty-note">Chưa có đề thi nào. Bấm "Tạo đề thi mới" để bắt đầu.</p>
              )}
            </div>
          )}
          {total > 20 && (
            <div className="section-actions">
              <button type="button" className="btn btn--outline" disabled={loading || page <= 1} onClick={() => setPage((current) => current - 1)}>← Trước</button>
              <span>Trang {page}/{Math.max(1, Math.ceil(total / 20))} · {total} đề thi</span>
              <button type="button" className="btn btn--outline" disabled={loading || page >= Math.ceil(total / 20)} onClick={() => setPage((current) => current + 1)}>Sau →</button>
            </div>
          )}
        </div>
      </section>

      {creating && (
        <div className="modal-overlay" onClick={closeCreate}>
          <form className="modal-card" role="dialog" aria-modal="true" aria-label="Tạo đề thi mới" onClick={(e) => e.stopPropagation()} onSubmit={handleCreate}>
            <h3 className="profile-card-title">Tạo đề thi mới</h3>

            <div className="field-group">
              <label className="field-label" htmlFor="exam-create-name">Tên đề thi</label>
              <input id="exam-create-name" className="field-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Đề thi cuối kỳ - Cấu trúc dữ liệu" />
            </div>

            <div className="field-group">
              <label className="field-label" htmlFor="exam-create-title">Tên kỳ thi</label>
              <input id="exam-create-title" className="field-input" value={examTitle} onChange={(e) => setExamTitle(e.target.value)} placeholder="Thi cuối học kỳ I 2025-2026" />
            </div>

            <div className="field-group">
              <label className="field-label" htmlFor="exam-create-subject">Môn học/học phần</label>
              <select id="exam-create-subject" className="field-select" value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
                <option value="">Chọn môn học</option>
                {subjects.map((subject) => (
                  <option key={refId(subject)} value={refId(subject)}>
                    {subject.subject_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="field-group">
              <label className="field-label" htmlFor="exam-create-count">Số lượng câu hỏi</label>
              <input
                id="exam-create-count"
                type="number"
                min={1}
                max={200}
                className="field-input"
                value={questionCount}
                onChange={(e) => setQuestionCount(e.target.value)}
              />
            </div>

            {createError && <p className="exam-error" role="alert">{createError}</p>}
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
