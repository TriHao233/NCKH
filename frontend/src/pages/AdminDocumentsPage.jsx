import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faChevronLeft, faChevronRight, faRotateRight, faUpload } from '@fortawesome/free-solid-svg-icons';
import { listAdminDocuments } from '../api/adminOverview';
import { listSubjects } from '../api/catalog';
import { chunkDocument } from '../api/chunk';
import { deleteDocument, getDocument, listDocumentPages, reindexDocument, updateDocument, updateDocumentSharing } from '../api/documents';
import { getOcrStatus, uploadSourceDocument } from '../api/ocr';
import { listUsers } from '../api/users';
import { pollJob } from '../hooks/useJobPoll';
import '../css/AdminJobsPage.css';
import '../css/AdminQuestionBankPage.css';

const PAGE_SIZE = 20;
const UPLOAD_ACCEPT = '.pdf,.doc,.docx,.md,.markdown,.txt';
const STATUS = {
  READY: { label: 'Sẵn sàng', tone: 'success' },
  PROCESSING: { label: 'Đang xử lý', tone: 'active' },
  UPLOADED: { label: 'Đã tải lên', tone: 'muted' },
  FAILED: { label: 'Xử lý lỗi', tone: 'danger' },
};
const STATUS_ORDER = ['READY', 'PROCESSING', 'UPLOADED', 'FAILED'];
const PIPELINE_STEPS = [
  { key: 'ocr_status', label: 'Đọc nội dung' },
  { key: 'chunk_status', label: 'Tách đoạn' },
  { key: 'index_status', label: 'Lập chỉ mục' },
];
const STEP_STATUS = {
  NOT_STARTED: 'chưa chạy',
  QUEUED: 'chờ chạy',
  PROCESSING: 'đang chạy',
  COMPLETED: 'xong',
  FAILED: 'lỗi',
  CANCELLED: 'đã hủy',
};
const UPLOAD_PHASE = {
  uploading: 'Đang tải file lên...',
  reading: 'Đang đọc nội dung tài liệu. Tài liệu dài có thể mất vài phút...',
  chunking: 'Đang tách đoạn và lập chỉ mục...',
};

function refId(value) {
  if (!value) return '';
  return typeof value === 'string' ? value : value.id || value._id || '';
}

function formatDateTime(value) {
  if (!value) return '--';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '--' : date.toLocaleString('vi-VN');
}

function pipelineText(document) {
  const summary = document.pipeline_summary || {};
  return PIPELINE_STEPS.map((step) => `${step.label}: ${STEP_STATUS[summary[step.key]] || STEP_STATUS.NOT_STARTED}`).join(' · ');
}

// Tài liệu đã đọc xong nhưng chưa tách đoạn: bước tách đoạn chạy theo yêu cầu, có thể bị bỏ dở.
function needsChunking(document) {
  const summary = document.pipeline_summary || {};
  return summary.ocr_status === 'COMPLETED' && !['COMPLETED', 'PROCESSING', 'QUEUED'].includes(summary.chunk_status);
}

async function fetchAllUsers() {
  const first = await listUsers({ page: 1, pageSize: 100 });
  const items = [...(first.items || [])];
  for (let page = 2; items.length < (first.total || 0); page += 1) {
    const next = await listUsers({ page, pageSize: 100 });
    if (!next.items?.length) break;
    items.push(...next.items);
  }
  return items;
}

