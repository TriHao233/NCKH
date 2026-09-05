import React, { useContext, useEffect, useMemo, useState } from 'react';
import {
  addSubjectChapter,
  addSubjectLearningOutcome,
  deactivateSubject,
  listSubjects,
  saveSubject,
  updateSubject,
  updateSubjectChapter,
  updateSubjectLearningOutcome,
} from '../api/catalog';
import { permissionsForUser } from '../auth/permissions';
import { AuthContext } from '../context/AuthContext';
import '../css/SubjectManage.css';

const EMPTY_SUBJECT = { subject_code: '', subject_name: '', description: '', is_active: true };
const EMPTY_CHAPTER = { chapter_code: '', chapter_name: '', sequence_no: 1, is_active: true };
const EMPTY_CLO = { clo_code: '', description: '', target_weight: 1, is_active: true };

function refId(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  return value.id || value._id || '';
}

function usageTotal(counts) {
  if (!counts) return 0;
  return Object.values(counts).reduce((sum, value) => sum + (Number(value) || 0), 0);
}

function SubjectManage() {
  const { user } = useContext(AuthContext);
  const canCreateSubjects = permissionsForUser(user).includes('admin.catalog');
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const [keyword, setKeyword] = useState('');
  const [showInactive, setShowInactive] = useState(false);
  const [expandedId, setExpandedId] = useState(null);

  // Modal học phần: editing=null nghĩa là đang tạo mới.
  const [subjectModalOpen, setSubjectModalOpen] = useState(false);
  const [editingSubject, setEditingSubject] = useState(null);
  const [subjectForm, setSubjectForm] = useState(EMPTY_SUBJECT);

  // Modal chương / CLO dùng chung một khung, phân biệt bằng childMode.
  const [childModal, setChildModal] = useState(null);
  const [chapterForm, setChapterForm] = useState(EMPTY_CHAPTER);
  const [cloForm, setCloForm] = useState(EMPTY_CLO);

  const fetchSubjects = async () => {
    setLoading(true);
    setError('');
    try {
      setSubjects(await listSubjects());
    } catch (err) {
      setError(err.message || 'Không tải được danh sách học phần');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSubjects();
  }, []);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = window.setTimeout(() => setNotice(''), 3200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const visibleSubjects = useMemo(() => {
    const needle = keyword.trim().toLowerCase();
    return subjects.filter((subject) => {
      if (!showInactive && !subject.is_active) return false;
      if (!needle) return true;
      return `${subject.subject_code} ${subject.subject_name}`.toLowerCase().includes(needle);
    });
  }, [subjects, keyword, showInactive]);

  const stats = useMemo(() => ({
    total: subjects.length,
    active: subjects.filter((item) => item.is_active).length,
    owned: subjects.filter((item) => item.can_manage).length,
  }), [subjects]);

  const openCreateSubject = () => {
    setEditingSubject(null);
    setSubjectForm(EMPTY_SUBJECT);
    setSubjectModalOpen(true);
  };

  const openEditSubject = (subject) => {
    setEditingSubject(subject);
    setSubjectForm({
      subject_code: subject.subject_code || '',
      subject_name: subject.subject_name || '',
      description: subject.description || '',
      is_active: subject.is_active !== false,
    });
    setSubjectModalOpen(true);
  };

  const closeSubjectModal = () => {
    if (saving) return;
    setSubjectModalOpen(false);
  };

  const handleSubmitSubject = async (event) => {
    event.preventDefault();
    if (!subjectForm.subject_code.trim() || !subjectForm.subject_name.trim()) {
      setError('Vui lòng nhập mã và tên học phần.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const payload = {
        subject_code: subjectForm.subject_code.trim(),
        subject_name: subjectForm.subject_name.trim(),
        description: subjectForm.description.trim(),
        is_active: subjectForm.is_active,
      };
      if (editingSubject) {
        await updateSubject(refId(editingSubject), payload);
        setNotice('Đã cập nhật học phần.');
      } else {
        await saveSubject(payload);
        setNotice('Đã tạo học phần mới.');
      }
      setSubjectModalOpen(false);
      await fetchSubjects();
    } catch (err) {
      setError(err.message || 'Lưu học phần thất bại');
    } finally {
      setSaving(false);
    }
  };

  const handleDeactivate = async (subject) => {
    const used = usageTotal(subject.usage_counts);
    const warning = used > 0
      ? `\n\nHọc phần này đang gắn với ${used} tài liệu/câu hỏi/đề thi. Dữ liệu đó vẫn được giữ nguyên.`
      : '';
    const confirmed = window.confirm(
      `Ngừng sử dụng học phần "${subject.subject_name}"?`
      + `\nHọc phần sẽ bị ẩn khỏi các danh sách chọn nhưng có thể bật lại bất cứ lúc nào.${warning}`,
    );
    if (!confirmed) return;
    setBusyId(refId(subject));
    setError('');
    try {
      await deactivateSubject(refId(subject));
      setNotice('Đã ngừng sử dụng học phần.');
      await fetchSubjects();
    } catch (err) {
      setError(err.message || 'Không thể ngừng sử dụng học phần');
    } finally {
      setBusyId(null);
    }
  };

  const handleRestore = async (subject) => {
    setBusyId(refId(subject));
    setError('');
    try {
      await updateSubject(refId(subject), { is_active: true });
      setNotice('Đã khôi phục học phần.');
      await fetchSubjects();
    } catch (err) {
      setError(err.message || 'Không thể khôi phục học phần');
    } finally {
      setBusyId(null);
    }
  };

  const openChildModal = (subject, mode, item = null) => {
    if (mode === 'chapter') {
      setChapterForm(item ? {
        chapter_code: item.chapter_code || '',
        chapter_name: item.chapter_name || '',
        sequence_no: item.sequence_no || 1,
        is_active: item.is_active !== false,
      } : {
        ...EMPTY_CHAPTER,
        sequence_no: (subject.chapters?.length || 0) + 1,
      });
    } else {
      setCloForm(item ? {
        clo_code: item.clo_code || '',
        description: item.description || '',
        target_weight: item.target_weight ?? 1,
        is_active: item.is_active !== false,
      } : EMPTY_CLO);
    }
    setChildModal({ subjectId: refId(subject), mode, itemId: item ? refId(item) : null });
  };

  const closeChildModal = () => {
    if (saving) return;
    setChildModal(null);
  };

  const handleSubmitChild = async (event) => {
    event.preventDefault();
    if (!childModal) return;
    const { subjectId, mode, itemId } = childModal;
    setSaving(true);
    setError('');
    try {
      if (mode === 'chapter') {
        if (!chapterForm.chapter_code.trim() || !chapterForm.chapter_name.trim()) {
          setError('Vui lòng nhập mã và tên chương.');
          return;
        }
        const payload = {
          chapter_code: chapterForm.chapter_code.trim(),
          chapter_name: chapterForm.chapter_name.trim(),
          sequence_no: Number(chapterForm.sequence_no) || 1,
          is_active: chapterForm.is_active,
        };
        if (itemId) await updateSubjectChapter(subjectId, itemId, payload);
        else await addSubjectChapter(subjectId, payload);
        setNotice(itemId ? 'Đã cập nhật chương.' : 'Đã thêm chương mới.');
      } else {
        if (!cloForm.clo_code.trim() || !cloForm.description.trim()) {
          setError('Vui lòng nhập mã CLO và mô tả.');
          return;
        }
        const payload = {
          clo_code: cloForm.clo_code.trim(),
          description: cloForm.description.trim(),
          target_weight: Number(cloForm.target_weight) || 0,
          is_active: cloForm.is_active,
        };
        if (itemId) await updateSubjectLearningOutcome(subjectId, itemId, payload);
        else await addSubjectLearningOutcome(subjectId, payload);
        setNotice(itemId ? 'Đã cập nhật CLO.' : 'Đã thêm CLO mới.');
      }
      setChildModal(null);
      await fetchSubjects();
    } catch (err) {
      setError(err.message || 'Lưu thất bại');
    } finally {
      setSaving(false);
    }
  };

  const toggleChildActive = async (subject, mode, item) => {
    setBusyId(refId(item));
    setError('');
    try {
      const payload = { is_active: item.is_active === false };
      if (mode === 'chapter') {
        await updateSubjectChapter(refId(subject), refId(item), payload);
      } else {
        await updateSubjectLearningOutcome(refId(subject), refId(item), payload);
      }
      await fetchSubjects();
    } catch (err) {
      setError(err.message || 'Không thể đổi trạng thái');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <main className="subject-manage-page">
      <section className="page-hero">
        <div className="container subject-hero-row">
          <div>
            <div className="page-hero-badge">Giảng viên</div>
            <h1 className="page-hero-title">Quản lý học phần</h1>
            <p className="page-hero-desc">
              Tạo và duy trì danh mục học phần của bạn cùng cấu trúc chương và chuẩn đầu ra (CLO).
              Đây là nền tảng phân loại cho toàn bộ tài liệu, câu hỏi và đề thi.
            </p>
          </div>
          {canCreateSubjects && (
            <button type="button" className="btn btn--primary" onClick={openCreateSubject}>
              + Thêm học phần
            </button>
          )}
        </div>
      </section>

      <section className="subject-manage-body">
        <div className="container">
          <div className="subject-stats">
            <div className="stat-chip"><b>{stats.total}</b><span>Tổng học phần</span></div>
            <div className="stat-chip"><b>{stats.active}</b><span>Đang sử dụng</span></div>
            <div className="stat-chip"><b>{stats.owned}</b><span>Bạn quản lý</span></div>
          </div>

          <div className="subject-toolbar">
            <input
              className="field-input subject-search"
              placeholder="Tìm theo mã hoặc tên học phần..."
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
            <label className="subject-switch">
              <input
                type="checkbox"
                checked={showInactive}
                onChange={(event) => setShowInactive(event.target.checked)}
              />
              Hiện học phần đã ngừng
            </label>
          </div>

          {error && <p className="subject-alert subject-alert--error">{error}</p>}
          {notice && <p className="subject-alert subject-alert--ok">{notice}</p>}

          {loading ? (
            <p className="empty-note">Đang tải danh sách học phần...</p>
          ) : visibleSubjects.length === 0 ? (
            <p className="empty-note">
              {keyword
                ? 'Không tìm thấy học phần phù hợp.'
                : canCreateSubjects
                  ? 'Chưa có học phần nào. Bấm "Thêm học phần" để bắt đầu.'
                  : 'Chưa có học phần nào được phân quyền cho bạn.'}
            </p>
          ) : (
            <div className="subject-list">
              {visibleSubjects.map((subject) => {
                const id = refId(subject);
                const expanded = expandedId === id;
                const editable = subject.can_manage;
                const counts = subject.usage_counts || {};
                return (
                  <article className={`subject-card ${subject.is_active ? '' : 'subject-card--muted'}`} key={id}>
                    <header className="subject-card-head">
                      <div className="subject-card-title">
                        <span className="subject-code">{subject.subject_code}</span>
                        <h3>{subject.subject_name}</h3>
                        {!subject.is_active && <span className="tag tag--muted">Đã ngừng</span>}
                        {!editable && <span className="tag tag--lock">Chỉ xem</span>}
                      </div>
                      <div className="subject-card-tools">
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() => setExpandedId(expanded ? null : id)}
                        >
                          {expanded ? 'Thu gọn' : 'Chi tiết'}
                        </button>
                        {editable && (
                          <>
                            <button type="button" className="btn btn--outline" onClick={() => openEditSubject(subject)}>
                              Sửa
                            </button>
                            {subject.is_active ? (
                              <button
                                type="button"
                                className="btn btn--danger"
                                disabled={busyId === id}
                                onClick={() => handleDeactivate(subject)}
                              >
                                {busyId === id ? '...' : 'Ngừng dùng'}
                              </button>
                            ) : (
                              <button
                                type="button"
                                className="btn btn--outline"
                                disabled={busyId === id}
                                onClick={() => handleRestore(subject)}
                              >
                                {busyId === id ? '...' : 'Khôi phục'}
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </header>

                    {subject.description && <p className="subject-desc">{subject.description}</p>}

                    <div className="subject-metrics">
                      <span>{subject.chapters?.length || 0} chương</span>
                      <span>{subject.learning_outcomes?.length || 0} CLO</span>
                      <span>{counts.documents || 0} tài liệu</span>
                      <span>{counts.questions || 0} câu hỏi</span>
                      <span>{counts.exams || 0} đề thi</span>
                      {subject.owner_email && <span className="subject-owner">{subject.owner_email}</span>}
                    </div>

                    {expanded && (
                      <div className="subject-detail">
                        <div className="detail-block">
                          <div className="detail-head">
                            <h4>Chương</h4>
                            {editable && (
                              <button type="button" className="btn btn--ghost" onClick={() => openChildModal(subject, 'chapter')}>
                                + Thêm chương
                              </button>
                            )}
                          </div>
                          {subject.chapters?.length ? (
                            <ul className="detail-list">
                              {subject.chapters.map((chapter) => (
                                <li key={refId(chapter)} className={chapter.is_active === false ? 'is-off' : ''}>
                                  <div>
                                    <b>{chapter.chapter_code}</b> — {chapter.chapter_name}
                                    <small>{chapter.usage_counts?.questions || 0} câu hỏi</small>
                                  </div>
                                  {editable && (
                                    <div className="detail-actions">
                                      <button type="button" onClick={() => openChildModal(subject, 'chapter', chapter)}>Sửa</button>
                                      <button
                                        type="button"
                                        disabled={busyId === refId(chapter)}
                                        onClick={() => toggleChildActive(subject, 'chapter', chapter)}
                                      >
                                        {chapter.is_active === false ? 'Bật' : 'Tắt'}
                                      </button>
                                    </div>
                                  )}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="detail-empty">Chưa có chương nào.</p>
                          )}
                        </div>

                        <div className="detail-block">
                          <div className="detail-head">
                            <h4>Chuẩn đầu ra (CLO)</h4>
                            {editable && (
                              <button type="button" className="btn btn--ghost" onClick={() => openChildModal(subject, 'clo')}>
                                + Thêm CLO
                              </button>
                            )}
                          </div>
                          {subject.learning_outcomes?.length ? (
                            <ul className="detail-list">
                              {subject.learning_outcomes.map((clo) => (
                                <li key={refId(clo)} className={clo.is_active === false ? 'is-off' : ''}>
                                  <div>
                                    <b>{clo.clo_code}</b> — {clo.description}
                                    <small>Trọng số {clo.target_weight ?? 1}</small>
                                  </div>
                                  {editable && (
                                    <div className="detail-actions">
                                      <button type="button" onClick={() => openChildModal(subject, 'clo', clo)}>Sửa</button>
                                      <button
                                        type="button"
                                        disabled={busyId === refId(clo)}
                                        onClick={() => toggleChildActive(subject, 'clo', clo)}
                                      >
                                        {clo.is_active === false ? 'Bật' : 'Tắt'}
                                      </button>
                                    </div>
                                  )}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="detail-empty">Chưa có CLO nào.</p>
                          )}
                        </div>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </div>
      </section>

      {subjectModalOpen && (
        <div className="modal-overlay" onClick={closeSubjectModal}>
          <form className="modal-card" onClick={(event) => event.stopPropagation()} onSubmit={handleSubmitSubject}>
            <h3 className="modal-title">{editingSubject ? 'Sửa học phần' : 'Thêm học phần mới'}</h3>

            <div className="field-group">
              <label className="field-label">Mã học phần</label>
              <input
                className="field-input"
                value={subjectForm.subject_code}
                maxLength={40}
                placeholder="CT101"
                onChange={(event) => setSubjectForm({ ...subjectForm, subject_code: event.target.value })}
              />
            </div>

            <div className="field-group">
              <label className="field-label">Tên học phần</label>
              <input
                className="field-input"
                value={subjectForm.subject_name}
                maxLength={200}
                placeholder="Cấu trúc dữ liệu và giải thuật"
                onChange={(event) => setSubjectForm({ ...subjectForm, subject_name: event.target.value })}
              />
            </div>

            <div className="field-group">
              <label className="field-label">Mô tả</label>
              <textarea
                className="field-input field-textarea"
                rows={3}
                value={subjectForm.description}
                placeholder="Mô tả ngắn về nội dung học phần..."
                onChange={(event) => setSubjectForm({ ...subjectForm, description: event.target.value })}
              />
            </div>

            <label className="subject-switch">
              <input
                type="checkbox"
                checked={subjectForm.is_active}
                onChange={(event) => setSubjectForm({ ...subjectForm, is_active: event.target.checked })}
              />
              Đang sử dụng
            </label>

            <div className="modal-actions">
              <button type="button" className="btn btn--outline" onClick={closeSubjectModal} disabled={saving}>Huỷ</button>
              <button type="submit" className="btn btn--primary" disabled={saving}>
                {saving ? 'Đang lưu...' : 'Lưu học phần'}
              </button>
            </div>
          </form>
        </div>
      )}

      {childModal && (
        <div className="modal-overlay" onClick={closeChildModal}>
          <form className="modal-card" onClick={(event) => event.stopPropagation()} onSubmit={handleSubmitChild}>
            <h3 className="modal-title">
              {childModal.mode === 'chapter'
                ? (childModal.itemId ? 'Sửa chương' : 'Thêm chương')
                : (childModal.itemId ? 'Sửa CLO' : 'Thêm CLO')}
            </h3>

            {childModal.mode === 'chapter' ? (
              <>
                <div className="field-group">
                  <label className="field-label">Mã chương</label>
                  <input
                    className="field-input"
                    value={chapterForm.chapter_code}
                    maxLength={40}
                    placeholder="C1"
                    onChange={(event) => setChapterForm({ ...chapterForm, chapter_code: event.target.value })}
                  />
                </div>
                <div className="field-group">
                  <label className="field-label">Tên chương</label>
                  <input
                    className="field-input"
                    value={chapterForm.chapter_name}
                    maxLength={200}
                    placeholder="Giới thiệu về cấu trúc dữ liệu"
                    onChange={(event) => setChapterForm({ ...chapterForm, chapter_name: event.target.value })}
                  />
                </div>
                <div className="field-group">
                  <label className="field-label">Thứ tự</label>
                  <input
                    type="number"
                    min={1}
                    className="field-input"
                    value={chapterForm.sequence_no}
                    onChange={(event) => setChapterForm({ ...chapterForm, sequence_no: event.target.value })}
                  />
                </div>
                <label className="subject-switch">
                  <input
                    type="checkbox"
                    checked={chapterForm.is_active}
                    onChange={(event) => setChapterForm({ ...chapterForm, is_active: event.target.checked })}
                  />
                  Đang sử dụng
                </label>
              </>
            ) : (
              <>
                <div className="field-group">
                  <label className="field-label">Mã CLO</label>
                  <input
                    className="field-input"
                    value={cloForm.clo_code}
                    maxLength={40}
                    placeholder="CLO1"
                    onChange={(event) => setCloForm({ ...cloForm, clo_code: event.target.value })}
                  />
                </div>
                <div className="field-group">
                  <label className="field-label">Mô tả chuẩn đầu ra</label>
                  <textarea
                    className="field-input field-textarea"
                    rows={3}
                    maxLength={500}
                    value={cloForm.description}
                    placeholder="Sinh viên có khả năng phân tích độ phức tạp thuật toán..."
                    onChange={(event) => setCloForm({ ...cloForm, description: event.target.value })}
                  />
                </div>
                <div className="field-group">
                  <label className="field-label">Trọng số mục tiêu (0 - 1)</label>
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    className="field-input"
                    value={cloForm.target_weight}
                    onChange={(event) => setCloForm({ ...cloForm, target_weight: event.target.value })}
                  />
                </div>
                <label className="subject-switch">
                  <input
                    type="checkbox"
                    checked={cloForm.is_active}
                    onChange={(event) => setCloForm({ ...cloForm, is_active: event.target.checked })}
                  />
                  Đang sử dụng
                </label>
              </>
            )}

            <div className="modal-actions">
              <button type="button" className="btn btn--outline" onClick={closeChildModal} disabled={saving}>Huỷ</button>
              <button type="submit" className="btn btn--primary" disabled={saving}>
                {saving ? 'Đang lưu...' : 'Lưu'}
              </button>
            </div>
          </form>
        </div>
      )}
    </main>
  );
}

export default SubjectManage;
