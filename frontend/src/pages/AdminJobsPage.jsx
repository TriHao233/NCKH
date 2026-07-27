import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faBan,
  faChevronLeft,
  faChevronRight,
  faFilter,
  faPlay,
  faRotateRight,
  faSearch,
} from '@fortawesome/free-solid-svg-icons';
import { cancelAdminJob, listAdminJobs, retryAdminJob } from '../api/adminJobs';
import '../css/AdminJobsPage.css';

const PAGE_SIZE = 25;

const KIND_LABEL = {
  generation: 'Sinh câu hỏi',
  evaluation: 'Đánh giá',
  document: 'Tài liệu',
};

const STATUS_LABEL = {
  queued: 'Đang chờ',
  processing: 'Đang xử lý',
  failed: 'Thất bại',
  QUEUED: 'Đang chờ',
  PROCESSING: 'Đang xử lý',
  COMPLETED: 'Hoàn tất',
  FAILED: 'Thất bại',
  ERROR: 'Lỗi',
  STALE: 'Cần chạy lại',
  CANCELLED: 'Đã hủy',
};

const STATUS_OPTIONS = [
  { value: 'all', label: 'Tất cả trạng thái' },
  { value: 'active', label: 'Đang chờ / đang xử lý' },
  { value: 'retryable', label: 'Cần xử lý / có thể retry' },
  { value: 'queued', label: 'Generation: đang chờ' },
  { value: 'processing', label: 'Generation: đang xử lý' },
  { value: 'failed', label: 'Generation: thất bại' },
  { value: 'QUEUED', label: 'Job: đang chờ' },
  { value: 'PROCESSING', label: 'Job: đang xử lý' },
  { value: 'FAILED', label: 'Job: thất bại' },
  { value: 'ERROR', label: 'Job: lỗi' },
  { value: 'STALE', label: 'Job: stale' },
  { value: 'COMPLETED', label: 'Job: hoàn tất' },
  { value: 'CANCELLED', label: 'Job: đã hủy' },
];

function jobKey(job) {
  return `${job.kind}:${job.id}`;
}

function compactId(value) {
  if (!value) return 'Chưa có';
  const text = String(value);
  if (text.length <= 12) return text;
  return `${text.slice(0, 6)}...${text.slice(-4)}`;
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

function formatAge(seconds) {
  if (seconds === null || seconds === undefined) return 'Chưa có';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} phút`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} giờ`;
  return `${Math.floor(seconds / 86400)} ngày`;
}

function statusClass(status) {
  const normalized = String(status || 'unknown').toLowerCase();
  if (['failed', 'error', 'cancelled'].includes(normalized)) return 'danger';
  if (normalized === 'stale') return 'warning';
  if (['queued', 'processing'].includes(normalized)) return 'active';
  if (normalized === 'completed') return 'success';
  return 'muted';
}

function entityText(job) {
  const entity = job.entity || {};
  return entity.label || entity.id || 'Chưa gắn đối tượng';
}

