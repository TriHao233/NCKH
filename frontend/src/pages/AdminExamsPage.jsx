import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faClone, faPlus, faRotateRight, faTrashCan } from '@fortawesome/free-solid-svg-icons';
import { listSubjects } from '../api/catalog';
import { createExam, deleteExam, duplicateExam, listExams } from '../api/exams';
import { listUsers } from '../api/users';
import '../css/AdminJobsPage.css';
import '../css/AdminQuestionBankPage.css';

const STATUS = {
  DRAFT: { label: 'Nháp', tone: 'muted' },
  READY: { label: 'Sẵn sàng', tone: 'active' },
  FINALIZED: { label: 'Đã chốt', tone: 'success' },
  ARCHIVED: { label: 'Lưu trữ', tone: 'warning' },
};
const STATUS_ORDER = ['DRAFT', 'READY', 'FINALIZED'];
const EMPTY_FORM = { name: '', examTitle: '', subjectId: '', questionCount: 25 };

function refId(value) {
  if (!value) return '';
  return typeof value === 'string' ? value : value.id || value._id || '';
}

function statusKey(exam) {
  return String(exam.status || 'DRAFT').toUpperCase();
}

function formatDateTime(value) {
  if (!value) return '--';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '--' : date.toLocaleString('vi-VN');
}

// Hai danh sách này nhỏ nên tải hết một lần để lọc và tra tên ngay trên trình duyệt.
async function fetchAllPages(fetchPage) {
  const first = await fetchPage(1);
  const items = [...(first.items || [])];
  for (let page = 2; items.length < (first.total || 0); page += 1) {
    const next = await fetchPage(page);
    if (!next.items?.length) break;
    items.push(...next.items);
  }
  return items;
}

