import { useCallback, useEffect, useMemo, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faBookOpen, faMagnifyingGlass, faPen, faPlus } from '@fortawesome/free-solid-svg-icons';
import {
  addSubjectChapter,
  addSubjectLearningOutcome,
  getCatalogOverview,
  saveSubject,
  updateSubject,
  updateSubjectChapter,
  updateSubjectLearningOutcome,
} from '../api/catalog';
import WorkspaceHero from '../components/workspace/WorkspaceHero';
import Drawer from '../components/workspace/Drawer';
import { EmptyState, ErrorState, Notice, SkeletonRows } from '../components/workspace/Feedback';
import { useConfirm, useFlash } from '../components/workspace/Dialog';
import { Tabs } from '../components/workspace/Navigation';
import { childId } from '../features/review/reviewModel';
import '../css/workspace.css';
import '../css/AdminPages.css';

const EMPTY_SUBJECT = { id: '', subject_code: '', subject_name: '', description: '', is_active: true };

function usageText(counts = {}) {
  const parts = [
    counts.documents ? `${counts.documents} tài liệu` : '',
    counts.questions ? `${counts.questions} câu hỏi` : '',
    counts.exams ? `${counts.exams} đề` : '',
  ].filter(Boolean);
  return parts.length ? parts.join(', ') : 'Chưa được dùng';
}

