import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faClockRotateLeft, faFileCsv, faFileExcel, faMagnifyingGlass, faRotateRight } from '@fortawesome/free-solid-svg-icons';
import { listAdminAuditLogs } from '../api/adminAudit';
import {
  downloadCsv,
  downloadXlsx,
  rowsToCsv,
  timestampedCsvFilename,
  timestampedXlsxFilename,
} from '../utils/csvExport';
import WorkspaceHero from '../components/workspace/WorkspaceHero';
import Drawer from '../components/workspace/Drawer';
import MoreMenu from '../components/workspace/MoreMenu';
import { EmptyState, ErrorState, Notice, SkeletonRows } from '../components/workspace/Feedback';
import { useFlash } from '../components/workspace/Dialog';
import { FilterChips, FilterToggle } from '../components/workspace/Filters';
import { Pagination } from '../components/workspace/Navigation';
import { useReviewLookups, userName } from '../features/review/reviewData';
import {
  AUDIT_ACTION_LABEL,
  AUDIT_ENTITY_LABEL,
  auditActionLabel,
  auditEntityLabel,
  compactId,
} from '../features/admin/adminLabels';
import { formatDateTime, refId } from '../features/review/reviewModel';
import '../css/workspace.css';
import '../css/AdminPages.css';

const PAGE_SIZE = 25;
const EXPORT_PAGE_SIZE = 100;

function actorText(log) {
  const actor = log.actor || {};
  return actor.user_name || (actor.user_id ? compactId(actor.user_id) : (actor.service_name || 'Hệ thống'));
}

function entityName(log) {
  return log.entity?.label || compactId(log.entity?.id);
}

function entityLink(entity = {}) {
  if (!entity.id) return null;
  if (['QUESTION', 'question'].includes(entity.type)) return `/kiem-duyet/${entity.id}`;
  if (entity.type === 'user') return '/quan-ly-nguoi-dung';
  if (entity.type === 'document') return '/quan-ly-tai-lieu';
  if (['moodle_target', 'moodle_publication'].includes(entity.type)) return '/quan-ly-moodle';
  if (['generation', 'evaluation'].includes(entity.type)) return `/quan-ly-job?type=${entity.type}`;
  return null;
}

function stringify(value) {
  if (value === null || value === undefined || value === '') return '(trống)';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

function hasContent(value) {
  if (!value) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value).length > 0;
  return true;
}

/** Tách before/after thành danh sách trường thay đổi để làm nổi bật. */
function changedFields(before = {}, after = {}) {
  if (typeof before !== 'object' || typeof after !== 'object' || !before || !after) return [];
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  return [...keys]
    .filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key]))
    .map((key) => ({ path: key, old_value: before[key], new_value: after[key] }));
}

const EXPORT_COLUMNS = [
  { header: 'Mã nhật ký', value: (log) => log.id },
  { header: 'Thời gian', value: (log) => log.created_at || '' },
  { header: 'Người thực hiện', value: actorText },
  { header: 'Hành động', value: (log) => auditActionLabel(log.action) },
  { header: 'Mã hành động', value: (log) => log.action || '' },
  { header: 'Loại đối tượng', value: (log) => auditEntityLabel(log.entity?.type) },
  { header: 'Đối tượng', value: entityName },
  { header: 'Mã đối tượng', value: (log) => log.entity?.id || '' },
  { header: 'Trước', value: (log) => log.before || {} },
  { header: 'Sau', value: (log) => log.after || {} },
  { header: 'Thay đổi', value: (log) => log.changes || [] },
  { header: 'Thông tin thêm', value: (log) => log.metadata || {} },
];

