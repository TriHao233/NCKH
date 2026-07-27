import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faChevronLeft,
  faChevronRight,
  faFilter,
  faRotateRight,
  faSearch,
} from '@fortawesome/free-solid-svg-icons';
import { listAdminAuditLogs } from '../api/adminAudit';
import '../css/AdminJobsPage.css';

const PAGE_SIZE = 25;

const ACTION_OPTIONS = [
  { value: 'all', label: 'Tất cả hành động' },
  { value: 'user.admin_update', label: 'Cập nhật user' },
  { value: 'user.deactivate', label: 'Khóa user' },
  { value: 'QUESTION_EVALUATED', label: 'Đánh giá câu hỏi' },
  { value: 'QUESTION_APPROVED', label: 'Duyệt câu hỏi' },
  { value: 'QUESTION_REJECTED', label: 'Từ chối câu hỏi' },
  { value: 'QUESTION_NEEDS_REVISION', label: 'Yêu cầu sửa' },
  { value: 'QUESTION_REVIEW_CLAIMED', label: 'Claim review' },
  { value: 'QUESTION_REVIEW_RELEASED', label: 'Release review' },
  { value: 'admin.job_retry', label: 'Retry job' },
  { value: 'admin.job_cancel', label: 'Hủy job' },
  { value: 'admin.moodle_target_save', label: 'Lưu Moodle target' },
  { value: 'admin.moodle_target_deactivate', label: 'Tắt Moodle target' },
  { value: 'admin.moodle_target_check', label: 'Kiểm tra Moodle target' },
  { value: 'auth.demo_login', label: 'Demo login' },
];

const ENTITY_OPTIONS = [
  { value: 'all', label: 'Tất cả entity' },
  { value: 'user', label: 'User' },
  { value: 'QUESTION', label: 'Question' },
  { value: 'generation', label: 'Generation job' },
  { value: 'evaluation', label: 'Evaluation job' },
  { value: 'document', label: 'Document job' },
  { value: 'moodle_target', label: 'Moodle target' },
];

function compactId(value) {
  if (!value) return 'Chưa có';
  const text = String(value);
  if (text.length <= 14) return text;
  return `${text.slice(0, 7)}...${text.slice(-5)}`;
}