function AdminJobsPage() {
  const [jobs, setJobs] = useState([]);
  const [summary, setSummary] = useState({ total: 0, active: 0, failed: 0, long_running: 0 });
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [kindFilter, setKindFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [staleOnly, setStaleOnly] = useState(false);
  const [userIdFilter, setUserIdFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionKey, setActionKey] = useState('');
  const [selectedKey, setSelectedKey] = useState('');

  useEffect(() => {
    const handle = setTimeout(() => {
      setPage(1);
      setSearchTerm(searchInput.trim());
    }, 350);
    return () => clearTimeout(handle);
  }, [searchInput]);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await listAdminJobs({
        page,
        pageSize: PAGE_SIZE,
        kind: kindFilter,
        status: statusFilter,
        staleOnly,
        search: searchTerm,
        userId: userIdFilter.trim(),
        dateFrom,
        dateTo,
      });
      setJobs(result.items || []);
      setSummary(result.summary || { total: 0, active: 0, failed: 0, long_running: 0 });
      setTotal(result.total || 0);
    } catch (err) {
      setError(err.message || 'Không tải được danh sách job');
      setJobs([]);
      setSummary({ total: 0, active: 0, failed: 0, long_running: 0 });
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, kindFilter, page, searchTerm, staleOnly, statusFilter, userIdFilter]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  useEffect(() => {
    if (!jobs.length) {
      setSelectedKey('');
      return;
    }
    if (!selectedKey || !jobs.some((job) => jobKey(job) === selectedKey)) {
      setSelectedKey(jobKey(jobs[0]));
    }
  }, [jobs, selectedKey]);

  const selectedJob = useMemo(
    () => jobs.find((job) => jobKey(job) === selectedKey) || jobs[0] || null,
    [jobs, selectedKey],
  );

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const updateKindFilter = (value) => {
    setKindFilter(value);
    setPage(1);
  };

  const updateStatusFilter = (value) => {
    setStatusFilter(value);
    setPage(1);
  };

  const toggleStaleOnly = () => {
    setStaleOnly((current) => !current);
    setPage(1);
  };

  const updateUserIdFilter = (value) => {
    setUserIdFilter(value);
    setPage(1);
  };

  const updateDateFrom = (value) => {
    setDateFrom(value);
    setPage(1);
  };

  const updateDateTo = (value) => {
    setDateTo(value);
    setPage(1);
  };

  const showAllJobs = () => {
    setStatusFilter('all');
    setStaleOnly(false);
    setPage(1);
  };

  const showActiveJobs = () => {
    setStaleOnly(false);
    updateStatusFilter('active');
  };

  const showRetryableJobs = () => {
    setStaleOnly(false);
    updateStatusFilter('retryable');
  };

  const showLongRunningJobs = () => {
    setStatusFilter('all');
    setStaleOnly(true);
    setPage(1);
  };

  const handleRetry = async (job) => {
    const key = `retry:${jobKey(job)}`;
    setActionKey(key);
    try {
      await retryAdminJob(job.kind, job.id);
      await fetchJobs();
    } catch (err) {
      window.alert(err.message || 'Retry job thất bại');
    } finally {
      setActionKey('');
    }
  };

  const handleCancel = async (job) => {
    if (!window.confirm(`Hủy job ${compactId(job.id)}?`)) return;
    const key = `cancel:${jobKey(job)}`;
    setActionKey(key);
    try {
      await cancelAdminJob(job.kind, job.id);
      await fetchJobs();
    } catch (err) {
      window.alert(err.message || 'Hủy job thất bại');
    } finally {
      setActionKey('');
    }
  };

  return (
    <main className="admin-jobs-page">
      <section className="jobs-header">
        <div>
          <span>Quản trị hệ thống</span>
          <h1>Job hệ thống</h1>
          <p>Theo dõi hàng đợi sinh câu hỏi, đánh giá chất lượng và xử lý tài liệu.</p>
        </div>
        <button type="button" className="jobs-primary-button" onClick={fetchJobs} disabled={loading}>
          <FontAwesomeIcon icon={faRotateRight} />
          <span>{loading ? 'Đang tải' : 'Làm mới'}</span>
        </button>
      </section>

      <section className="jobs-summary" aria-label="Tổng quan job">
        <button type="button" className="summary-tile" onClick={showAllJobs}>
          <b>{summary.total}</b>
          <span>Tổng job</span>
        </button>
        <button type="button" className="summary-tile summary-tile--active" onClick={showActiveJobs}>
          <b>{summary.active}</b>
          <span>Đang chạy</span>
        </button>
        <button type="button" className="summary-tile summary-tile--danger" onClick={showRetryableJobs}>
          <b>{summary.failed}</b>
          <span>Cần xử lý</span>
        </button>
        <button type="button" className="summary-tile summary-tile--warning" onClick={showLongRunningJobs}>
          <b>{summary.long_running}</b>
          <span>Quá lâu</span>
        </button>
      </section>

      <section className="jobs-toolbar" aria-label="Bộ lọc job">
        <div className="toolbar-field toolbar-field--search">
          <label htmlFor="job-search">
            <FontAwesomeIcon icon={faSearch} />
            Tìm kiếm
          </label>
          <input
            id="job-search"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Job ID, đối tượng, lỗi..."
          />
        </div>
        <div className="toolbar-field">
          <label htmlFor="job-kind">
            <FontAwesomeIcon icon={faFilter} />
            Loại
          </label>
          <select id="job-kind" value={kindFilter} onChange={(event) => updateKindFilter(event.target.value)}>
            <option value="all">Tất cả loại job</option>
            <option value="generation">Sinh câu hỏi</option>
            <option value="evaluation">Đánh giá</option>
            <option value="document">Tài liệu</option>
          </select>
        </div>
        <div className="toolbar-field">
          <label htmlFor="job-status">Trạng thái</label>
          <select id="job-status" value={statusFilter} onChange={(event) => updateStatusFilter(event.target.value)}>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
        <div className="toolbar-field">
          <label htmlFor="job-user">Người tạo</label>
          <input
            id="job-user"
            value={userIdFilter}
            onChange={(event) => updateUserIdFilter(event.target.value)}
            placeholder="User ID"
          />
        </div>
        <div className="toolbar-field">
          <label htmlFor="job-date-from">Từ ngày</label>
          <input
            id="job-date-from"
            type="date"
            value={dateFrom}
            max={dateTo || undefined}
            onChange={(event) => updateDateFrom(event.target.value)}
          />
        </div>
        <div className="toolbar-field">
          <label htmlFor="job-date-to">Đến ngày</label>
          <input
            id="job-date-to"
            type="date"
            value={dateTo}
            min={dateFrom || undefined}
            onChange={(event) => updateDateTo(event.target.value)}
          />
        </div>
        <label className="jobs-toggle">
          <input type="checkbox" checked={staleOnly} onChange={toggleStaleOnly} />
          Chỉ job quá lâu
        </label>
      </section>

      {error && <p className="jobs-error">{error}</p>}

      <section className="jobs-layout">
        <div className="jobs-table-panel">
          <div className="jobs-table-header">
            <div>
              <h2>Danh sách job</h2>
              <span>{total} kết quả</span>
            </div>
          </div>
          <div className="jobs-table-wrap">
            <table className="jobs-table">
              <thead>
                <tr>
                  <th>Loại</th>
                  <th>Trạng thái</th>
                  <th>Đối tượng</th>
                  <th>Người tạo</th>
                  <th>Cập nhật</th>
                  <th>Lỗi</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => {
                  const key = jobKey(job);
                  return (
                    <tr
                      key={key}
                      className={selectedKey === key ? 'is-selected' : ''}
                      onClick={() => setSelectedKey(key)}
                    >
                      <td>
                        <strong>{KIND_LABEL[job.kind] || job.kind}</strong>
                        <small>{compactId(job.id)}</small>
                      </td>
                      <td>
                        <span className={`status-pill status-pill--${statusClass(job.status)}`}>
                          {STATUS_LABEL[job.status] || job.status || 'Chưa rõ'}
                        </span>
                        {job.is_long_running && <small className="long-running">Quá ngưỡng</small>}
                      </td>
                      <td>
                        <span className="entity-text">{entityText(job)}</span>
                        <small>{job.entity?.type || 'entity'} {compactId(job.entity?.id)}</small>
                      </td>
                      <td>{compactId(job.actor_user_id)}</td>
                      <td>
                        <span>{formatDateTime(job.updated_at || job.finished_at || job.started_at || job.queued_at)}</span>
                        <small>{formatAge(job.age_seconds)}</small>
                      </td>
                      <td>
                        <span className="error-cell">{job.error_message || 'Không có'}</span>
                      </td>
                      <td>
                        <div className="row-actions">
                          <button
                            type="button"
                            title="Retry job"
                            disabled={!job.can_retry || Boolean(actionKey)}
                            onClick={(event) => {
                              event.stopPropagation();
                              handleRetry(job);
                            }}
                          >
                            <FontAwesomeIcon icon={faPlay} />
                          </button>
                          <button
                            type="button"
                            title="Hủy job"
                            disabled={!job.can_cancel || Boolean(actionKey)}
                            onClick={(event) => {
                              event.stopPropagation();
                              handleCancel(job);
                            }}
                          >
                            <FontAwesomeIcon icon={faBan} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!loading && jobs.length === 0 && (
              <p className="jobs-empty">Không có job phù hợp với bộ lọc hiện tại.</p>
            )}
            {loading && (
              <p className="jobs-empty">Đang tải danh sách job...</p>
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

        <aside className="job-detail-panel" aria-label="Chi tiết job">
          {selectedJob ? (
            <>
              <div className="job-detail-header">
                <span>{KIND_LABEL[selectedJob.kind] || selectedJob.kind}</span>
                <h2>{compactId(selectedJob.id)}</h2>
              </div>
              <dl className="job-detail-list">
                <div>
                  <dt>Trạng thái</dt>
                  <dd>{STATUS_LABEL[selectedJob.status] || selectedJob.status || 'Chưa rõ'}</dd>
                </div>
                <div>
                  <dt>Đối tượng</dt>
                  <dd>{entityText(selectedJob)}</dd>
                </div>
                <div>
                  <dt>Queued</dt>
                  <dd>{formatDateTime(selectedJob.queued_at)}</dd>
                </div>
                <div>
                  <dt>Started</dt>
                  <dd>{formatDateTime(selectedJob.started_at)}</dd>
                </div>
                <div>
                  <dt>Finished</dt>
                  <dd>{formatDateTime(selectedJob.finished_at)}</dd>
                </div>
                <div>
                  <dt>Tiến độ</dt>
                  <dd>{selectedJob.progress === null || selectedJob.progress === undefined ? 'Chưa có' : `${selectedJob.progress}%`}</dd>
                </div>
              </dl>
              {selectedJob.error_message && (
                <div className="job-detail-error">
                  <span>Lỗi gần nhất</span>
                  <p>{selectedJob.error_message}</p>
                </div>
              )}
              <div className="job-detail-json">
                <span>Snapshot</span>
                <pre>{JSON.stringify(selectedJob.snapshot || {}, null, 2)}</pre>
              </div>
            </>
          ) : (
            <p className="job-detail-empty">Chọn một job để xem chi tiết.</p>
          )}
        </aside>
      </section>
    </main>
  );
}

export default AdminJobsPage;
