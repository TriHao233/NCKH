import React, { useMemo, useState } from 'react';
import {
  addSubjectChapter,
  addSubjectLearningOutcome,
  saveSubject,
  updateSubject,
  updateSubjectChapter,
  updateSubjectLearningOutcome,
} from '../../api/catalog';
import CatalogModal from './CatalogModal';

const EMPTY_SUBJECT_FORM = { id: '', subject_code: '', subject_name: '', description: '', is_active: true };
const EMPTY_CHAPTER_FORM = { id: '', chapter_code: '', chapter_name: '', sequence_no: 1, is_active: true };
const EMPTY_CLO_FORM = { id: '', clo_code: '', description: '', target_weight: 1, is_active: true };

function childId(item) {
  return item?.id || item?._id || '';
}

function usageText(counts = {}) {
  const parts = [
    counts.documents ? `${counts.documents} tài liệu` : '',
    counts.questions ? `${counts.questions} câu hỏi` : '',
    counts.exams ? `${counts.exams} đề` : '',
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : 'Chưa được dùng';
}

function SubjectsTab({ subjects, saving, run }) {
  const [activeId, setActiveId] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [dialog, setDialog] = useState(null);
  const [dialogError, setDialogError] = useState('');

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return subjects.filter((subject) => {
      if (statusFilter === 'active' && subject.is_active === false) return false;
      if (statusFilter === 'locked' && subject.is_active !== false) return false;
      if (!needle) return true;
      return [subject.subject_code, subject.subject_name, subject.owner_email]
        .some((value) => String(value || '').toLowerCase().includes(needle));
    });
  }, [subjects, search, statusFilter]);

  const active = filtered.find((subject) => subject.id === activeId) || filtered[0] || null;
  const chapters = useMemo(
    () => [...(active?.chapters || [])].sort((left, right) => (left.sequence_no || 0) - (right.sequence_no || 0)),
    [active],
  );
  const outcomes = active?.learning_outcomes || [];

  const openDialog = (type, form) => {
    setDialogError('');
    setDialog({ type, form });
  };
  const closeDialog = () => setDialog(null);
  const setField = (field, value) => setDialog((current) => ({ ...current, form: { ...current.form, [field]: value } }));

  const finishDialog = (outcome) => {
    if (outcome.ok) closeDialog();
    else setDialogError(outcome.error?.message || 'Lưu thất bại');
    return outcome;
  };

  const handleSaveSubject = async (event) => {
    event.preventDefault();
    const { id, ...payload } = dialog.form;
    const submit = (extra = {}) => run(
      () => (id ? updateSubject(id, { ...payload, ...extra }) : saveSubject(payload)),
      id ? 'Đã lưu học phần.' : 'Đã tạo học phần.',
      { quiet: true },
    );
    let outcome = await submit();
    // Đổi mã của học phần đang được dùng cần người quản trị xác nhận lại.
    if (!outcome.ok && id && outcome.error?.status === 409 && /xác nhận/.test(outcome.error.message || '')) {
      if (!window.confirm(`${outcome.error.message}\n\nVẫn đổi mã học phần?`)) return;
      outcome = await submit({ confirm_code_change: true });
    }
    if (finishDialog(outcome).ok) setActiveId(outcome.result.id);
  };

  const handleSaveChapter = async (event) => {
    event.preventDefault();
    const { id, ...payload } = dialog.form;
    const normalized = { ...payload, sequence_no: Number(payload.sequence_no) || 1 };
    finishDialog(await run(
      () => (id ? updateSubjectChapter(active.id, id, normalized) : addSubjectChapter(active.id, normalized)),
      id ? 'Đã lưu chương.' : 'Đã thêm chương.',
      { quiet: true },
    ));
  };

  const handleSaveClo = async (event) => {
    event.preventDefault();
    const { id, ...payload } = dialog.form;
    const normalized = { ...payload, target_weight: Number(payload.target_weight) || 0 };
    finishDialog(await run(
      () => (id ? updateSubjectLearningOutcome(active.id, id, normalized) : addSubjectLearningOutcome(active.id, normalized)),
      id ? 'Đã lưu CLO.' : 'Đã thêm CLO.',
      { quiet: true },
    ));
  };

  const toggleSubject = () => {
    const lock = active.is_active !== false;
    if (lock && !window.confirm(`Tạm khóa học phần "${active.subject_name}"? Học phần sẽ không còn trong danh sách chọn khi tạo tài liệu, câu hỏi và đề thi mới.`)) return;
    run(() => updateSubject(active.id, { is_active: !lock }), lock ? 'Đã tạm khóa học phần.' : 'Đã kích hoạt học phần.');
  };

  const toggleChapter = (chapter) => {
    const lock = chapter.is_active !== false;
    if (lock && !window.confirm(`Tạm khóa chương "${chapter.chapter_name}"?`)) return;
    run(
      () => updateSubjectChapter(active.id, childId(chapter), { is_active: !lock }),
      lock ? 'Đã tạm khóa chương.' : 'Đã kích hoạt chương.',
    );
  };

  const toggleClo = (clo) => {
    const lock = clo.is_active !== false;
    if (lock && !window.confirm(`Tạm khóa ${clo.clo_code}?`)) return;
    run(
      () => updateSubjectLearningOutcome(active.id, childId(clo), { is_active: !lock }),
      lock ? 'Đã tạm khóa CLO.' : 'Đã kích hoạt CLO.',
    );
  };

  return (
    <div className="catalog-card">
      <div className="catalog-card-title-row">
        <div>
          <h2>Học phần</h2>
          <p className="catalog-card-note">Mỗi học phần gồm các chương và chuẩn đầu ra (CLO) để gắn cho tài liệu, câu hỏi.</p>
        </div>
        <button type="button" onClick={() => openDialog('subject', EMPTY_SUBJECT_FORM)} disabled={saving}>Thêm học phần</button>
      </div>

      <div className="subject-layout">
        <div className="subject-side">
          <input
            type="search"
            className="catalog-input"
            aria-label="Tìm học phần"
            placeholder="Tìm theo mã, tên, người tạo"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <select className="catalog-input" aria-label="Lọc trạng thái học phần" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">Tất cả ({subjects.length})</option>
            <option value="active">Đang dùng</option>
            <option value="locked">Đã khóa</option>
          </select>
          <div className="subject-list">
            {filtered.map((subject) => (
              <button
                type="button"
                className={`${active?.id === subject.id ? 'active' : ''} ${subject.is_active === false ? 'inactive' : ''}`}
                key={subject.id}
                onClick={() => setActiveId(subject.id)}
              >
                <b>{subject.subject_code}{subject.is_active === false && <em className="catalog-badge catalog-badge--locked">Đã khóa</em>}</b>
                <span>{subject.subject_name}</span>
                <small>{usageText(subject.usage_counts)}</small>
              </button>
            ))}
            {filtered.length === 0 && <p className="catalog-empty-note">{subjects.length ? 'Không có học phần phù hợp.' : 'Chưa có học phần nào.'}</p>}
          </div>
        </div>

        {active ? (
          <div className="subject-detail">
            <div className="catalog-detail-head">
              <div>
                <h3>{active.subject_code} — {active.subject_name}</h3>
                {active.description && <p>{active.description}</p>}
                <p>
                  {usageText(active.usage_counts)}
                  {active.owner_email && ` · Người tạo: ${active.owner_email}`}
                  {active.is_active === false && ' · Đang tạm khóa'}
                </p>
              </div>
              <div className="catalog-item-actions">
                <button
                  type="button"
                  className="catalog-ghost-button"
                  onClick={() => openDialog('subject', {
                    id: active.id,
                    subject_code: active.subject_code || '',
                    subject_name: active.subject_name || '',
                    description: active.description || '',
                    is_active: active.is_active !== false,
                  })}
                  disabled={saving}
                >
                  Sửa
                </button>
                <button type="button" className="catalog-ghost-button" onClick={toggleSubject} disabled={saving}>
                  {active.is_active === false ? 'Kích hoạt' : 'Tạm khóa'}
                </button>
              </div>
            </div>

            <section className="catalog-section">
              <div className="catalog-section-head">
                <h4>Chương ({chapters.length})</h4>
                <button type="button" className="catalog-ghost-button" onClick={() => openDialog('chapter', { ...EMPTY_CHAPTER_FORM, sequence_no: chapters.length + 1 })} disabled={saving}>
                  Thêm chương
                </button>
              </div>
              <div className="catalog-list">
                {chapters.map((chapter) => (
                  <article className={`catalog-list-item ${chapter.is_active === false ? 'inactive' : ''}`} key={childId(chapter)}>
                    <div>
                      <b>
                        {chapter.sequence_no}. {chapter.chapter_code} — {chapter.chapter_name}
                        {chapter.is_active === false && <em className="catalog-badge catalog-badge--locked">Đã khóa</em>}
                      </b>
                      <span>{usageText(chapter.usage_counts)}</span>
                    </div>
                    <div className="catalog-item-actions">
                      <button
                        type="button"
                        className="catalog-ghost-button"
                        onClick={() => openDialog('chapter', {
                          id: childId(chapter),
                          chapter_code: chapter.chapter_code || '',
                          chapter_name: chapter.chapter_name || '',
                          sequence_no: chapter.sequence_no || 1,
                          is_active: chapter.is_active !== false,
                        })}
                        disabled={saving}
                      >
                        Sửa
                      </button>
                      <button type="button" className="catalog-ghost-button" onClick={() => toggleChapter(chapter)} disabled={saving}>
                        {chapter.is_active === false ? 'Kích hoạt' : 'Tạm khóa'}
                      </button>
                    </div>
                  </article>
                ))}
                {chapters.length === 0 && <p className="catalog-empty-note">Học phần này chưa có chương.</p>}
              </div>
            </section>

            <section className="catalog-section">
              <div className="catalog-section-head">
                <h4>Chuẩn đầu ra CLO ({outcomes.length})</h4>
                <button type="button" className="catalog-ghost-button" onClick={() => openDialog('clo', EMPTY_CLO_FORM)} disabled={saving}>
                  Thêm CLO
                </button>
              </div>
              <div className="catalog-list">
                {outcomes.map((clo) => (
                  <article className={`catalog-list-item ${clo.is_active === false ? 'inactive' : ''}`} key={childId(clo)}>
                    <div>
                      <b>
                        {clo.clo_code}
                        {clo.is_active === false && <em className="catalog-badge catalog-badge--locked">Đã khóa</em>}
                      </b>
                      <p>{clo.description}</p>
                      <span>Tỉ trọng mục tiêu {clo.target_weight ?? 1} · {usageText(clo.usage_counts)}</span>
                    </div>
                    <div className="catalog-item-actions">
                      <button
                        type="button"
                        className="catalog-ghost-button"
                        onClick={() => openDialog('clo', {
                          id: childId(clo),
                          clo_code: clo.clo_code || '',
                          description: clo.description || '',
                          target_weight: clo.target_weight ?? 1,
                          is_active: clo.is_active !== false,
                        })}
                        disabled={saving}
                      >
                        Sửa
                      </button>
                      <button type="button" className="catalog-ghost-button" onClick={() => toggleClo(clo)} disabled={saving}>
                        {clo.is_active === false ? 'Kích hoạt' : 'Tạm khóa'}
                      </button>
                    </div>
                  </article>
                ))}
                {outcomes.length === 0 && <p className="catalog-empty-note">Học phần này chưa có CLO.</p>}
              </div>
            </section>
          </div>
        ) : (
          <p className="catalog-empty-note">Chọn hoặc thêm một học phần để xem chương và CLO.</p>
        )}
      </div>

      {dialog?.type === 'subject' && (
        <CatalogModal title={dialog.form.id ? 'Sửa học phần' : 'Thêm học phần'} onClose={closeDialog}>
          <form className="catalog-form" onSubmit={handleSaveSubject}>
            <label className="catalog-field">
              <span>Mã học phần</span>
              <input required maxLength={40} placeholder="Ví dụ: CT101" value={dialog.form.subject_code} onChange={(event) => setField('subject_code', event.target.value)} />
            </label>
            <label className="catalog-field">
              <span>Tên học phần</span>
              <input required maxLength={200} value={dialog.form.subject_name} onChange={(event) => setField('subject_name', event.target.value)} />
            </label>
            <label className="catalog-field">
              <span>Mô tả</span>
              <input value={dialog.form.description} onChange={(event) => setField('description', event.target.value)} />
            </label>
            <label className="catalog-check">
              <input type="checkbox" checked={dialog.form.is_active} onChange={(event) => setField('is_active', event.target.checked)} />
              Đang dùng
            </label>
            {dialogError && <p className="catalog-form-error" role="alert">{dialogError}</p>}
            <div className="catalog-form-actions">
              <button type="button" className="catalog-ghost-button" onClick={closeDialog} disabled={saving}>Hủy</button>
              <button type="submit" disabled={saving}>{saving ? 'Đang lưu...' : 'Lưu học phần'}</button>
            </div>
          </form>
        </CatalogModal>
      )}

      {dialog?.type === 'chapter' && (
        <CatalogModal title={dialog.form.id ? 'Sửa chương' : `Thêm chương cho ${active?.subject_code}`} onClose={closeDialog}>
          <form className="catalog-form" onSubmit={handleSaveChapter}>
            <label className="catalog-field">
              <span>Mã chương</span>
              <input required maxLength={40} placeholder="Ví dụ: CH01" value={dialog.form.chapter_code} onChange={(event) => setField('chapter_code', event.target.value)} />
            </label>
            <label className="catalog-field">
              <span>Tên chương</span>
              <input required maxLength={200} value={dialog.form.chapter_name} onChange={(event) => setField('chapter_name', event.target.value)} />
            </label>
            <label className="catalog-field">
              <span>Thứ tự trong học phần</span>
              <input type="number" min="1" required value={dialog.form.sequence_no} onChange={(event) => setField('sequence_no', event.target.value)} />
            </label>
            <label className="catalog-check">
              <input type="checkbox" checked={dialog.form.is_active} onChange={(event) => setField('is_active', event.target.checked)} />
              Đang dùng
            </label>
            {dialogError && <p className="catalog-form-error" role="alert">{dialogError}</p>}
            <div className="catalog-form-actions">
              <button type="button" className="catalog-ghost-button" onClick={closeDialog} disabled={saving}>Hủy</button>
              <button type="submit" disabled={saving}>{saving ? 'Đang lưu...' : 'Lưu chương'}</button>
            </div>
          </form>
        </CatalogModal>
      )}

      {dialog?.type === 'clo' && (
        <CatalogModal title={dialog.form.id ? 'Sửa CLO' : `Thêm CLO cho ${active?.subject_code}`} onClose={closeDialog}>
          <form className="catalog-form" onSubmit={handleSaveClo}>
            <label className="catalog-field">
              <span>Mã CLO</span>
              <input required maxLength={40} placeholder="Ví dụ: CLO1" value={dialog.form.clo_code} onChange={(event) => setField('clo_code', event.target.value)} />
            </label>
            <label className="catalog-field">
              <span>Mô tả chuẩn đầu ra</span>
              <textarea required rows={3} maxLength={500} value={dialog.form.description} onChange={(event) => setField('description', event.target.value)} />
            </label>
            <label className="catalog-field">
              <span>Tỉ trọng mục tiêu (0 đến 1)</span>
              <input type="number" min="0" max="1" step="0.05" required value={dialog.form.target_weight} onChange={(event) => setField('target_weight', event.target.value)} />
              <small>Phần câu hỏi mong muốn cho CLO này trong ngân hàng của học phần.</small>
            </label>
            <label className="catalog-check">
              <input type="checkbox" checked={dialog.form.is_active} onChange={(event) => setField('is_active', event.target.checked)} />
              Đang dùng
            </label>
            {dialogError && <p className="catalog-form-error" role="alert">{dialogError}</p>}
            <div className="catalog-form-actions">
              <button type="button" className="catalog-ghost-button" onClick={closeDialog} disabled={saving}>Hủy</button>
              <button type="submit" disabled={saving}>{saving ? 'Đang lưu...' : 'Lưu CLO'}</button>
            </div>
          </form>
        </CatalogModal>
      )}
    </div>
  );
}

export default SubjectsTab;
