import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faChevronLeft,
  faChevronRight,
  faFileCsv,
  faFileExcel,
  faFilter,
  faRotateRight,
  faSearch,
} from '@fortawesome/free-solid-svg-icons';
import { listAdminAuditLogs } from '../api/adminAudit';
import { listUsers } from '../api/users';
import {
  downloadCsv,
  downloadXlsx,
  rowsToCsv,
  timestampedCsvFilename,
  timestampedXlsxFilename,
} from '../utils/csvExport';
import '../css/AdminJobsPage.css';

const PAGE_SIZE = 25;
const EXPORT_PAGE_SIZE = 100;

const ACTION_OPTIONS = [
  { value: 'all', label: 'Tất cả hành động' },
  { value: 'user.admin_update', label: 'Cập nhật người dùng' },
  { value: 'user.deactivate', label: 'Khóa người dùng' },
  { value: 'QUESTION_EVALUATED', label: 'Đánh giá câu hỏi' },
  { value: 'QUESTION_APPROVED', label: 'Duyệt câu hỏi' },
  { value: 'QUESTION_REJECTED', label: 'Từ chối câu hỏi' },
  { value: 'QUESTION_NEEDS_REVISION', label: 'Yêu cầu sửa' },
  { value: 'QUESTION_REVIEW_CLAIMED', label: 'Nhận kiểm duyệt' },
  { value: 'QUESTION_REVIEW_RELEASED', label: 'Trả câu kiểm duyệt' },
  { value: 'QUESTION_REVIEW_ASSIGNED', label: 'Phân công kiểm duyệt' },
  { value: 'QUESTION_COMMENT_ADDED', label: 'Thêm bình luận câu hỏi' },
  { value: 'QUESTION_COMMENT_UPDATED', label: 'Sửa bình luận câu hỏi' },
  { value: 'QUESTION_COMMENT_DELETED', label: 'Xóa bình luận câu hỏi' },
  { value: 'catalog.subject_create', label: 'Tạo học phần' },
  { value: 'catalog.subject_update', label: 'Sửa học phần' },
  { value: 'catalog.subject_deactivate', label: 'Ngừng dùng học phần' },
  { value: 'catalog.chapter_create', label: 'Tạo chương' },
  { value: 'catalog.chapter_update', label: 'Sửa chương' },
  { value: 'catalog.clo_create', label: 'Tạo chuẩn đầu ra' },
  { value: 'catalog.clo_update', label: 'Sửa chuẩn đầu ra' },
  { value: 'catalog.ai_model_create', label: 'Thêm mô hình AI' },
  { value: 'catalog.ai_model_update', label: 'Sửa mô hình AI' },
  { value: 'catalog.ai_model_activate', label: 'Bật mô hình AI' },
  { value: 'catalog.ai_model_deactivate', label: 'Khóa mô hình AI' },
  { value: 'catalog.prompt_create', label: 'Tạo mẫu prompt' },
  { value: 'catalog.prompt_update', label: 'Sửa mẫu prompt' },
  { value: 'catalog.prompt_activate', label: 'Bật mẫu prompt' },
  { value: 'catalog.prompt_deactivate', label: 'Tắt mẫu prompt' },
  { value: 'catalog.evaluation_policy_create', label: 'Tạo tiêu chí đánh giá' },
  { value: 'catalog.evaluation_policy_update', label: 'Sửa tiêu chí đánh giá' },
  { value: 'catalog.evaluation_policy_activate', label: 'Áp dụng tiêu chí đánh giá' },
  { value: 'catalog.evaluation_policy_deactivate', label: 'Ngừng dùng tiêu chí đánh giá' },
  { value: 'QUESTION_SUBMITTED_FOR_REVIEW', label: 'Câu hỏi được gửi duyệt' },
  { value: 'question.submit_review', label: 'Gửi duyệt câu hỏi' },
  { value: 'question.sharing_update', label: 'Đổi chia sẻ câu hỏi' },
  { value: 'question.archive', label: 'Lưu trữ câu hỏi' },
  { value: 'document.sharing_update', label: 'Đổi chia sẻ tài liệu' },
  { value: 'document.archive', label: 'Lưu trữ tài liệu' },
  { value: 'document.ocr_correction', label: 'Sửa nội dung đã đọc của tài liệu' },
  { value: 'REVIEW_POLICY_UPDATED', label: 'Sửa chính sách duyệt lần 2' },
  { value: 'ai_model.save', label: 'Lưu mô hình AI' },
  { value: 'ai_model.activate', label: 'Bật / khóa mô hình AI' },
  { value: 'prompt.save', label: 'Lưu mẫu prompt' },
  { value: 'prompt.activate', label: 'Bật / tắt mẫu prompt' },
  { value: 'evaluation_policy.save', label: 'Lưu tiêu chí đánh giá' },
  { value: 'evaluation_policy.activate', label: 'Đổi tiêu chí đánh giá đang dùng' },
  { value: 'user.invite', label: 'Mời người dùng' },
  { value: 'user.create', label: 'Tạo người dùng' },
  { value: 'admin.job_retry', label: 'Chạy lại tác vụ' },
  { value: 'admin.job_cancel', label: 'Hủy tác vụ' },
  { value: 'admin.moodle_target_save', label: 'Lưu cấu hình Moodle' },
  { value: 'admin.moodle_target_deactivate', label: 'Tắt cấu hình Moodle' },
  { value: 'admin.moodle_target_check', label: 'Kiểm tra cấu hình Moodle' },
  { value: 'auth.demo_login', label: 'Đăng nhập demo' },
  { value: 'user.password_reset', label: 'Đặt lại mật khẩu' },
];

