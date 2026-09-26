import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faBan,
  faCircleCheck,
  faFileCsv,
  faFileExcel,
  faMagnifyingGlass,
  faPlay,
  faRotateRight,
} from '@fortawesome/free-solid-svg-icons';
import { cancelAdminJob, listAdminJobs, retryAdminJob } from '../api/adminJobs';
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
import { useConfirm, useFlash } from '../components/workspace/Dialog';
import { FilterChips, FilterToggle } from '../components/workspace/Filters';
import { Pagination, Tabs } from '../components/workspace/Navigation';
import { useReviewLookups, userName } from '../features/review/reviewData';
import {
  JOB_KIND_LABEL,
  JOB_TYPE_LABEL,
  compactId,
  formatAge,
  jobStatusLabel,
  jobStatusTone,
} from '../features/admin/adminLabels';
import { formatDateTime, refId } from '../features/review/reviewModel';
import '../css/workspace.css';
import '../css/AdminPages.css';

const PAGE_SIZE = 25;
const EXPORT_PAGE_SIZE = 100;

const TYPE_TABS = [
  { value: 'all', label: 'Tất cả' },
  { value: 'document', label: 'Tài liệu (OCR/Chunk)' },
  { value: 'generation', label: 'Sinh câu hỏi' },
  { value: 'evaluation', label: 'Đánh giá AI' },
];

const STATUS_OPTIONS = [
  { value: 'all', label: 'Mọi trạng thái' },
  { value: 'active', label: 'Đang chờ hoặc đang chạy' },
  { value: 'retryable', label: 'Lỗi, có thể chạy lại' },
  { value: 'COMPLETED', label: 'Hoàn tất' },
  { value: 'FAILED', label: 'Thất bại' },
  { value: 'ERROR', label: 'Lỗi' },
  { value: 'STALE', label: 'Cần chạy lại' },
  { value: 'BLOCKED', label: 'Thiếu bằng chứng' },
  { value: 'CANCELLED', label: 'Đã huỷ' },
];

const QUERY_STATUS = { failed: 'retryable', error: 'retryable' };

function jobKey(job) {
  return `${job.kind}:${job.id}`;
}

function entityText(job) {
  return job.entity?.label || compactId(job.entity?.id) || 'Chưa gắn đối tượng';
}

function durationSeconds(job) {
  const start = new Date(job.started_at || job.queued_at).getTime();
  const end = job.finished_at ? new Date(job.finished_at).getTime() : Date.now();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  return Math.round((end - start) / 1000);
}

const EXPORT_COLUMNS = [
  { header: 'Mã tác vụ', value: (job) => job.id },
  { header: 'Nhóm', value: (job) => JOB_KIND_LABEL[job.kind] || job.kind || '' },
  { header: 'Loại', value: (job) => JOB_TYPE_LABEL[job.type] || job.type || '' },
  { header: 'Trạng thái', value: (job) => jobStatusLabel(job.status) },
  { header: 'Đối tượng', value: entityText },
  { header: 'Mã đối tượng', value: (job) => job.entity?.id || '' },
  { header: 'Người tạo', value: (job) => job.actor_user_name || job.actor_user_id || '' },
  { header: 'Vào hàng đợi', value: (job) => job.queued_at || '' },
  { header: 'Bắt đầu', value: (job) => job.started_at || '' },
  { header: 'Hoàn tất', value: (job) => job.finished_at || '' },
  { header: 'Thời lượng (giây)', value: (job) => durationSeconds(job) ?? '' },
  { header: 'Quá ngưỡng', value: (job) => (job.is_long_running ? 'có' : 'không') },
  { header: 'Lỗi', value: (job) => job.error_message || '' },
  { header: 'Dữ liệu trạng thái', value: (job) => job.snapshot || {} },
];

function AdminJobsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const lookups = useReviewLookups();
  const { flash, show: showFlash, clear: clearFlash } = useFlash();
  const [confirm, confirmDialog] = useConfirm();

  const typeParam = searchParams.get('type') || searchParams.get('kind') || 'all';
  const kind = TYPE_TABS.some((item) => item.value === typeParam) ? typeParam : 'all';
  const statusParam = QUERY_STATUS[searchParams.get('status')] || searchParams.get('status') || 'all';
  const status = STATUS_OPTIONS.some((item) => item.value === statusParam) ? statusParam : 'all';
  const staleOnly = searchParams.get('stale_only') === 'true';

  const [jobs, setJobs] = useState([]);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState({});
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [userId, setUserId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [detailKey, setDetailKey] = useState('');

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setSearchTerm(searchInput.trim());
      setPage(1);
    }, 350);
    return () => window.clearTimeout(handle);
  }, [searchInput]);

  const setParam = (patch) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(patch).forEach(([key, value]) => {
      if (!value || value === 'all' || value === false) next.delete(key);
      else next.set(key, String(value));
    });
    next.delete('kind');
    setSearchParams(next, { replace: true });
    setPage(1);
  };

  const baseQuery = useCallback((extra) => ({
    status,
    staleOnly,
    search: searchTerm,
    userId,
    dateFrom,
    dateTo,
    ...extra,
  }), [status, staleOnly, searchTerm, userId, dateFrom, dateTo]);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [result, ...tabResults] = await Promise.all([
        listAdminJobs(baseQuery({ kind, page, pageSize: PAGE_SIZE })),
        ...TYPE_TABS.map((item) => listAdminJobs(baseQuery({ kind: item.value, page: 1, pageSize: 1 })).catch(() => null)),
      ]);
      setJobs(result.items || []);
      setTotal(result.total || 0);
      setCounts(Object.fromEntries(TYPE_TABS.map((item, index) => [item.value, tabResults[index]?.total])));
    } catch (err) {
      setError(err.message || 'Không tải được danh sách tác vụ.');
      setJobs([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [baseQuery, kind, page]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // Còn tác vụ đang chạy thì tự làm mới mỗi 10 giây.
  useEffect(() => {
    if (!jobs.some((job) => ['queued', 'processing'].includes(String(job.status).toLowerCase()))) return undefined;
    const timer = window.setInterval(fetchJobs, 10000);
    return () => window.clearInterval(timer);
  }, [jobs, fetchJobs]);

  const people = useMemo(() => {
    const map = new Map();
    [...lookups.teachers, ...lookups.reviewers].forEach((person) => map.set(refId(person), person));
    return Array.from(map.values());
  }, [lookups]);

  const detail = jobs.find((job) => jobKey(job) === detailKey) || null;

  const retry = async (job) => {
    setBusy(`retry:${jobKey(job)}`);
    clearFlash();
    try {
      await retryAdminJob(job.kind, job.id);
      showFlash('success', 'Đã đưa tác vụ vào hàng đợi chạy lại.');
      await fetchJobs();
    } catch (err) {
      showFlash('error', err.message || 'Chạy lại thất bại.');
    } finally {
      setBusy('');
    }
  };

  const cancel = async (job) => {
    const accepted = await confirm({
      title: 'Huỷ tác vụ',
      description: `${JOB_TYPE_LABEL[job.type] || JOB_KIND_LABEL[job.kind] || 'Tác vụ'} cho "${entityText(job)}" sẽ dừng lại.`,
      confirmLabel: 'Huỷ tác vụ',
      cancelLabel: 'Giữ lại',
      tone: 'danger',
    });
    if (!accepted) return;
    setBusy(`cancel:${jobKey(job)}`);
    clearFlash();
    try {
      await cancelAdminJob(job.kind, job.id);
      showFlash('success', 'Đã huỷ tác vụ.');
      await fetchJobs();
    } catch (err) {
      showFlash('error', err.message || 'Huỷ thất bại.');
    } finally {
      setBusy('');
    }
  };

  const exportJobs = async (format) => {
    setBusy(`export:${format}`);
    clearFlash();
    try {
      const first = await listAdminJobs(baseQuery({ kind, page: 1, pageSize: EXPORT_PAGE_SIZE }));
      const rows = [...(first.items || [])];
      for (let next = 2; rows.length < (first.total || 0); next += 1) {
        const result = await listAdminJobs(baseQuery({ kind, page: next, pageSize: EXPORT_PAGE_SIZE }));
        if (!(result.items || []).length) break;
        rows.push(...result.items);
      }
      if (format === 'csv') downloadCsv(timestampedCsvFilename('tac-vu'), rowsToCsv(EXPORT_COLUMNS, rows));
      else downloadXlsx(timestampedXlsxFilename('tac-vu'), EXPORT_COLUMNS, rows, 'Tac vu');
    } catch (err) {
      showFlash('error', err.message || 'Xuất tệp thất bại.');
    } finally {
      setBusy('');
    }
  };

  const chips = [
    staleOnly && { key: 'stale', label: 'Chỉ tác vụ chạy quá lâu', onRemove: () => setParam({ stale_only: false }) },
    userId && { key: 'user', label: `Người tạo: ${userName(people.find((person) => refId(person) === userId), '...')}`, onRemove: () => { setUserId(''); setPage(1); } },
    dateFrom && { key: 'from', label: `Từ ${dateFrom}`, onRemove: () => { setDateFrom(''); setPage(1); } },
    dateTo && { key: 'to', label: `Đến ${dateTo}`, onRemove: () => { setDateTo(''); setPage(1); } },
  ].filter(Boolean);

  return (
    <main className="ws-page jobs-workspace-page">
      <WorkspaceHero
        badge="Vận hành hệ thống"
        title="Tác vụ"
        description="Theo dõi tác vụ OCR, cắt đoạn, sinh và đánh giá câu hỏi; chạy lại hoặc huỷ tác vụ bị lỗi hay treo."
        actions={(
          <>
            <MoreMenu
              items={[
                { key: 'csv', label: 'Xuất CSV', icon: faFileCsv, disabled: Boolean(busy) || total === 0, onClick: () => exportJobs('csv') },
                { key: 'xlsx', label: 'Xuất Excel', icon: faFileExcel, disabled: Boolean(busy) || total === 0, onClick: () => exportJobs('xlsx') },
              ]}
            />
            <button type="button" className="btn btn--outline" onClick={fetchJobs} disabled={loading}>
              <FontAwesomeIcon icon={faRotateRight} />
              Làm mới
            </button>
          </>
        )}
      >
        <Tabs label="Loại tác vụ" value={kind} onChange={(value) => setParam({ type: value })} items={TYPE_TABS.map((item) => ({ ...item, count: counts[item.value] }))} />
      </WorkspaceHero>

      <section className="ws-body">
        <div className="container ws-main">
          {flash && <Notice tone={flash.tone} onDismiss={clearFlash}>{flash.message}</Notice>}
          <section className="ws-card">
            <div className="ws-card-head">
              <div className="ws-card-title">
                <h2>{TYPE_TABS.find((item) => item.value === kind)?.label}</h2>
                <span className="ws-list-count tabular">{loading ? 'Đang tải...' : `${jobs.length} / ${total} tác vụ đang hiển thị`}</span>
              </div>
            </div>
            <div className="ws-toolbar">
              <label className="ws-search">
                <span className="ws-sr-only">Tìm tác vụ</span>
                <FontAwesomeIcon icon={faMagnifyingGlass} />
                <input className="ws-input" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Mã tác vụ, đối tượng hoặc nội dung lỗi" />
              </label>
              <select className="ws-select" aria-label="Trạng thái" value={status} onChange={(event) => setParam({ status: event.target.value })}>
                {STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <FilterToggle open={filtersOpen} count={chips.length} onToggle={() => setFiltersOpen((value) => !value)} />
            </div>
            {filtersOpen && (
              <div className="ws-filter-panel">
                <label className="ws-field">
                  <span>Người tạo</span>
                  <select className="ws-select" value={userId} onChange={(event) => { setUserId(event.target.value); setPage(1); }}>
                    <option value="">Tất cả</option>
                    {people.map((person) => <option key={refId(person)} value={refId(person)}>{userName(person)}</option>)}
                  </select>
                </label>
                <label className="ws-field">
                  <span>Từ ngày</span>
                  <input type="date" className="ws-input" value={dateFrom} max={dateTo || undefined} onChange={(event) => { setDateFrom(event.target.value); setPage(1); }} />
                </label>
                <label className="ws-field">
                  <span>Đến ngày</span>
                  <input type="date" className="ws-input" value={dateTo} min={dateFrom || undefined} onChange={(event) => { setDateTo(event.target.value); setPage(1); }} />
                </label>
                <label className="ws-check" style={{ alignSelf: 'end', paddingBottom: 10 }}>
                  <input type="checkbox" checked={staleOnly} onChange={(event) => setParam({ stale_only: event.target.checked })} />
                  Chỉ tác vụ chạy quá lâu
                </label>
              </div>
            )}
            <FilterChips
              chips={chips}
              onClearAll={() => {
                setUserId('');
                setDateFrom('');
                setDateTo('');
                setParam({ stale_only: false });
              }}
            />

            <div style={{ marginTop: 14 }}>
              {loading && jobs.length === 0 ? (
                <SkeletonRows rows={6} lines={2} />
              ) : error ? (
                <ErrorState message={error} onRetry={fetchJobs} />
              ) : jobs.length === 0 ? (
                <EmptyState icon={faCircleCheck} title="Không có tác vụ phù hợp" description="Thử đổi loại, trạng thái hoặc bỏ bớt bộ lọc." />
              ) : (
                <div className="ws-table-wrap">
                  <table className="ws-table">
                    <thead>
                      <tr>
                        <th>Loại</th>
                        <th>Đối tượng</th>
                        <th>Người tạo</th>
                        <th>Trạng thái</th>
                        <th className="ws-num">Thời lượng</th>
                        <th>Thời điểm</th>
                        <th aria-label="Thao tác" />
                      </tr>
                    </thead>
                    <tbody>
                      {jobs.map((job) => {
                        const tone = jobStatusTone(job.status);
                        const duration = durationSeconds(job);
                        return (
                          <tr key={jobKey(job)} data-clickable="true" onClick={() => setDetailKey(jobKey(job))}>
                            <td>
                              <strong>{JOB_TYPE_LABEL[job.type] || JOB_KIND_LABEL[job.kind] || job.type}</strong>
                              <small>{JOB_KIND_LABEL[job.kind] || job.kind}</small>
                            </td>
                            <td><span className="ws-cell-clip">{entityText(job)}</span></td>
                            <td>{job.actor_user_name || 'Hệ thống'}</td>
                            <td>
                              <span className={`ws-pill ${tone ? `ws-pill--${tone}` : ''}`}>{jobStatusLabel(job.status)}</span>
                              {job.error_message && <small className="ws-clip-1" style={{ maxWidth: 220 }} title={job.error_message}>{job.error_message}</small>}
                            </td>
                            <td className="ws-num">
                              <span className={job.is_long_running ? 'ws-text-warn' : ''}>{duration === null ? '--' : formatAge(duration)}</span>
                            </td>
                            <td>{formatDateTime(job.updated_at || job.finished_at || job.started_at || job.queued_at)}</td>
                            <td onClick={(event) => event.stopPropagation()}>
                              <MoreMenu
                                variant="icon"
                                label="Thao tác với tác vụ"
                                items={[
                                  { key: 'detail', label: 'Xem chi tiết', onClick: () => setDetailKey(jobKey(job)) },
                                  { key: 'retry', label: 'Chạy lại', icon: faPlay, disabled: !job.can_retry || Boolean(busy), title: job.can_retry ? undefined : 'Tác vụ này không chạy lại được', onClick: () => retry(job) },
                                  { key: 'cancel', label: 'Huỷ', icon: faBan, danger: true, disabled: !job.can_cancel || Boolean(busy), title: job.can_cancel ? undefined : 'Chỉ huỷ được tác vụ đang chờ hoặc đang chạy', onClick: () => cancel(job) },
                                ]}
                              />
                            </td>
                          </tr>
                        );
                      })}
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
        title={detail ? (JOB_TYPE_LABEL[detail.type] || JOB_KIND_LABEL[detail.kind] || detail.type) : ''}
        subtitle={detail?.id}
        onClose={() => setDetailKey('')}
        footer={detail && (detail.can_retry || detail.can_cancel) ? (
          <>
            {detail.can_cancel && <button type="button" className="btn btn--danger" disabled={Boolean(busy)} onClick={() => cancel(detail)}>Huỷ</button>}
            {detail.can_retry && (
              <button type="button" className="btn btn--primary" disabled={Boolean(busy)} onClick={() => retry(detail)}>
                {busy === `retry:${jobKey(detail)}` ? 'Đang gửi...' : 'Chạy lại'}
              </button>
            )}
          </>
        ) : null}
      >
        {detail && (
          <>
            <span className={`ws-pill ${jobStatusTone(detail.status) ? `ws-pill--${jobStatusTone(detail.status)}` : ''}`} style={{ alignSelf: 'flex-start' }}>
              {jobStatusLabel(detail.status)}
            </span>
            <dl className="ws-kv">
              <div><dt>Đối tượng</dt><dd>{entityText(detail)}</dd></div>
              <div><dt>Người tạo</dt><dd>{detail.actor_user_name || 'Hệ thống'}</dd></div>
              <div><dt>Vào hàng đợi</dt><dd>{formatDateTime(detail.queued_at)}</dd></div>
              <div><dt>Bắt đầu</dt><dd>{formatDateTime(detail.started_at)}</dd></div>
              <div><dt>Hoàn tất</dt><dd>{formatDateTime(detail.finished_at)}</dd></div>
              <div><dt>Tiến độ</dt><dd>{detail.progress === null || detail.progress === undefined ? '--' : `${detail.progress}%`}</dd></div>
            </dl>
            {detail.error_message && (
              <div>
                <h4 className="ws-subhead">Lỗi gần nhất</h4>
                <div className="ad-error-box">{detail.error_message}</div>
              </div>
            )}
            <details className="ws-fold">
              <summary>Dữ liệu trạng thái</summary>
              <div className="ws-fold__body"><pre className="ws-pre">{JSON.stringify(detail.snapshot || {}, null, 2)}</pre></div>
            </details>
          </>
        )}
      </Drawer>
      {confirmDialog}
    </main>
  );
}

export default AdminJobsPage;