/** Trang Học phần: môn học, chương và chuẩn đầu ra (CLO) dùng để phân loại câu hỏi. */
function CatalogAdminPage() {
  const { flash, show: showFlash, clear: clearFlash } = useFlash();
  const [confirm, confirmDialog] = useConfirm();
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [activeId, setActiveId] = useState('');
  const [search, setSearch] = useState('');
  const [detailTab, setDetailTab] = useState('chapters');
  const [drawer, setDrawer] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const result = await getCatalogOverview();
      setSubjects(result.subjects || []);
    } catch (err) {
      setLoadError(err.message || 'Không tải được danh sách học phần.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return subjects;
    return subjects.filter((subject) => `${subject.subject_code} ${subject.subject_name}`.toLowerCase().includes(term));
  }, [subjects, search]);

  const active = subjects.find((subject) => subject.id === activeId) || filtered[0] || null;
  const chapters = [...(active?.chapters || [])].sort((a, b) => (a.sequence_no || 0) - (b.sequence_no || 0));
  const clos = active?.learning_outcomes || [];

  const openDrawer = (kind, item = null) => {
    const forms = {
      subject: item
        ? { id: item.id, subject_code: item.subject_code || '', subject_name: item.subject_name || '', description: item.description || '', is_active: item.is_active !== false }
        : { ...EMPTY_SUBJECT },
      chapter: item
        ? { id: childId(item), chapter_code: item.chapter_code || '', chapter_name: item.chapter_name || '', sequence_no: item.sequence_no || 1, is_active: item.is_active !== false }
        : { id: '', chapter_code: `CH${String(chapters.length + 1).padStart(2, '0')}`, chapter_name: '', sequence_no: chapters.length + 1, is_active: true },
      clo: item
        ? { id: childId(item), clo_code: item.clo_code || '', description: item.description || '', target_weight: item.target_weight ?? 1, is_active: item.is_active !== false }
        : { id: '', clo_code: `CLO${clos.length + 1}`, description: '', target_weight: 1, is_active: true },
    };
    setDrawer({ kind, form: forms[kind], error: '' });
  };

  const setField = (patch) => setDrawer((current) => ({ ...current, form: { ...current.form, ...patch }, error: '' }));

  const validate = ({ kind, form }) => {
    if (kind === 'subject' && (!form.subject_code.trim() || !form.subject_name.trim())) return 'Nhập mã và tên học phần.';
    if (kind === 'chapter' && (!form.chapter_code.trim() || !form.chapter_name.trim())) return 'Nhập mã và tên chương.';
    if (kind === 'chapter' && !(Number(form.sequence_no) >= 1)) return 'Thứ tự chương phải từ 1 trở lên.';
    if (kind === 'clo') {
      if (!form.clo_code.trim() || !form.description.trim()) return 'Nhập mã và mô tả chuẩn đầu ra.';
      const weight = Number(form.target_weight);
      if (!Number.isFinite(weight) || weight < 0 || weight > 1) return 'Trọng số phải từ 0 đến 1.';
    }
    return '';
  };

  const saveDrawer = async () => {
    const message = validate(drawer);
    if (message) {
      setDrawer((current) => ({ ...current, error: message }));
      return;
    }
    const { kind, form } = drawer;
    const { id, ...payload } = form;
    setSaving(true);
    clearFlash();
    try {
      if (kind === 'subject') {
        const cleaned = { ...payload, subject_code: payload.subject_code.trim(), subject_name: payload.subject_name.trim() };
        const saved = id ? await updateSubject(id, cleaned) : await saveSubject(cleaned);
        if (saved?.id) setActiveId(saved.id);
      } else if (kind === 'chapter') {
        const cleaned = { ...payload, chapter_code: payload.chapter_code.trim(), chapter_name: payload.chapter_name.trim(), sequence_no: Number(payload.sequence_no) };
        if (id) await updateSubjectChapter(active.id, id, cleaned);
        else await addSubjectChapter(active.id, cleaned);
      } else {
        const cleaned = { ...payload, clo_code: payload.clo_code.trim(), description: payload.description.trim(), target_weight: Number(payload.target_weight) };
        if (id) await updateSubjectLearningOutcome(active.id, id, cleaned);
        else await addSubjectLearningOutcome(active.id, cleaned);
      }
      setDrawer(null);
      showFlash('success', id ? 'Đã lưu thay đổi.' : 'Đã thêm mới.');
      await load();
    } catch (err) {
      setDrawer((current) => ({ ...current, error: err.message || 'Lưu thất bại.' }));
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (kind, item) => {
    const turningOff = item.is_active !== false;
    const names = { subject: 'học phần', chapter: 'chương', clo: 'chuẩn đầu ra' };
    if (turningOff) {
      const accepted = await confirm({
        title: `Tạm khoá ${names[kind]}`,
        description: 'Mục bị khoá không hiện trong lựa chọn khi giảng viên sinh câu hỏi hoặc làm đề. Dữ liệu cũ vẫn giữ nguyên.',
        confirmLabel: 'Tạm khoá',
        tone: 'danger',
      });
      if (!accepted) return;
    }
    setSaving(true);
    clearFlash();
    try {
      if (kind === 'subject') await updateSubject(item.id, { is_active: !turningOff });
      if (kind === 'chapter') await updateSubjectChapter(active.id, childId(item), { is_active: !turningOff });
      if (kind === 'clo') await updateSubjectLearningOutcome(active.id, childId(item), { is_active: !turningOff });
      showFlash('success', turningOff ? 'Đã tạm khoá.' : 'Đã bật lại.');
      await load();
    } catch (err) {
      showFlash('error', err.message || 'Thao tác thất bại.');
    } finally {
      setSaving(false);
    }
  };

  const drawerTitle = drawer && {
    subject: drawer.form.id ? 'Sửa học phần' : 'Thêm học phần',
    chapter: drawer.form.id ? 'Sửa chương' : 'Thêm chương',
    clo: drawer.form.id ? 'Sửa chuẩn đầu ra' : 'Thêm chuẩn đầu ra',
  }[drawer.kind];

  return (
    <main className="ws-page catalog-admin-page">
      <WorkspaceHero
        badge="Quản trị viên"
        title="Học phần"
        description="Môn học, chương và chuẩn đầu ra dùng để phân loại tài liệu, câu hỏi và đề thi."
        actions={(
          <button type="button" className="btn btn--primary" onClick={() => openDrawer('subject')}>
            <FontAwesomeIcon icon={faPlus} />
            Thêm học phần
          </button>
        )}
      />

      <section className="ws-body">
        <div className="container ws-main">
          {flash && <Notice tone={flash.tone} onDismiss={clearFlash}>{flash.message}</Notice>}
          {loading && subjects.length === 0 ? (
            <div className="ws-card"><SkeletonRows rows={5} lines={2} /></div>
          ) : loadError ? (
            <div className="ws-card"><ErrorState message={loadError} onRetry={load} /></div>
          ) : subjects.length === 0 ? (
            <div className="ws-card">
              <EmptyState
                icon={faBookOpen}
                title="Chưa có học phần"
                description="Thêm học phần đầu tiên để giảng viên gắn tài liệu và câu hỏi."
                action={<button type="button" className="btn btn--primary btn--sm" onClick={() => openDrawer('subject')}>Thêm học phần</button>}
              />
            </div>
          ) : (
            <div className="ws-grid ws-grid--list">
              <section className="ws-card">
                <div className="ws-card-title" style={{ marginBottom: 12 }}>
                  <h2>Danh sách</h2>
                  <span className="ws-list-count tabular">{filtered.length} / {subjects.length} học phần</span>
                </div>
                <label className="ws-search" style={{ marginBottom: 10 }}>
                  <span className="ws-sr-only">Tìm học phần</span>
                  <FontAwesomeIcon icon={faMagnifyingGlass} />
                  <input className="ws-input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Mã hoặc tên học phần" />
                </label>
                <div className="ad-subject-list">
                  {filtered.map((subject) => (
                    <button
                      type="button"
                      key={subject.id}
                      className="ad-subject-item"
                      aria-current={active?.id === subject.id}
                      onClick={() => setActiveId(subject.id)}
                    >
                      <b>{subject.subject_code} - {subject.subject_name}</b>
                      <span>
                        {subject.is_active === false && <span className="ws-pill ws-pill--outline" style={{ marginRight: 6 }}>Tạm khoá</span>}
                        {subject.usage_counts?.questions ? `${subject.usage_counts.questions} câu hỏi đang dùng` : usageText(subject.usage_counts)}
                      </span>
                    </button>
                  ))}
                  {filtered.length === 0 && <p className="ws-hint">Không có học phần khớp từ khoá.</p>}
                </div>
              </section>

              {active && (
                <section className="ws-card">
                  <div className="ws-card-head">
                    <div className="ws-card-title">
                      <h2>{active.subject_name}</h2>
                      <span>{active.subject_code}, {usageText(active.usage_counts)}</span>
                    </div>
                    <div className="ws-card-actions">
                      <button type="button" className="btn btn--outline btn--sm" onClick={() => openDrawer('subject', active)}>
                        <FontAwesomeIcon icon={faPen} />
                        Sửa
                      </button>
                      <button type="button" className="btn btn--ghost btn--sm" disabled={saving} onClick={() => toggle('subject', active)}>
                        {active.is_active === false ? 'Bật lại' : 'Tạm khoá'}
                      </button>
                    </div>
                  </div>
                  {active.description && <p className="ws-muted" style={{ margin: '0 0 16px', fontSize: '0.9rem' }}>{active.description}</p>}

                  <Tabs
                    label="Nội dung học phần"
                    value={detailTab}
                    onChange={setDetailTab}
                    items={[
                      { value: 'chapters', label: 'Chương', count: chapters.length },
                      { value: 'clos', label: 'CLO', count: clos.length },
                    ]}
                  />

                  <div style={{ marginTop: 14 }}>
                    {detailTab === 'chapters' ? (
                      <>
                        {chapters.length === 0 ? (
                          <EmptyState compact title="Chưa có chương" description="Thêm chương để giảng viên phân loại câu hỏi theo nội dung." />
                        ) : (
                          <div className="ws-table-wrap">
                            <table className="ws-table">
                              <thead><tr><th className="ws-num" style={{ width: 60 }}>Thứ tự</th><th>Chương</th><th>Đang dùng</th><th aria-label="Thao tác" /></tr></thead>
                              <tbody>
                                {chapters.map((chapter) => (
                                  <tr key={childId(chapter)} style={{ opacity: chapter.is_active === false ? 0.6 : 1 }}>
                                    <td className="ws-num">{chapter.sequence_no}</td>
                                    <td><strong>{chapter.chapter_code}</strong> {chapter.chapter_name}</td>
                                    <td>{chapter.is_active === false ? <span className="ws-pill ws-pill--outline">Tạm khoá</span> : usageText(chapter.usage_counts)}</td>
                                    <td>
                                      <div className="ws-row-actions">
                                        <button type="button" className="ws-icon-btn" aria-label={`Sửa ${chapter.chapter_code}`} onClick={() => openDrawer('chapter', chapter)}>
                                          <FontAwesomeIcon icon={faPen} />
                                        </button>
                                        <button type="button" className="btn btn--ghost btn--sm" disabled={saving} onClick={() => toggle('chapter', chapter)}>
                                          {chapter.is_active === false ? 'Bật' : 'Khoá'}
                                        </button>
                                      </div>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                        <button type="button" className="btn btn--outline btn--sm" style={{ marginTop: 12 }} onClick={() => openDrawer('chapter')}>
                          <FontAwesomeIcon icon={faPlus} />
                          Thêm chương
                        </button>
                      </>
                    ) : (
                      <>
                        {clos.length === 0 ? (
                          <EmptyState compact title="Chưa có chuẩn đầu ra" description="CLO giúp đo độ phủ ngân hàng câu hỏi theo mục tiêu học phần." />
                        ) : (
                          <div className="ws-table-wrap">
                            <table className="ws-table">
                              <thead><tr><th>CLO</th><th className="ws-num">Trọng số</th><th>Đang dùng</th><th aria-label="Thao tác" /></tr></thead>
                              <tbody>
                                {clos.map((clo) => (
                                  <tr key={childId(clo)} style={{ opacity: clo.is_active === false ? 0.6 : 1 }}>
                                    <td><strong>{clo.clo_code}</strong> <span className="ws-muted">{clo.description}</span></td>
                                    <td className="ws-num">{clo.target_weight ?? 1}</td>
                                    <td>{clo.is_active === false ? <span className="ws-pill ws-pill--outline">Tạm khoá</span> : usageText(clo.usage_counts)}</td>
                                    <td>
                                      <div className="ws-row-actions">
                                        <button type="button" className="ws-icon-btn" aria-label={`Sửa ${clo.clo_code}`} onClick={() => openDrawer('clo', clo)}>
                                          <FontAwesomeIcon icon={faPen} />
                                        </button>
                                        <button type="button" className="btn btn--ghost btn--sm" disabled={saving} onClick={() => toggle('clo', clo)}>
                                          {clo.is_active === false ? 'Bật' : 'Khoá'}
                                        </button>
                                      </div>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                        <button type="button" className="btn btn--outline btn--sm" style={{ marginTop: 12 }} onClick={() => openDrawer('clo')}>
                          <FontAwesomeIcon icon={faPlus} />
                          Thêm CLO
                        </button>
                      </>
                    )}
                  </div>
                </section>
              )}
            </div>
          )}
        </div>
      </section>

      <Drawer
        open={Boolean(drawer)}
        title={drawerTitle}
        subtitle={drawer?.kind !== 'subject' ? active?.subject_name : undefined}
        onClose={() => setDrawer(null)}
        busy={saving}
        as="form"
        onSubmit={saveDrawer}
        footer={(
          <>
            <button type="button" className="btn btn--outline" onClick={() => setDrawer(null)} disabled={saving}>Huỷ</button>
            <button type="submit" className="btn btn--primary" disabled={saving}>{saving ? 'Đang lưu...' : 'Lưu'}</button>
          </>
        )}
      >
        {drawer?.kind === 'subject' && (
          <>
            <label className="ws-field"><span>Mã học phần</span><input className="ws-input" value={drawer.form.subject_code} onChange={(event) => setField({ subject_code: event.target.value })} placeholder="CT177" /></label>
            <label className="ws-field"><span>Tên học phần</span><input className="ws-input" value={drawer.form.subject_name} onChange={(event) => setField({ subject_name: event.target.value })} /></label>
            <label className="ws-field"><span>Mô tả</span><textarea className="ws-textarea" value={drawer.form.description} onChange={(event) => setField({ description: event.target.value })} /></label>
            <label className="ws-check"><input type="checkbox" checked={drawer.form.is_active} onChange={(event) => setField({ is_active: event.target.checked })} />Đang dùng</label>
          </>
        )}
        {drawer?.kind === 'chapter' && (
          <>
            <label className="ws-field"><span>Mã chương</span><input className="ws-input" value={drawer.form.chapter_code} onChange={(event) => setField({ chapter_code: event.target.value })} /></label>
            <label className="ws-field"><span>Tên chương</span><input className="ws-input" value={drawer.form.chapter_name} onChange={(event) => setField({ chapter_name: event.target.value })} /></label>
            <label className="ws-field"><span>Thứ tự</span><input className="ws-input" type="number" min="1" value={drawer.form.sequence_no} onChange={(event) => setField({ sequence_no: event.target.value })} /></label>
            <label className="ws-check"><input type="checkbox" checked={drawer.form.is_active} onChange={(event) => setField({ is_active: event.target.checked })} />Đang dùng</label>
          </>
        )}
        {drawer?.kind === 'clo' && (
          <>
            <label className="ws-field"><span>Mã CLO</span><input className="ws-input" value={drawer.form.clo_code} onChange={(event) => setField({ clo_code: event.target.value })} /></label>
            <label className="ws-field"><span>Mô tả</span><textarea className="ws-textarea" value={drawer.form.description} onChange={(event) => setField({ description: event.target.value })} /></label>
            <label className="ws-field">
              <span>Trọng số mục tiêu (0 đến 1)</span>
              <input className="ws-input" type="number" min="0" max="1" step="0.05" value={drawer.form.target_weight} onChange={(event) => setField({ target_weight: event.target.value })} />
              <small>Dùng để tính độ phủ ngân hàng câu hỏi theo CLO.</small>
            </label>
            <label className="ws-check"><input type="checkbox" checked={drawer.form.is_active} onChange={(event) => setField({ is_active: event.target.checked })} />Đang dùng</label>
          </>
        )}
        {drawer?.error && <Notice tone="error">{drawer.error}</Notice>}
      </Drawer>
      {confirmDialog}
    </main>
  );
}

export default CatalogAdminPage;