const ENTITY_OPTIONS = [
  { value: 'all', label: 'Tất cả đối tượng' },
  { value: 'user', label: 'Người dùng' },
  { value: 'question', label: 'Câu hỏi (soạn, chia sẻ)' },
  { value: 'QUESTION', label: 'Câu hỏi (kiểm duyệt)' },
  { value: 'document', label: 'Tài liệu' },
  { value: 'subject', label: 'Học phần' },
  { value: 'chapter', label: 'Chương' },
  { value: 'clo', label: 'Chuẩn đầu ra' },
  { value: 'generation', label: 'Tác vụ sinh câu hỏi' },
  { value: 'evaluation', label: 'Tác vụ đánh giá' },
  { value: 'ai_model', label: 'Mô hình AI' },
  { value: 'prompt_template', label: 'Mẫu prompt' },
  { value: 'evaluation_policy', label: 'Tiêu chí đánh giá' },
  { value: 'review_policy', label: 'Chính sách duyệt' },
  { value: 'moodle_target', label: 'Kết nối Moodle' },
];
const ENTITY_LABEL = {
  ...Object.fromEntries(ENTITY_OPTIONS.slice(1).map((option) => [option.value, option.label])),
  question: 'Câu hỏi',
  QUESTION: 'Câu hỏi',
  document_page: 'Trang tài liệu',
  subject: 'Học phần',
};
const ROLE_LABEL = { Admin: 'Quản trị viên', Teacher: 'Giảng viên', Reviewer: 'Người duyệt' };

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

// Nhật ký chỉ lưu mã đối tượng; tra tên người dùng từ danh sách tài khoản khi có thể.
function entityText(log, userById = new Map()) {
  const entity = log.entity || {};
  const label = ENTITY_LABEL[entity.type] || entity.type || 'Đối tượng';
  if (entity.type === 'user') {
    const user = userById.get(entity.id);
    if (user) return `${label}: ${user.display_name || user.email}`;
  }
  return `${label} ${compactId(entity.id)}`;
}