function AdminDocumentsPage() {
  const [searchParams] = useSearchParams();
  const [filters, setFilters] = useState(() => ({
    status: STATUS[searchParams.get('status')] ? searchParams.get('status') : '',
    ownerId: '',
    subjectId: '',
  }));
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [documents, setDocuments] = useState([]);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState(null);
  const [subjects, setSubjects] = useState([]);
  const [users, setUsers] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState(null);
  const [editorError, setEditorError] = useState('');
  const [preview, setPreview] = useState(null);
  const [upload, setUpload] = useState(null);
  const [sharing, setSharing] = useState(null);
  const [sharingError, setSharingError] = useState('');
  const [deleteConfirmation, setDeleteConfirmation] = useState(null);
  const uploadAbortRef = useRef(null);

  const owners = useMemo(
    () => users.filter((user) => ['Teacher', 'Admin'].includes(user.role))
      .sort((left, right) => String(left.display_name || left.email).localeCompare(String(right.display_name || right.email), 'vi')),
    [users],
  );

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 350);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    listSubjects().then(setSubjects).catch(() => setSubjects([]));
    fetchAllUsers().then(setUsers).catch(() => setUsers([]));
  }, []);

  const fetchCounts = useCallback(async () => {
    try {
      const results = await Promise.all([
        listAdminDocuments({ page: 1, pageSize: 1 }),
        ...STATUS_ORDER.map((status) => listAdminDocuments({ page: 1, pageSize: 1, status })),
      ]);
      setCounts(Object.fromEntries([['all', results[0].total || 0], ...STATUS_ORDER.map((status, index) => [status, results[index + 1].total || 0])]));
    } catch {
      // Ô đếm không thiết yếu; giữ số cũ khi tải lỗi.
    }
  }, []);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await listAdminDocuments({ page, pageSize: PAGE_SIZE, search, ...filters });
      setDocuments(result.items || []);
      setTotal(result.total || 0);
    } catch (err) {
      setError(err.message || 'Không tải được danh sách tài liệu');
    } finally {
      setLoading(false);
    }
  }, [page, search, filters]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  useEffect(() => {
    fetchCounts();
  }, [fetchCounts]);

  useEffect(() => {
    if (!notice || notice.type === 'error') return undefined;
    const timer = setTimeout(() => setNotice(null), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  const refreshAll = useCallback(() => Promise.all([fetchDocuments(), fetchCounts()]), [fetchDocuments, fetchCounts]);

  const selected = documents.find((document) => document.id === selectedId) || null;
  const overlayOpen = Boolean(editor || preview || upload || sharing || deleteConfirmation);
  useEffect(() => {
    if (!selected || overlayOpen) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') setSelectedId('');
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [selected, overlayOpen]);

  const updateFilter = (field, value) => {
    setFilters((current) => ({ ...current, [field]: value }));
    setPage(1);
  };
  const activeFilterCount = Object.values(filters).filter(Boolean).length + (search ? 1 : 0);
  const resetFilters = () => {
    setFilters({ status: '', ownerId: '', subjectId: '' });
    setSearchInput('');
    setPage(1);
  };
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const runAction = async (action, successText) => {
    setBusy(true);
    try {
      await action();
      setNotice({ type: 'success', text: successText });
      await refreshAll();
      return true;
    } catch (err) {
      setNotice({ type: 'error', text: err.message || 'Thao tác thất bại' });
      return false;
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (document) => {
    if (await runAction(() => deleteDocument(document.id), 'Đã lưu trữ tài liệu khỏi danh sách sử dụng.')) {
      setSelectedId('');
      setDeleteConfirmation(null);
    }
  };

  const openSharing = async (document) => {
    setBusy(true);
    setSharingError('');
    try {
      const detail = await getDocument(document.id);
      setSharing({ id: document.id, title: document.title, ownerId: detail.uploaded_by_user_id || '', scope: detail.shared_scope || 'PRIVATE', userIds: detail.shared_with_user_ids || [] });
    } catch (err) {
      setNotice({ type: 'error', text: err.message || 'Không tải được thông tin chia sẻ' });
    } finally {
      setBusy(false);
    }
  };

  const saveSharing = async (event) => {
    event.preventDefault();
    setBusy(true);
    setSharingError('');
    try {
      await updateDocumentSharing(sharing.id, {
        shared_scope: sharing.scope,
        shared_with_user_ids: sharing.userIds,
        ...(sharing.ownerId ? { owner_user_id: sharing.ownerId } : {}),
      });
      setSharing(null);
      setNotice({ type: 'success', text: 'Đã lưu chia sẻ và chủ sở hữu tài liệu.' });
      await refreshAll();
    } catch (err) {
      setSharingError(err.message || 'Không lưu được chia sẻ');
    } finally {
      setBusy(false);
    }
  };

  const handleReindex = (document) => runAction(() => reindexDocument(document.id), 'Đã đưa yêu cầu lập chỉ mục lại vào hàng tác vụ.');
  const handleChunk = (document) => runAction(() => chunkDocument(document.id), 'Đã tách đoạn và lập chỉ mục cho tài liệu.');

  const handleSaveEdit = async (event) => {
    event.preventDefault();
    if (!editor.title.trim()) {
      setEditorError('Tên tài liệu không được để trống.');
      return;
    }
    setBusy(true);
    setEditorError('');
    try {
      await updateDocument(editor.id, { title: editor.title.trim(), subject_ids: editor.subjectIds });
      setEditor(null);
      setNotice({ type: 'success', text: 'Đã lưu tên và học phần của tài liệu.' });
      await refreshAll();
    } catch (err) {
      setEditorError(err.message || 'Lưu tài liệu thất bại');
    } finally {
      setBusy(false);
    }
  };

  const openPreview = async (document) => {
    setPreview({ document, loading: true, pages: [] });
    try {
      const result = await listDocumentPages(document.id, { limit: 100 });
      setPreview({ document, loading: false, pages: result.items || [] });
    } catch (err) {
      setPreview(null);
      setNotice({ type: 'error', text: err.message || 'Không tải được nội dung đã đọc' });
    }
  };

  const handleUpload = async (event) => {
    event.preventDefault();
    if (!upload.file) {
      setUpload((current) => ({ ...current, error: 'Hãy chọn file tài liệu.' }));
      return;
    }
    const controller = new AbortController();
    uploadAbortRef.current = controller;
    setUpload((current) => ({ ...current, phase: 'uploading', error: '' }));
    try {
      const result = await uploadSourceDocument(upload.file, { subjectId: upload.subjectId || undefined });
      setUpload((current) => ({ ...current, phase: 'reading' }));
      const ocr = await pollJob(getOcrStatus, result.job_id, { signal: controller.signal, timeoutMs: 45 * 60 * 1000 });
      if (ocr.status !== 'completed') throw new Error(ocr.error_message || 'Đọc nội dung tài liệu thất bại');
      setUpload((current) => ({ ...current, phase: 'chunking' }));
      await chunkDocument(result.document_id);
      setUpload(null);
      setNotice({ type: 'success', text: `Đã tải lên và xử lý xong "${upload.file.name}".` });
    } catch (err) {
      if (err.name === 'AbortError') {
        setUpload(null);
        setNotice({ type: 'success', text: 'Đã đóng cửa sổ tải lên. Tài liệu vẫn được đọc tiếp trên máy chủ; mở tài liệu đó và bấm "Xử lý tiếp" khi đọc xong.' });
      } else {
        setUpload((current) => (current ? { ...current, phase: '', error: err.message || 'Tải tài liệu thất bại' } : current));
      }
    } finally {
      uploadAbortRef.current = null;
      await refreshAll();
    }
  };

  const closeUpload = () => {
    if (uploadAbortRef.current) uploadAbortRef.current.abort();
    else setUpload(null);
  };

  return (
    <main className="admin-jobs-page question-bank-page">
      <section className="jobs-header">
        <div>
          <span>Ngân hàng</span>
          <h1>Tài liệu</h1>
          <p>Tài liệu nguồn của mọi giảng viên: theo dõi việc xử lý, chỉnh sửa, xóa và tải tài liệu mới.</p>
        </div>
        <div className="jobs-header-actions">
          <button type="button" className="jobs-secondary-button" onClick={refreshAll} disabled={loading}>
            <FontAwesomeIcon icon={faRotateRight} />
            <span>{loading ? 'Đang tải' : 'Làm mới'}</span>
          </button>
          <button type="button" className="jobs-primary-button" onClick={() => setUpload({ file: null, subjectId: '', phase: '', error: '' })}>
            <FontAwesomeIcon icon={faUpload} />
            <span>Tải tài liệu lên</span>
          </button>
        </div>
      </section>

      <section className="jobs-summary qbank-summary qbank-summary--five" aria-label="Số tài liệu theo trạng thái">
        <button type="button" className={`summary-tile ${filters.status === '' ? 'summary-tile--active' : ''}`} onClick={() => updateFilter('status', '')}>
          <b>{counts.all ?? '--'}</b>
          <span>Tất cả</span>
        </button>
        {STATUS_ORDER.map((status) => (
          <button
            type="button"
            key={status}
            className={`summary-tile ${filters.status === status ? 'summary-tile--active' : ''} ${status === 'FAILED' && counts.FAILED ? 'summary-tile--danger' : ''}`}
            onClick={() => updateFilter('status', status)}
          >
            <b>{counts[status] ?? '--'}</b>
            <span>{STATUS[status].label}</span>
          </button>
        ))}
      </section>

      <section className="jobs-toolbar qbank-toolbar qbank-toolbar--documents" aria-label="Bộ lọc tài liệu">
        <div className="toolbar-field">
          <label htmlFor="doc-search">Tìm kiếm</label>
          <input id="doc-search" type="search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Tên tài liệu hoặc tên file" />
        </div>
        <div className="toolbar-field">
          <label htmlFor="doc-owner">Người tải lên</label>
          <select id="doc-owner" value={filters.ownerId} onChange={(event) => updateFilter('ownerId', event.target.value)}>
            <option value="">Tất cả</option>
            {owners.map((user) => <option key={user.id} value={user.id}>{user.display_name || user.email}</option>)}
          </select>
        </div>
        <div className="toolbar-field">
          <label htmlFor="doc-subject">Học phần</label>
          <select id="doc-subject" value={filters.subjectId} onChange={(event) => updateFilter('subjectId', event.target.value)}>
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
              <h2>Danh sách tài liệu</h2>
              <span>{total} tài liệu{activeFilterCount > 0 ? ' phù hợp với bộ lọc' : ''}</span>
            </div>
          </div>
          <div className="jobs-table-wrap">
            <table className="jobs-table qbank-table">
              <thead>
                <tr>
                  <th>Tài liệu</th>
                  <th>Người tải lên</th>
                  <th>Học phần</th>
                  <th>Trạng thái</th>
                  <th>Số trang</th>
                  <th>Xử lý</th>
                  <th>Cập nhật</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((item) => (
                  <tr
                    key={item.id}
                    className={selectedId === item.id ? 'is-selected' : ''}
                    tabIndex={0}
                    onClick={() => setSelectedId(item.id)}
                    onKeyDown={(event) => { if (event.key === 'Enter') setSelectedId(item.id); }}
                  >
                    <td className="qbank-cell-question">
                      <strong>{item.title || item.original_filename}</strong>
                      <small>{item.original_filename}</small>
                    </td>
                    <td>
                      <span>{item.owner?.display_name || item.owner?.email || 'Chưa rõ'}</span>
                      {item.owner?.display_name && item.owner?.email && <small>{item.owner.email}</small>}
                    </td>
                    <td>{item.subjects?.map((subject) => subject.code || subject.name).filter(Boolean).join(', ') || 'Chưa gắn'}</td>
                    <td><span className={`status-pill status-pill--${STATUS[item.status]?.tone || 'muted'}`}>{STATUS[item.status]?.label || item.status}</span></td>
                    <td>{item.page_count ?? '--'}</td>
                    <td>
                      {item.error_message
                        ? <span className="qbank-error-text">{item.error_message}</span>
                        : <small>{pipelineText(item)}</small>}
                    </td>
                    <td>{formatDateTime(item.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {loading && <p className="jobs-empty">Đang tải danh sách tài liệu...</p>}
            {!loading && documents.length === 0 && (
              <p className="jobs-empty">{activeFilterCount > 0 ? 'Không có tài liệu phù hợp với bộ lọc.' : 'Chưa có tài liệu nào.'}</p>
            )}
          </div>
          <div className="jobs-pagination">
            <button type="button" aria-label="Trang trước" disabled={page <= 1 || loading} onClick={() => setPage((current) => Math.max(1, current - 1))}>
              <FontAwesomeIcon icon={faChevronLeft} />
            </button>
            <span>Trang {page} / {pageCount}</span>
            <button type="button" aria-label="Trang sau" disabled={page >= pageCount || loading} onClick={() => setPage((current) => Math.min(pageCount, current + 1))}>
              <FontAwesomeIcon icon={faChevronRight} />
            </button>
          </div>
        </div>
      </section>

      {selected && (
        <div className="qbank-drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedId(''); }}>
          <aside className="qbank-drawer" role="dialog" aria-modal="true" aria-label={`Chi tiết ${selected.title}`}>
            <div className="qbank-drawer-head">
              <div>
                <span>{selected.original_filename}</span>
                <h2>{selected.title || selected.original_filename}</h2>
              </div>
              <button type="button" className="qbank-icon-button" onClick={() => setSelectedId('')} aria-label="Đóng">×</button>
            </div>
            <div className="qbank-drawer-pills">
              <span className={`status-pill status-pill--${STATUS[selected.status]?.tone || 'muted'}`}>{STATUS[selected.status]?.label || selected.status}</span>
            </div>
            <div className="qbank-drawer-actions">
              <button type="button" className="jobs-primary-button" onClick={() => openPreview(selected)}>Xem nội dung đã đọc</button>
              <button
                type="button"
                className="jobs-secondary-button"
                disabled={busy}
                onClick={() => { setEditorError(''); setEditor({ id: selected.id, title: selected.title || '', subjectIds: (selected.subjects || []).map((subject) => subject.id) }); }}
              >
                Sửa
              </button>
              {needsChunking(selected) ? (
                <button type="button" className="jobs-secondary-button" disabled={busy} onClick={() => handleChunk(selected)}>
                  {busy ? 'Đang xử lý...' : 'Xử lý tiếp'}
                </button>
              ) : (
                <button
                  type="button"
                  className="jobs-secondary-button"
                  disabled={busy || selected.pipeline_summary?.chunk_status !== 'COMPLETED'}
                  title={selected.pipeline_summary?.chunk_status !== 'COMPLETED' ? 'Tài liệu cần tách đoạn xong trước' : undefined}
                  onClick={() => handleReindex(selected)}
                >
                  Lập chỉ mục lại
                </button>
              )}
              <button type="button" className="jobs-secondary-button" disabled={busy} onClick={() => openSharing(selected)}>Chia sẻ / chuyển sở hữu</button>
              <button type="button" className="jobs-secondary-button qbank-danger" disabled={busy} onClick={() => { setNotice(null); setDeleteConfirmation(selected); }}>Xóa</button>
            </div>

            <section className="qbank-section">
              <h3>Thông tin</h3>
              <dl className="qbank-facts">
                <div><dt>Người tải lên</dt><dd>{selected.owner?.display_name || 'Chưa rõ'}{selected.owner?.email ? ` · ${selected.owner.email}` : ''}</dd></div>
                <div><dt>Học phần</dt><dd>{selected.subjects?.map((subject) => subject.name || subject.code).filter(Boolean).join(', ') || 'Chưa gắn'}</dd></div>
                <div><dt>Số trang</dt><dd>{selected.page_count ?? '--'}</dd></div>
                <div><dt>Phiên bản</dt><dd>{selected.current_version ?? '--'}</dd></div>
                <div><dt>Tải lên lúc</dt><dd>{formatDateTime(selected.created_at)}</dd></div>
                <div><dt>Cập nhật</dt><dd>{formatDateTime(selected.updated_at)}</dd></div>
              </dl>
            </section>

            <section className="qbank-section">
              <h3>Các bước xử lý</h3>
              <dl className="qbank-facts">
                {PIPELINE_STEPS.map((step) => (
                  <div key={step.key}>
                    <dt>{step.label}</dt>
                    <dd>{STEP_STATUS[selected.pipeline_summary?.[step.key]] || STEP_STATUS.NOT_STARTED}</dd>
                  </div>
                ))}
              </dl>
              {selected.error_message && <p className="qbank-note qbank-note--error">Lỗi gần nhất: {selected.error_message}</p>}
              {needsChunking(selected) && (
                <p className="qbank-note qbank-note--warning">Tài liệu đã đọc xong nhưng chưa tách đoạn, nên chưa dùng được để sinh câu hỏi. Bấm "Xử lý tiếp".</p>
              )}
              <p className="qbank-muted">
                Chạy lại hoặc hủy từng bước ở <Link to={`/quan-ly-job?kind=document&search=${encodeURIComponent(selected.title || '')}`}>Tác vụ hệ thống</Link>.
              </p>
            </section>
          </aside>
        </div>
      )}

      {sharing && (
        <div className="modal-overlay">
          <form className="qbank-dialog qbank-dialog--narrow" role="dialog" aria-modal="true" aria-label="Chia sẻ và chuyển sở hữu tài liệu" onSubmit={saveSharing}>
            <h2>Chia sẻ {sharing.title}</h2>
            <label className="qbank-field"><span>Phạm vi</span><select value={sharing.scope} onChange={(event) => setSharing({ ...sharing, scope: event.target.value })}><option value="PRIVATE">Riêng tư</option><option value="SUBJECT">Chia sẻ theo môn</option></select></label>
            <label className="qbank-field"><span>Chủ sở hữu tài liệu</span><select value={sharing.ownerId} onChange={(event) => setSharing({ ...sharing, ownerId: event.target.value })}><option value="">Không đổi chủ sở hữu</option>{owners.filter((owner) => owner.is_active !== false || owner.id === sharing.ownerId).map((owner) => <option key={owner.id} value={owner.id}>{owner.display_name || owner.email}</option>)}</select></label>
            <div className="qbank-field"><span>Chia sẻ riêng cho giảng viên</span>{users.filter((user) => user.role === 'Teacher' && (user.is_active !== false || sharing.userIds.includes(user.id))).map((user) => <label className="qbank-check" key={user.id}><input type="checkbox" checked={sharing.userIds.includes(user.id)} onChange={() => setSharing({ ...sharing, userIds: sharing.userIds.includes(user.id) ? sharing.userIds.filter((id) => id !== user.id) : [...sharing.userIds, user.id] })} />{user.display_name || user.email}</label>)}</div>
            {sharingError && <p className="qbank-note qbank-note--error" role="alert">{sharingError}</p>}
            <div className="qbank-dialog-actions"><button type="button" className="jobs-secondary-button" disabled={busy} onClick={() => setSharing(null)}>Hủy</button><button type="submit" className="jobs-primary-button" disabled={busy}>{busy ? 'Đang lưu...' : 'Lưu chia sẻ'}</button></div>
          </form>
        </div>
      )}

      {deleteConfirmation && (
        <div className="modal-overlay">
          <div className="qbank-dialog qbank-dialog--narrow" role="dialog" aria-modal="true" aria-label="Xác nhận xóa tài liệu">
            <h2>Xóa {deleteConfirmation.title}?</h2><p>Tài liệu sẽ được lưu trữ và không còn dùng để sinh câu hỏi.</p>
            {notice?.type === 'error' && <p role="alert" className="qbank-note qbank-note--error">{notice.text}</p>}
            <div className="qbank-dialog-actions"><button type="button" className="jobs-secondary-button" disabled={busy} onClick={() => setDeleteConfirmation(null)}>Hủy</button><button type="button" className="jobs-primary-button" disabled={busy} onClick={() => handleDelete(deleteConfirmation)}>Xác nhận xóa</button></div>
          </div>
        </div>
      )}

      {editor && (
        <div className="modal-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setEditor(null); }}>
          <form className="qbank-dialog qbank-dialog--narrow" onSubmit={handleSaveEdit} role="dialog" aria-modal="true" aria-label="Sửa tài liệu">
            <div className="qbank-dialog-head">
              <h2>Sửa tài liệu</h2>
              <button type="button" className="qbank-icon-button" onClick={() => setEditor(null)} aria-label="Đóng">×</button>
            </div>
            <label className="qbank-field">
              <span>Tên tài liệu</span>
              <input maxLength={300} value={editor.title} onChange={(event) => setEditor({ ...editor, title: event.target.value })} />
            </label>
            <div className="qbank-field">
              <span>Dùng cho học phần</span>
              {subjects.filter((subject) => subject.is_active !== false || editor.subjectIds.includes(refId(subject))).map((subject) => (
                <label className="qbank-check" key={refId(subject)}>
                  <input
                    type="checkbox"
                    checked={editor.subjectIds.includes(refId(subject))}
                    onChange={() => setEditor({
                      ...editor,
                      subjectIds: editor.subjectIds.includes(refId(subject))
                        ? editor.subjectIds.filter((id) => id !== refId(subject))
                        : [...editor.subjectIds, refId(subject)],
                    })}
                  />
                  <span><b>{subject.subject_code}</b> {subject.subject_name}</span>
                </label>
              ))}
              {subjects.length === 0 && <small>Chưa có học phần nào.</small>}
            </div>
            {editorError && <p className="qbank-note qbank-note--error" role="alert">{editorError}</p>}
            <div className="qbank-dialog-actions">
              <button type="button" className="jobs-secondary-button" onClick={() => setEditor(null)} disabled={busy}>Hủy</button>
              <button type="submit" className="jobs-primary-button" disabled={busy}>{busy ? 'Đang lưu...' : 'Lưu thay đổi'}</button>
            </div>
          </form>
        </div>
      )}

      {preview && (
        <div className="modal-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) setPreview(null); }}>
          <div className="qbank-dialog" role="dialog" aria-modal="true" aria-label="Nội dung đã đọc">
            <div className="qbank-dialog-head">
              <h2>Nội dung đã đọc từ "{preview.document.title}"</h2>
              <button type="button" className="qbank-icon-button" onClick={() => setPreview(null)} aria-label="Đóng">×</button>
            </div>
            {preview.loading && <p className="qbank-muted">Đang tải...</p>}
            {!preview.loading && preview.pages.length === 0 && <p className="qbank-muted">Tài liệu chưa có nội dung đã đọc.</p>}
            {preview.pages.length >= 100 && <p className="qbank-muted">Chỉ hiển thị 100 trang đầu.</p>}
            {preview.pages.map((item) => (
              <section className="qbank-page-preview" key={item.id || item.page_number}>
                <h3>Trang {item.page_number || item.unit_number || '--'}</h3>
                <pre>{item.cleaned_text || item.raw_text || '(trang trống)'}</pre>
              </section>
            ))}
          </div>
        </div>
      )}

      {upload && (
        <div className="modal-overlay">
          <form className="qbank-dialog qbank-dialog--narrow" onSubmit={handleUpload} role="dialog" aria-modal="true" aria-label="Tải tài liệu lên">
            <div className="qbank-dialog-head">
              <h2>Tải tài liệu lên</h2>
              <button type="button" className="qbank-icon-button" onClick={closeUpload} aria-label="Đóng">×</button>
            </div>
            <label className="qbank-field">
              <span>File tài liệu</span>
              <input type="file" accept={UPLOAD_ACCEPT} disabled={Boolean(upload.phase)} onChange={(event) => setUpload({ ...upload, file: event.target.files?.[0] || null, error: '' })} />
              <small>Nhận PDF, Word (.doc, .docx), Markdown và .txt.</small>
            </label>
            <label className="qbank-field">
              <span>Học phần</span>
              <select value={upload.subjectId} disabled={Boolean(upload.phase)} onChange={(event) => setUpload({ ...upload, subjectId: event.target.value })}>
                <option value="">Chưa gắn học phần</option>
                {subjects.filter((subject) => subject.is_active !== false).map((subject) => (
                  <option key={refId(subject)} value={refId(subject)}>{subject.subject_code} — {subject.subject_name}</option>
                ))}
              </select>
            </label>
            {upload.phase && <p className="qbank-note qbank-note--warning" role="status">{UPLOAD_PHASE[upload.phase]}</p>}
            {upload.error && <p className="qbank-note qbank-note--error" role="alert">{upload.error}</p>}
            <div className="qbank-dialog-actions">
              <button type="button" className="jobs-secondary-button" onClick={closeUpload}>{upload.phase ? 'Đóng, để máy chủ đọc tiếp' : 'Hủy'}</button>
              <button type="submit" className="jobs-primary-button" disabled={Boolean(upload.phase)}>{upload.phase ? 'Đang xử lý...' : 'Tải lên và xử lý'}</button>
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

export default AdminDocumentsPage;