function formatDateTime(value) {
  if (!value) return 'Chưa có';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Chưa có';
  return new Intl.DateTimeFormat('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date);
}

function actionLabel(action) {
  return ACTION_OPTIONS.find((option) => option.value === action)?.label
    || String(action || 'UNKNOWN').replace(/[._]/g, ' ');
}

function jsonText(value) {
  if (!value || (Array.isArray(value) && value.length === 0)) return '{}';
  if (!Array.isArray(value) && typeof value === 'object' && Object.keys(value).length === 0) return '{}';
  return JSON.stringify(value, null, 2);
}

function entityText(log) {
  const entity = log.entity || {};
  return `${entity.type || 'entity'} ${compactId(entity.id)}`;
}

function actorText(log) {
  const actor = log.actor || {};
  if (actor.user_id) return compactId(actor.user_id);
  return actor.service_name || actor.type || 'System';
}

function AdminAuditPage() {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [actionFilter, setActionFilter] = useState('all');
  const [entityTypeFilter, setEntityTypeFilter] = useState('all');
  const [actorUserId, setActorUserId] = useState('');
  const [entityId, setEntityId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedId, setSelectedId] = useState('');

  useEffect(() => {
    const handle = setTimeout(() => {
      setPage(1);
      setSearchTerm(searchInput.trim());
    }, 350);
    return () => clearTimeout(handle);
  }, [searchInput]);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await listAdminAuditLogs({
        page,
        pageSize: PAGE_SIZE,
        search: searchTerm,
        action: actionFilter,
        entityType: entityTypeFilter,
        actorUserId: actorUserId.trim(),
        entityId: entityId.trim(),
        dateFrom,
        dateTo,
      });
      setLogs(result.items || []);
      setTotal(result.total || 0);
    } catch (err) {
      setError(err.message || 'Không tải được audit log');
      setLogs([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [actionFilter, actorUserId, dateFrom, dateTo, entityId, entityTypeFilter, page, searchTerm]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    if (!logs.length) {
      setSelectedId('');
      return;
    }
    if (!selectedId || !logs.some((log) => log.id === selectedId)) {
      setSelectedId(logs[0].id);
    }
  }, [logs, selectedId]);

  const selectedLog = useMemo(
    () => logs.find((log) => log.id === selectedId) || logs[0] || null,
    [logs, selectedId],
  );
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const updateActionFilter = (value) => {
    setActionFilter(value);
    setPage(1);
  };

  const updateEntityTypeFilter = (value) => {
    setEntityTypeFilter(value);
    setPage(1);
  };

  const updateActorUserId = (value) => {
    setActorUserId(value);
    setPage(1);
  };

  const updateEntityId = (value) => {
    setEntityId(value);
    setPage(1);
  };

  return (
    <main className="admin-jobs-page">
      <section className="jobs-header">
        <div>
          <span>Quản trị hệ thống</span>
          <h1>Audit log</h1>
          <p>Theo dõi hành động nhạy cảm, thay đổi quyền và workflow trên toàn hệ thống.</p>
        </div>
        <button type="button" className="jobs-primary-button" onClick={fetchLogs} disabled={loading}>
          <FontAwesomeIcon icon={faRotateRight} />
          <span>{loading ? 'Đang tải' : 'Làm mới'}</span>
        </button>
      </section>

      <section className="jobs-toolbar jobs-toolbar--audit" aria-label="Bộ lọc audit">
        <div className="toolbar-field toolbar-field--search">
          <label htmlFor="audit-search">
            <FontAwesomeIcon icon={faSearch} />
            Tìm kiếm
          </label>
          <input
            id="audit-search"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Action, actor, entity..."
          />
        </div>
        <div className="toolbar-field">
          <label htmlFor="audit-action">
            <FontAwesomeIcon icon={faFilter} />
            Hành động
          </label>
          <select id="audit-action" value={actionFilter} onChange={(event) => updateActionFilter(event.target.value)}>
            {ACTION_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
        <div className="toolbar-field">
          <label htmlFor="audit-entity-type">Entity</label>
          <select id="audit-entity-type" value={entityTypeFilter} onChange={(event) => updateEntityTypeFilter(event.target.value)}>
            {ENTITY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
        <div className="toolbar-field">
          <label htmlFor="audit-actor">Actor ID</label>
          <input id="audit-actor" value={actorUserId} onChange={(event) => updateActorUserId(event.target.value)} placeholder="User ID" />
        </div>
        <div className="toolbar-field">
          <label htmlFor="audit-entity">Entity ID</label>
          <input id="audit-entity" value={entityId} onChange={(event) => updateEntityId(event.target.value)} placeholder="Object ID" />
        </div>
        <div className="toolbar-field">
          <label htmlFor="audit-from">Từ ngày</label>
          <input id="audit-from" type="datetime-local" value={dateFrom} onChange={(event) => { setDateFrom(event.target.value); setPage(1); }} />
        </div>
        <div className="toolbar-field">
          <label htmlFor="audit-to">Đến ngày</label>
          <input id="audit-to" type="datetime-local" value={dateTo} onChange={(event) => { setDateTo(event.target.value); setPage(1); }} />
        </div>
      </section>

      {error && <p className="jobs-error">{error}</p>}

      <section className="jobs-layout">
        <div className="jobs-table-panel">
          <div className="jobs-table-header">
            <div>
              <h2>Nhật ký</h2>
              <span>{total} kết quả</span>
            </div>
          </div>
          <div className="jobs-table-wrap">
            <table className="jobs-table">
              <thead>
                <tr>
                  <th>Thời gian</th>
                  <th>Hành động</th>
                  <th>Actor</th>
                  <th>Entity</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr
                    key={log.id}
                    className={selectedId === log.id ? 'is-selected' : ''}
                    onClick={() => setSelectedId(log.id)}
                  >
                    <td>
                      <span>{formatDateTime(log.created_at)}</span>
                      <small>{compactId(log.id)}</small>
                    </td>
                    <td>
                      <strong>{actionLabel(log.action)}</strong>
                      <small>{log.action}</small>
                    </td>
                    <td>
                      <span>{actorText(log)}</span>
                      <small>{log.actor?.role || log.actor?.type || 'actor'}</small>
                    </td>
                    <td>
                      <span className="entity-text">{entityText(log)}</span>
                      <small>{compactId(log.entity?.version_id)}</small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && logs.length === 0 && (
              <p className="jobs-empty">Không có audit log phù hợp với bộ lọc hiện tại.</p>
            )}
            {loading && (
              <p className="jobs-empty">Đang tải audit log...</p>
            )}
          </div>
          <div className="jobs-pagination">
            <button type="button" disabled={page <= 1 || loading} onClick={() => setPage((current) => Math.max(1, current - 1))}>
              <FontAwesomeIcon icon={faChevronLeft} />
            </button>
            <span>Trang {page} / {pageCount}</span>
            <button type="button" disabled={page >= pageCount || loading} onClick={() => setPage((current) => Math.min(pageCount, current + 1))}>
              <FontAwesomeIcon icon={faChevronRight} />
            </button>
          </div>
        </div>

        <aside className="job-detail-panel" aria-label="Chi tiết audit">
          {selectedLog ? (
            <>
              <div className="job-detail-header">
                <span>{selectedLog.action}</span>
                <h2>{actionLabel(selectedLog.action)}</h2>
              </div>
              <dl className="job-detail-list">
                <div>
                  <dt>Thời gian</dt>
                  <dd>{formatDateTime(selectedLog.created_at)}</dd>
                </div>
                <div>
                  <dt>Actor</dt>
                  <dd>{actorText(selectedLog)}</dd>
                </div>
                <div>
                  <dt>Entity</dt>
                  <dd>{entityText(selectedLog)}</dd>
                </div>
              </dl>
              <div className="audit-json-grid">
                <div className="job-detail-json">
                  <span>Before</span>
                  <pre>{jsonText(selectedLog.before)}</pre>
                </div>
                <div className="job-detail-json">
                  <span>After</span>
                  <pre>{jsonText(selectedLog.after)}</pre>
                </div>
                <div className="job-detail-json">
                  <span>Changes</span>
                  <pre>{jsonText(selectedLog.changes)}</pre>
                </div>
                <div className="job-detail-json">
                  <span>Metadata</span>
                  <pre>{jsonText(selectedLog.metadata)}</pre>
                </div>
              </div>
            </>
          ) : (
            <p className="job-detail-empty">Chọn một audit log để xem chi tiết.</p>
          )}
        </aside>
      </section>
    </main>
  );
}

export default AdminAuditPage;