function roleText(log, userById = new Map()) {
  const role = log.actor?.role || userById.get(log.actor?.user_id)?.role;
  if (role) return ROLE_LABEL[role] || role;
  return log.actor?.type === 'USER' ? 'Người dùng' : 'Hệ thống';
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

function actorText(log) {
  const actor = log.actor || {};
  if (actor.user_name) return actor.user_name;
  if (actor.user_id) return compactId(actor.user_id);
  return actor.service_name || actor.type || 'Hệ thống';
}

const AUDIT_EXPORT_COLUMNS = [
  { header: 'Mã nhật ký (Audit ID)', value: (log) => log.id },
  { header: 'Ngày tạo', value: (log) => log.created_at || '' },
  { header: 'Thao tác (Action)', value: (log) => log.action || '' },
  { header: 'Nhãn thao tác', value: (log) => actionLabel(log.action) },
  { header: 'Người dùng/Hệ thống', value: actorText },
  { header: 'Vai trò', value: (log) => log.actor?.role || '' },
  { header: 'Loại tác nhân', value: (log) => log.actor?.type || '' },
  { header: 'Đối tượng', value: (log) => entityText(log) },
  { header: 'Loại đối tượng', value: (log) => log.entity?.type || '' },
  { header: 'Mã đối tượng', value: (log) => log.entity?.id || '' },
  { header: 'Mã phiên bản đối tượng', value: (log) => log.entity?.version_id || '' },
  { header: 'Dữ liệu trước (Before)', value: (log) => log.before || {} },
  { header: 'Dữ liệu sau (After)', value: (log) => log.after || {} },
  { header: 'Thay đổi (Changes)', value: (log) => log.changes || [] },
  { header: 'Thông tin thêm (Metadata)', value: (log) => log.metadata || {} },
];

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
  const [exportKey, setExportKey] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [users, setUsers] = useState([]);
  const userById = useMemo(() => new Map(users.map((user) => [user.id, user])), [users]);

  useEffect(() => {
    fetchAllUsers()
      .then((items) => setUsers(items.sort((left, right) => String(left.display_name || left.email).localeCompare(String(right.display_name || right.email), 'vi'))))
      .catch(() => setUsers([]));
  }, []);

  useEffect(() => {
    const handle = setTimeout(() => {
      setPage(1);
      setSearchTerm(searchInput.trim());
    }, 350);
    return () => clearTimeout(handle);
  }, [searchInput]);

  const buildAuditQuery = useCallback((nextPage = page, pageSize = PAGE_SIZE) => ({
    page: nextPage,
    pageSize,
    search: searchTerm,
    action: actionFilter,
    entityType: entityTypeFilter,
    actorUserId: actorUserId.trim(),
    entityId: entityId.trim(),
    dateFrom,
    dateTo,
  }), [actionFilter, actorUserId, dateFrom, dateTo, entityId, entityTypeFilter, page, searchTerm]);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await listAdminAuditLogs(buildAuditQuery());
      setLogs(result.items || []);
      setTotal(result.total || 0);
    } catch (err) {
      setError(err.message || 'Không tải được nhật ký');
      setLogs([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [buildAuditQuery]);

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

  const fetchAuditForExport = async () => {
    const firstResult = await listAdminAuditLogs(buildAuditQuery(1, EXPORT_PAGE_SIZE));
    const exportRows = [...(firstResult.items || [])];
    const expectedTotal = firstResult.total || exportRows.length;

    for (let nextPage = 2; exportRows.length < expectedTotal; nextPage += 1) {
      const result = await listAdminAuditLogs(buildAuditQuery(nextPage, EXPORT_PAGE_SIZE));
      const pageRows = result.items || [];
      if (!pageRows.length) break;
      exportRows.push(...pageRows);
    }

    return exportRows;
  };

  const exportAuditCsv = async () => {
    setExportKey('audit-csv');
    try {
      const exportRows = await fetchAuditForExport();
      const csv = rowsToCsv(AUDIT_EXPORT_COLUMNS, exportRows);
      downloadCsv(timestampedCsvFilename('admin-audit'), csv);
    } catch (err) {
      window.alert(err.message || 'Xuất CSV thất bại');
    } finally {
      setExportKey('');
    }
  };

  const exportAuditXlsx = async () => {
    setExportKey('audit-xlsx');
    try {
      const exportRows = await fetchAuditForExport();
      downloadXlsx(timestampedXlsxFilename('admin-audit'), AUDIT_EXPORT_COLUMNS, exportRows, 'Admin audit');
    } catch (err) {
      window.alert(err.message || 'Xuất XLSX thất bại');
    } finally {
      setExportKey('');
    }
  };

  const exportDisabled = loading || Boolean(exportKey) || total === 0;

  return (
    <main className="admin-jobs-page">
      <section className="jobs-header">
        <div>
          <span>Hệ thống</span>
          <h1>Nhật ký hệ thống</h1>
          <p>Ai đã làm gì, lúc nào và thay đổi những gì trên toàn hệ thống.</p>
        </div>
        <div className="jobs-header-actions">
          <button
            type="button"
            className="jobs-secondary-button"
            onClick={exportAuditCsv}
            disabled={exportDisabled}
          >
            <FontAwesomeIcon icon={faFileCsv} />
            <span>{exportKey === 'audit-csv' ? 'Đang xuất' : 'Xuất CSV'}</span>
          </button>
          <button
            type="button"
            className="jobs-secondary-button"
            onClick={exportAuditXlsx}
            disabled={exportDisabled}
          >
            <FontAwesomeIcon icon={faFileExcel} />
            <span>{exportKey === 'audit-xlsx' ? 'Đang xuất' : 'Xuất XLSX'}</span>
          </button>
          <button type="button" className="jobs-primary-button" onClick={fetchLogs} disabled={loading}>
            <FontAwesomeIcon icon={faRotateRight} />
            <span>{loading ? 'Đang tải' : 'Làm mới'}</span>
          </button>
        </div>
      </section>

      <section className="jobs-toolbar jobs-toolbar--audit" aria-label="Bộ lọc nhật ký">
        <div className="toolbar-field toolbar-field--search">
          <label htmlFor="audit-search">
            <FontAwesomeIcon icon={faSearch} />
            Tìm kiếm
          </label>
          <input
            id="audit-search"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Hành động, người thực hiện, đối tượng..."
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
          <label htmlFor="audit-entity-type">Đối tượng</label>
          <select id="audit-entity-type" value={entityTypeFilter} onChange={(event) => updateEntityTypeFilter(event.target.value)}>
            {ENTITY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
        <div className="toolbar-field">
          <label htmlFor="audit-actor">Người thực hiện</label>
          <select id="audit-actor" value={actorUserId} onChange={(event) => updateActorUserId(event.target.value)}>
            <option value="">Tất cả</option>
            {users.map((user) => <option key={user.id} value={user.id}>{user.display_name || user.email}</option>)}
          </select>
        </div>
        <div className="toolbar-field">
          <label htmlFor="audit-entity">Mã đối tượng</label>
          <input id="audit-entity" value={entityId} onChange={(event) => updateEntityId(event.target.value)} placeholder="Dán mã để lọc một đối tượng" />
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
                  <th>Người thực hiện</th>
                  <th>Đối tượng</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr
                    key={log.id}
                    tabIndex={0}
                    aria-label={`Xem nhật ký ${actionLabel(log.action)} ${formatDateTime(log.created_at)}`}
                    className={selectedId === log.id ? 'is-selected' : ''}
                    onClick={() => setSelectedId(log.id)}
                    onKeyDown={(event) => {
                      if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) {
                        event.preventDefault();
                        setSelectedId(log.id);
                      }
                    }}
                  >
                    <td>
                      <span>{formatDateTime(log.created_at)}</span>
                    </td>
                    <td>
                      <strong>{actionLabel(log.action)}</strong>
                    </td>
                    <td>
                      <span>{actorText(log)}</span>
                      <small>{roleText(log, userById)}</small>
                    </td>
                    <td>
                      <span className="entity-text">{entityText(log, userById)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && logs.length === 0 && (
              <p className="jobs-empty">Không có nhật ký phù hợp với bộ lọc hiện tại.</p>
            )}
            {loading && (
              <p className="jobs-empty">Đang tải nhật ký...</p>
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

        <aside className="job-detail-panel" aria-label="Chi tiết nhật ký">
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
                  <dt>Người thực hiện</dt>
                  <dd>{actorText(selectedLog)} · {roleText(selectedLog, userById)}</dd>
                </div>
                <div>
                  <dt>Đối tượng</dt>
                  <dd>
                    {entityText(selectedLog, userById)}
                    {['question', 'QUESTION'].includes(selectedLog.entity?.type) && selectedLog.entity?.id && (
                      <> · <Link to={`/quan-ly?questionId=${selectedLog.entity.id}`}>Mở câu hỏi</Link></>
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Mã đối tượng</dt>
                  <dd>{selectedLog.entity?.id || 'Không có'}</dd>
                </div>
              </dl>
              <div className="audit-json-grid">
                <div className="job-detail-json">
                  <span>Trước</span>
                  <pre>{jsonText(selectedLog.before)}</pre>
                </div>
                <div className="job-detail-json">
                  <span>Sau</span>
                  <pre>{jsonText(selectedLog.after)}</pre>
                </div>
                <div className="job-detail-json">
                  <span>Thay đổi</span>
                  <pre>{jsonText(selectedLog.changes)}</pre>
                </div>
                <div className="job-detail-json">
                  <span>Dữ liệu bổ sung</span>
                  <pre>{jsonText(selectedLog.metadata)}</pre>
                </div>
              </div>
            </>
          ) : (
            <p className="job-detail-empty">Chọn một nhật ký để xem chi tiết.</p>
          )}
        </aside>
      </section>
    </main>
  );
}

export default AdminAuditPage;