function AdminAuditPage() {
  const [searchParams] = useSearchParams();
  const lookups = useReviewLookups();
  const { flash, show: showFlash, clear: clearFlash } = useFlash();
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [action, setAction] = useState('all');
  const [entityType, setEntityType] = useState('all');
  const [actorUserId, setActorUserId] = useState('');
  const [entityId, setEntityId] = useState(searchParams.get('entity_id') || '');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(Boolean(searchParams.get('entity_id')));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setSearchTerm(searchInput.trim());
      setPage(1);
    }, 350);
    return () => window.clearTimeout(handle);
  }, [searchInput]);

  const buildQuery = useCallback((nextPage, pageSize) => ({
    page: nextPage,
    pageSize,
    search: searchTerm,
    action,
    entityType,
    actorUserId,
    entityId: entityId.trim(),
    dateFrom: dateFrom ? `${dateFrom}T00:00:00` : '',
    dateTo: dateTo ? `${dateTo}T23:59:59` : '',
  }), [action, actorUserId, dateFrom, dateTo, entityId, entityType, searchTerm]);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await listAdminAuditLogs(buildQuery(page, PAGE_SIZE));
      setLogs(result.items || []);
      setTotal(result.total || 0);
    } catch (err) {
      setError(err.message || 'Không tải được nhật ký.');
      setLogs([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [buildQuery, page]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const people = useMemo(() => {
    const map = new Map();
    [...lookups.teachers, ...lookups.reviewers].forEach((person) => map.set(refId(person), person));
    return Array.from(map.values());
  }, [lookups]);

  const reset = (setter) => (value) => {
    setter(value);
    setPage(1);
  };

  const exportLogs = async (format) => {
    setBusy(format);
    clearFlash();
    try {
      const first = await listAdminAuditLogs(buildQuery(1, EXPORT_PAGE_SIZE));
      const rows = [...(first.items || [])];
      for (let next = 2; rows.length < (first.total || 0); next += 1) {
        const result = await listAdminAuditLogs(buildQuery(next, EXPORT_PAGE_SIZE));
        if (!(result.items || []).length) break;
        rows.push(...result.items);
      }
      if (format === 'csv') downloadCsv(timestampedCsvFilename('nhat-ky'), rowsToCsv(EXPORT_COLUMNS, rows));
      else downloadXlsx(timestampedXlsxFilename('nhat-ky'), EXPORT_COLUMNS, rows, 'Nhat ky');
    } catch (err) {
      showFlash('error', err.message || 'Xuất tệp thất bại.');
    } finally {
      setBusy('');
    }
  };

  const chips = [
    entityType !== 'all' && { key: 'entity', label: `Đối tượng: ${auditEntityLabel(entityType)}`, onRemove: () => reset(setEntityType)('all') },
    actorUserId && { key: 'actor', label: `Người thực hiện: ${userName(people.find((person) => refId(person) === actorUserId), '...')}`, onRemove: () => reset(setActorUserId)('') },
    entityId && { key: 'id', label: `Mã: ${compactId(entityId)}`, onRemove: () => reset(setEntityId)('') },
    dateFrom && { key: 'from', label: `Từ ${dateFrom}`, onRemove: () => reset(setDateFrom)('') },
    dateTo && { key: 'to', label: `Đến ${dateTo}`, onRemove: () => reset(setDateTo)('') },
  ].filter(Boolean);

  const detailChanges = detail
    ? (Array.isArray(detail.changes) && detail.changes.length ? detail.changes : changedFields(detail.before, detail.after))
    : [];
  const detailLink = detail ? entityLink(detail.entity) : null;

  return (
    <main className="ws-page audit-workspace-page">
      <WorkspaceHero
        badge="Vận hành hệ thống"
        title="Nhật ký"
        description="Tra cứu ai đã làm gì, khi nào, trên đối tượng nào: duyệt câu hỏi, đổi quyền, cấu hình Moodle, chạy lại tác vụ."
        actions={(
          <>
            <MoreMenu
              items={[
                { key: 'csv', label: 'Xuất CSV', icon: faFileCsv, disabled: Boolean(busy) || total === 0, onClick: () => exportLogs('csv') },
                { key: 'xlsx', label: 'Xuất Excel', icon: faFileExcel, disabled: Boolean(busy) || total === 0, onClick: () => exportLogs('xlsx') },
              ]}
            />
            <button type="button" className="btn btn--outline" onClick={fetchLogs} disabled={loading}>
              <FontAwesomeIcon icon={faRotateRight} />
              Làm mới
            </button>
          </>
        )}
      />

      <section className="ws-body">
        <div className="container ws-main">
          {flash && <Notice tone={flash.tone} onDismiss={clearFlash}>{flash.message}</Notice>}
          <section className="ws-card">
            <div className="ws-card-head">
              <div className="ws-card-title">
                <h2>Hoạt động</h2>
                <span className="ws-list-count tabular">{loading ? 'Đang tải...' : `${logs.length} / ${total} bản ghi đang hiển thị`}</span>
              </div>
            </div>
            <div className="ws-toolbar">
              <label className="ws-search">
                <span className="ws-sr-only">Tìm nhật ký</span>
                <FontAwesomeIcon icon={faMagnifyingGlass} />
                <input className="ws-input" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Hành động, người thực hiện hoặc đối tượng" />
              </label>
              <select className="ws-select" aria-label="Hành động" value={action} onChange={(event) => reset(setAction)(event.target.value)}>
                <option value="all">Mọi hành động</option>
                {Object.entries(AUDIT_ACTION_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <FilterToggle open={filtersOpen} count={chips.length} onToggle={() => setFiltersOpen((value) => !value)} />
            </div>
            {filtersOpen && (
              <div className="ws-filter-panel">
                <label className="ws-field">
                  <span>Người thực hiện</span>
                  <select className="ws-select" value={actorUserId} onChange={(event) => reset(setActorUserId)(event.target.value)}>
                    <option value="">Tất cả</option>
                    {people.map((person) => <option key={refId(person)} value={refId(person)}>{userName(person)}</option>)}
                  </select>
                </label>
                <label className="ws-field">
                  <span>Loại đối tượng</span>
                  <select className="ws-select" value={entityType} onChange={(event) => reset(setEntityType)(event.target.value)}>
                    <option value="all">Tất cả</option>
                    {Object.entries(AUDIT_ENTITY_LABEL).filter(([value]) => value !== 'question').map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
                <label className="ws-field">
                  <span>Mã đối tượng</span>
                  <input className="ws-input" value={entityId} onChange={(event) => reset(setEntityId)(event.target.value)} placeholder="Ví dụ: mã câu hỏi" />
                </label>
                <label className="ws-field">
                  <span>Từ ngày</span>
                  <input type="date" className="ws-input" value={dateFrom} max={dateTo || undefined} onChange={(event) => reset(setDateFrom)(event.target.value)} />
                </label>
                <label className="ws-field">
                  <span>Đến ngày</span>
                  <input type="date" className="ws-input" value={dateTo} min={dateFrom || undefined} onChange={(event) => reset(setDateTo)(event.target.value)} />
                </label>
              </div>
            )}
            <FilterChips chips={chips} onClearAll={() => { setEntityType('all'); setActorUserId(''); setEntityId(''); setDateFrom(''); setDateTo(''); setPage(1); }} />

            <div style={{ marginTop: 14 }}>
              {loading && logs.length === 0 ? (
                <SkeletonRows rows={6} lines={1} />
              ) : error ? (
                <ErrorState message={error} onRetry={fetchLogs} />
              ) : logs.length === 0 ? (
                <EmptyState icon={faClockRotateLeft} title="Không có bản ghi phù hợp" description="Thử mở rộng khoảng ngày hoặc bỏ bớt bộ lọc." />
              ) : (
                <div className="ws-table-wrap">
                  <table className="ws-table">
                    <tbody>
                      {logs.map((log) => (
                        <tr key={log.id} data-clickable="true" onClick={() => setDetail(log)}>
                          <td className="ad-sentence">
                            <b>{actorText(log)}</b> đã {auditActionLabel(log.action).toLowerCase()}
                            {' '}
                            <span className="ws-muted">{auditEntityLabel(log.entity?.type).toLowerCase()}</span>
                            {' '}
                            <span className="ws-code">{entityName(log)}</span>
                          </td>
                          <td style={{ whiteSpace: 'nowrap', textAlign: 'right' }} className="ws-muted">{formatDateTime(log.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <Pagination page={page} pageSize={PAGE_SIZE} total={total} loading={loading} onChange={setPage} />
            </div>
          </section>
        </div>
      </section>

      <Drawer
        open={Boolean(detail)}
        wide
        title={detail ? auditActionLabel(detail.action) : ''}
        subtitle={detail ? `${actorText(detail)}, ${formatDateTime(detail.created_at)}` : ''}
        onClose={() => setDetail(null)}
      >
        {detail && (
          <>
            <dl className="ws-kv">
              <div><dt>Đối tượng</dt><dd>{auditEntityLabel(detail.entity?.type)}</dd></div>
              <div>
                <dt>Mã</dt>
                <dd>{detailLink ? <Link to={detailLink} className="ws-code">{entityName(detail)}</Link> : <span className="ws-code">{entityName(detail)}</span>}</dd>
              </div>
              <div><dt>Mã hành động</dt><dd className="ws-code">{detail.action}</dd></div>
              {detail.entity?.version_id && <div><dt>Phiên bản</dt><dd className="ws-code">{compactId(detail.entity.version_id)}</dd></div>}
            </dl>
            <div>
              <h4 className="ws-subhead">Các trường thay đổi</h4>
              {detailChanges.length === 0 ? (
                <p className="ws-hint" style={{ margin: 0 }}>Không ghi nhận thay đổi dữ liệu.</p>
              ) : detailChanges.map((change, index) => (
                <div className="ad-change" key={`${change.path}-${index}`}>
                  <code>{change.path || 'giá trị'}</code>
                  <div className="ad-change-values">
                    <pre className="is-old" aria-label="Trước">{stringify(change.old_value)}</pre>
                    <pre className="is-new" aria-label="Sau">{stringify(change.new_value)}</pre>
                  </div>
                </div>
              ))}
            </div>
            {hasContent(detail.metadata) && (
              <div>
                <h4 className="ws-subhead">Dữ liệu bổ sung</h4>
                <pre className="ws-pre">{stringify(detail.metadata)}</pre>
              </div>
            )}
          </>
        )}
      </Drawer>
    </main>
  );
}

export default AdminAuditPage;