function AdminExamsPage() {
  const navigate = useNavigate();
  const [exams, setExams] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState(null);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [ownerId, setOwnerId] = useState('');
  const [subjectId, setSubjectId] = useState('');
  const [busyId, setBusyId] = useState('');
  const [form, setForm] = useState(null);
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  const userById = useMemo(() => new Map(users.map((user) => [user.id, user])), [users]);
  const subjectById = useMemo(() => new Map(subjects.map((subject) => [refId(subject), subject])), [subjects]);

  const fetchExams = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setExams(await fetchAllPages((page) => listExams({ page, pageSize: 100 })));
    } catch (err) {
      setError(err.message || 'Không tải được danh sách đề thi');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchExams();
    listSubjects().then(setSubjects).catch(() => setSubjects([]));
    fetchAllPages((page) => listUsers({ page, pageSize: 100 })).then(setUsers).catch(() => setUsers([]));
  }, [fetchExams]);

  useEffect(() => {
    if (!notice || notice.type === 'error') return undefined;
    const timer = setTimeout(() => setNotice(null), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!form) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && !saving) setForm(null);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [form, saving]);

  const ownerName = (exam) => {
    const owner = userById.get(exam.created_by_user_id);
    return owner?.display_name || owner?.email || (exam.created_by_user_id ? 'Tài khoản không còn trong hệ thống' : 'Chưa rõ');
  };
  const subjectLabel = (exam) => {
    const subject = subjectById.get(exam.subject_id);
    return subject ? subject.subject_code || subject.subject_name : 'Chưa rõ';
  };

  // Chỉ liệt kê những người thực sự có đề thi trong bộ lọc "Người soạn".
  const owners = useMemo(() => {
    const ids = [...new Set(exams.map((exam) => exam.created_by_user_id).filter(Boolean))];
    return ids
      .map((id) => ({ id, name: userById.get(id)?.display_name || userById.get(id)?.email || id }))
      .sort((left, right) => left.name.localeCompare(right.name, 'vi'));
  }, [exams, userById]);

  const counts = useMemo(() => {
    const result = { all: exams.length };
    STATUS_ORDER.forEach((key) => { result[key] = exams.filter((exam) => statusKey(exam) === key).length; });
    return result;
  }, [exams]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return exams
      .filter((exam) => !status || statusKey(exam) === status)
      .filter((exam) => !ownerId || exam.created_by_user_id === ownerId)
      .filter((exam) => !subjectId || exam.subject_id === subjectId)
      .filter((exam) => !needle || [exam.name, exam.exam_title].some((value) => String(value || '').toLowerCase().includes(needle)))
      .sort((left, right) => String(right.updated_at || '').localeCompare(String(left.updated_at || '')));
  }, [exams, search, status, ownerId, subjectId]);

  const activeFilterCount = [search.trim(), status, ownerId, subjectId].filter(Boolean).length;
  const resetFilters = () => {
    setSearch('');
    setStatus('');
    setOwnerId('');
    setSubjectId('');
  };

  const handleCreate = async (event) => {
    event.preventDefault();
    const questionCount = Number(form.questionCount);
    if (!form.name.trim() || !form.examTitle.trim() || !form.subjectId) {
      setFormError('Hãy nhập tên đề thi, tên kỳ thi và chọn học phần.');
      return;
    }
    if (!Number.isInteger(questionCount) || questionCount < 1 || questionCount > 200) {
      setFormError('Số câu hỏi phải là số nguyên từ 1 đến 200.');
      return;
    }
    setSaving(true);
    setFormError('');
    try {
      const exam = await createExam({
        name: form.name.trim(),
        exam_title: form.examTitle.trim(),
        subject_id: form.subjectId,
        question_count: questionCount,
        header: {},
      });
      navigate(`/lam-de-thi/${exam.id}`);
    } catch (err) {
      setFormError(err.message || 'Tạo đề thi thất bại');
      setSaving(false);
    }
  };

  const handleDuplicate = async (exam) => {
    setBusyId(exam.id);
    try {
      const copy = await duplicateExam(exam.id);
      setNotice({ type: 'success', text: `Đã nhân bản thành "${copy.name}". Bản sao thuộc về bạn.` });
      await fetchExams();
    } catch (err) {
      setNotice({ type: 'error', text: err.message || 'Nhân bản đề thi thất bại' });
    } finally {
      setBusyId('');
    }
  };

  const handleDelete = async (exam) => {
    if (!window.confirm(`Xóa đề thi "${exam.name}" của ${ownerName(exam)}?`)) return;
    setBusyId(exam.id);
    try {
      await deleteExam(exam.id);
      setNotice({ type: 'success', text: `Đã xóa đề thi "${exam.name}".` });
      await fetchExams();
    } catch (err) {
      setNotice({ type: 'error', text: err.message || 'Xóa đề thi thất bại' });
    } finally {
      setBusyId('');
    }
  };

  return (
    <main className="admin-jobs-page question-bank-page">
      <section className="jobs-header">
        <div>
          <span>Ngân hàng</span>
          <h1>Đề thi</h1>
          <p>Đề thi của mọi giảng viên. Mở một đề để xem hoặc sửa bằng màn soạn đề.</p>
        </div>
        <div className="jobs-header-actions">
          <button type="button" className="jobs-secondary-button" onClick={fetchExams} disabled={loading}>
            <FontAwesomeIcon icon={faRotateRight} />
            <span>{loading ? 'Đang tải' : 'Làm mới'}</span>
          </button>
          <button type="button" className="jobs-primary-button" onClick={() => { setFormError(''); setForm(EMPTY_FORM); }}>
            <FontAwesomeIcon icon={faPlus} />
            <span>Tạo đề thi</span>
          </button>
        </div>
      </section>

      <section className="jobs-summary qbank-summary qbank-summary--four" aria-label="Số đề thi theo trạng thái">
        <button type="button" className={`summary-tile ${status === '' ? 'summary-tile--active' : ''}`} onClick={() => setStatus('')}>
          <b>{counts.all}</b>
          <span>Tất cả</span>
        </button>
        {STATUS_ORDER.map((key) => (
          <button type="button" key={key} className={`summary-tile ${status === key ? 'summary-tile--active' : ''}`} onClick={() => setStatus(key)}>
            <b>{counts[key]}</b>
            <span>{STATUS[key].label}</span>
          </button>
        ))}
      </section>

      <section className="jobs-toolbar qbank-toolbar qbank-toolbar--documents" aria-label="Bộ lọc đề thi">
        <div className="toolbar-field">
          <label htmlFor="exam-search">Tìm kiếm</label>
          <input id="exam-search" type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Tên đề thi hoặc tên kỳ thi" />
        </div>
        <div className="toolbar-field">
          <label htmlFor="exam-owner">Người soạn</label>
          <select id="exam-owner" value={ownerId} onChange={(event) => setOwnerId(event.target.value)}>
            <option value="">Tất cả</option>
            {owners.map((owner) => <option key={owner.id} value={owner.id}>{owner.name}</option>)}
          </select>
        </div>
        <div className="toolbar-field">
          <label htmlFor="exam-subject">Học phần</label>
          <select id="exam-subject" value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
            <option value="">Tất cả</option>
            {subjects.map((subject) => <option key={refId(subject)} value={refId(subject)}>{subject.subject_code} — {subject.subject_name}</option>)}
          </select>
        </div>
        <div className="qbank-toolbar-actions">
          {activeFilterCount > 0 && (
            <button type="button" className="qbank-link-button" onClick={resetFilters}>Xóa {activeFilterCount} bộ lọc</button>
          )}
        </div>
      </section>

      {error && <p className="jobs-error" role="alert">{error}</p>}

      <section className="jobs-layout">
        <div className="jobs-table-panel">
          <div className="jobs-table-header">
            <div>
              <h2>Danh sách đề thi</h2>
              <span>{filtered.length} đề thi{activeFilterCount > 0 ? ' phù hợp với bộ lọc' : ''}</span>
            </div>
          </div>
          <div className="jobs-table-wrap">
            <table className="jobs-table qbank-table">
              <thead>
                <tr>
                  <th>Đề thi</th>
                  <th>Người soạn</th>
                  <th>Học phần</th>
                  <th>Trạng thái</th>
                  <th>Câu hỏi</th>
                  <th>Mã đề</th>
                  <th>Cập nhật</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((exam) => {
                  const state = STATUS[statusKey(exam)] || { label: exam.status, tone: 'muted' };
                  const owner = userById.get(exam.created_by_user_id);
                  return (
                    <tr
                      key={exam.id}
                      tabIndex={0}
                      onClick={() => navigate(`/lam-de-thi/${exam.id}`)}
                      onKeyDown={(event) => { if (event.key === 'Enter' && event.target === event.currentTarget) navigate(`/lam-de-thi/${exam.id}`); }}
                    >
                      <td className="qbank-cell-question">
                        <strong>{exam.name}</strong>
                        <small>{exam.exam_title}</small>
                      </td>
                      <td>
                        <span>{ownerName(exam)}</span>
                        {owner?.display_name && owner?.email && <small>{owner.email}</small>}
                      </td>
                      <td title={subjectById.get(exam.subject_id)?.subject_name}>{subjectLabel(exam)}</td>
                      <td><span className={`status-pill status-pill--${state.tone}`}>{state.label}</span></td>
                      <td>{exam.question_selected_count ?? exam.questions?.length ?? 0} / {exam.question_count}</td>
                      <td>{exam.variant_count ?? 0}</td>
                      <td>{formatDateTime(exam.updated_at)}</td>
                      <td>
                        <div className="row-actions">
                          <button
                            type="button"
                            title="Nhân bản"
                            aria-label={`Nhân bản ${exam.name}`}
                            disabled={busyId === exam.id}
                            onClick={(event) => { event.stopPropagation(); handleDuplicate(exam); }}
                          >
                            <FontAwesomeIcon icon={faClone} />
                          </button>
                          <button
                            type="button"
                            title="Xóa"
                            aria-label={`Xóa ${exam.name}`}
                            disabled={busyId === exam.id}
                            onClick={(event) => { event.stopPropagation(); handleDelete(exam); }}
                          >
                            <FontAwesomeIcon icon={faTrashCan} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {loading && <p className="jobs-empty">Đang tải danh sách đề thi...</p>}
            {!loading && filtered.length === 0 && (
              <p className="jobs-empty">{activeFilterCount > 0 ? 'Không có đề thi phù hợp với bộ lọc.' : 'Chưa có đề thi nào.'}</p>
            )}
          </div>
        </div>
      </section>

      {form && (
        <div className="modal-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) setForm(null); }}>
          <form className="qbank-dialog qbank-dialog--narrow" onSubmit={handleCreate} role="dialog" aria-modal="true" aria-label="Tạo đề thi">
            <div className="qbank-dialog-head">
              <h2>Tạo đề thi</h2>
              <button type="button" className="qbank-icon-button" onClick={() => setForm(null)} aria-label="Đóng">×</button>
            </div>
            <label className="qbank-field">
              <span>Tên đề thi</span>
              <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Ví dụ: Đề cuối kỳ Cấu trúc dữ liệu" />
            </label>
            <label className="qbank-field">
              <span>Tên kỳ thi</span>
              <input value={form.examTitle} onChange={(event) => setForm({ ...form, examTitle: event.target.value })} placeholder="Ví dụ: Thi cuối học kỳ I 2026-2027" />
            </label>
            <label className="qbank-field">
              <span>Học phần</span>
              <select value={form.subjectId} onChange={(event) => setForm({ ...form, subjectId: event.target.value })}>
                <option value="">Chọn học phần</option>
                {subjects.filter((subject) => subject.is_active !== false).map((subject) => (
                  <option key={refId(subject)} value={refId(subject)}>{subject.subject_code} — {subject.subject_name}</option>
                ))}
              </select>
            </label>
            <label className="qbank-field">
              <span>Số câu hỏi</span>
              <input type="number" min={1} max={200} value={form.questionCount} onChange={(event) => setForm({ ...form, questionCount: event.target.value })} />
            </label>
            <p className="qbank-muted">Sau khi tạo, bạn được đưa sang màn soạn đề để lập ma trận và chọn câu hỏi.</p>
            {formError && <p className="qbank-note qbank-note--error" role="alert">{formError}</p>}
            <div className="qbank-dialog-actions">
              <button type="button" className="jobs-secondary-button" onClick={() => setForm(null)} disabled={saving}>Hủy</button>
              <button type="submit" className="jobs-primary-button" disabled={saving}>{saving ? 'Đang tạo...' : 'Tạo đề thi'}</button>
            </div>
          </form>
        </div>
      )}

      {notice && (
        <div className={`qbank-toast qbank-toast--${notice.type}`} role={notice.type === 'error' ? 'alert' : 'status'}>
          <span>{notice.text}</span>
          <button type="button" onClick={() => setNotice(null)} aria-label="Đóng thông báo">×</button>
        </div>
      )}
    </main>
  );
}

export default AdminExamsPage;
