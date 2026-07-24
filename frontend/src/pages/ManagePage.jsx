import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { deleteQuestion, listQuestions, updateQuestion } from '../api/questions';
import { deleteDocument, listDocuments } from '../api/documents';
import { QUESTION_TYPES, questionTypeLabel } from '../constants/generationEnums';
import '../css/ManagePage.css';

const REVIEW_STATUS_LABEL = {
  PENDING: 'Chờ duyệt',
  APPROVED: 'Đã duyệt',
  NEEDS_REVISION: 'Cần sửa',
  REJECTED: 'Từ chối',
};

const REVIEW_STATUS_CLASS = {
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

function ManagePage() {
  const navigate = useNavigate();

  const [questions, setQuestions] = useState([]);
  const [questionsLoading, setQuestionsLoading] = useState(true);
  const [questionsError, setQuestionsError] = useState('');

  const [documents, setDocuments] = useState([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentsError, setDocumentsError] = useState('');

  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all-type');
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  const [editing, setEditing] = useState(null);
  const [editContent, setEditContent] = useState('');
  const [editCorrectAnswer, setEditCorrectAnswer] = useState('');
  const [editExplanation, setEditExplanation] = useState('');
  const [editChangeNote, setEditChangeNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [deletingDocId, setDeletingDocId] = useState(null);

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
    setDocumentsLoading(true);
    setDocumentsError('');
    try {
      const result = await listDocuments({ page: 1, pageSize: 20 });
      setDocuments(result.items || []);
    } catch (error) {
      setDocumentsError(error.message || 'Không tải được danh sách tài liệu');
    } finally {
      setDocumentsLoading(false);
    }
  };

  useEffect(() => {
    fetchQuestions(searchTerm);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchTerm]);

  useEffect(() => {
    fetchDocuments();
  }, []);

  const counts = useMemo(() => ({
    all: questions.length,
    APPROVED: questions.filter((q) => q.review_status === 'APPROVED').length,
    PENDING: questions.filter((q) => q.review_status === 'PENDING').length,
    NEEDS_REVISION: questions.filter((q) => q.review_status === 'NEEDS_REVISION').length,
  }), [questions]);

  const filtered = useMemo(() => {
    return questions.filter((q) => {
      if (statusFilter !== 'all' && q.review_status !== statusFilter) return false;
      if (typeFilter !== 'all-type') {
        const assessmentType = (q.classification?.assessment_type || '').toLowerCase();
        if (assessmentType !== typeFilter) return false;
      }
      return true;
    });
  }, [questions, statusFilter, typeFilter]);

  const openEdit = (item) => {
    setEditing(item);
    setEditContent(item.content || '');
    setEditCorrectAnswer(item.question_data?.correct_answer ?? '');
    setEditExplanation(item.question_data?.explanation ?? '');
    setEditChangeNote('');
  };

  const closeEdit = () => {
    if (saving) return;
    setEditing(null);
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editing) return;
    if (!editContent.trim()) {
      alert('Nội dung câu hỏi không được để trống.');
      return;
    }
    setSaving(true);
    try {
      await updateQuestion(editing.id, {
        expected_version: editing.current_version,
        content: editContent,
        question_data: {
          ...editing.question_data,
          correct_answer: editCorrectAnswer,
          explanation: editExplanation,
        },
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
            <button type="button" className="btn btn--outline" disabled>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>
              Xuất đề thi
            </button>
            <button type="button" className="btn btn--primary" disabled>
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
                          <span className="source-tag">v{item.current_version}</span>
                        </div>
                        <p>{item.content}</p>
                      </div>
                      <div className="question-side">
                        <span className={`status-badge ${REVIEW_STATUS_CLASS[item.review_status] || ''}`}>
                          {REVIEW_STATUS_LABEL[item.review_status] || item.review_status}
                        </span>
                        <div className="question-actions">
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

            <div className="card side-card">
              <h3>Trạng thái Moodle</h3>
              <p className="side-note">
                Câu hỏi đã duyệt sẽ được chuyển đổi sang định dạng chuẩn của Moodle (nội dung, đáp án, thiết lập xáo trộn)
                trước khi đồng bộ.
              </p>
              <div className="moodle-status">
                <span className="moodle-dot" />
                Plugin Moodle: sẵn sàng đồng bộ
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
              <label className="field-label">Đáp án đúng</label>
              <input
                className="field-input"
                value={editCorrectAnswer}
                onChange={(e) => setEditCorrectAnswer(e.target.value)}
              />
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
