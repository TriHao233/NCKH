import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faBookOpen,
  faClipboardCheck,
  faDatabase,
  faPlugCircleCheck,
  faRotateRight,
  faServer,
  faTriangleExclamation,
  faUsers,
} from '@fortawesome/free-solid-svg-icons';
import { getAdminOverview } from '../api/adminOverview';
import '../css/AdminOverviewPage.css';

function formatNumber(value) {
  return new Intl.NumberFormat('vi-VN').format(value || 0);
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

function compactId(value) {
  if (!value) return 'Chưa có';
  const text = String(value);
  if (text.length <= 12) return text;
  return `${text.slice(0, 6)}...${text.slice(-4)}`;
}

function AdminOverviewPage() {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setOverview(await getAdminOverview());
    } catch (err) {
      setError(err.message || 'Không tải được tổng quan hệ thống');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const stats = useMemo(() => {
    const users = overview?.users || {};
    const questions = overview?.questions || {};
    const documents = overview?.documents || {};
    const jobs = overview?.jobs || {};
    const moodle = overview?.moodle || {};
    return [
      {
        key: 'users',
        label: 'Người dùng active',
        value: users.active,
        detail: `${formatNumber(users.teachers)} Teacher · ${formatNumber(users.reviewers)} Reviewer`,
        icon: faUsers,
      },
      {
        key: 'questions',
        label: 'Câu hỏi active',
        value: questions.total,
        detail: `${formatNumber(questions.pending)} chờ duyệt · ${formatNumber(questions.approved)} đã duyệt`,
        icon: faBookOpen,
      },
      {
        key: 'documents',
        label: 'Tài liệu',
        value: documents.total,
        detail: `${formatNumber(documents.processing)} đang xử lý · ${formatNumber(documents.failed)} lỗi`,
        icon: faDatabase,
      },
      {
        key: 'jobs',
        label: 'Job cần xử lý',
        value: jobs.failed,
        detail: `${formatNumber(jobs.active)} đang chạy · ${formatNumber(jobs.long_running)} quá ngưỡng`,
        icon: faServer,
      },
      {
        key: 'moodle',
        label: 'Moodle publication',
        value: moodle.publications?.total,
        detail: `${formatNumber(moodle.publications?.simulated)} mô phỏng · ${formatNumber(moodle.active_targets)} target active`,
        icon: faPlugCircleCheck,
      },
    ];
  }, [overview]);

  const attention = overview?.attention || [];
  const recentJobs = overview?.recent_jobs || [];
  const recentAudit = overview?.recent_audit || [];

  return (
    <main className="admin-overview-page">
      <section className="overview-header">
        <div>
          <span>Quản trị hệ thống</span>
          <h1>Tổng quan vận hành</h1>
          <p>Health, hàng đợi, kiểm duyệt và Moodle trong một màn hình.</p>
        </div>
        <button type="button" className="overview-primary-button" onClick={loadOverview} disabled={loading}>
          <FontAwesomeIcon icon={faRotateRight} />
          <span>{loading ? 'Đang tải' : 'Làm mới'}</span>
        </button>
      </section>

      {error && <p className="overview-error">{error}</p>}

      <section className="overview-stats" aria-label="Chỉ số vận hành">
        {stats.map((item) => (
          <article className={`overview-stat overview-stat--${item.key}`} key={item.key}>
            <FontAwesomeIcon icon={item.icon} />
            <div>
              <span>{item.label}</span>
              <b>{formatNumber(item.value)}</b>
              <small>{item.detail}</small>
            </div>
          </article>
        ))}
      </section>

      <section className="overview-grid">
        <section className="overview-panel overview-panel--attention">
          <div className="overview-panel-heading">
            <div>
              <span>Cần chú ý</span>
              <h2>Hàng đợi vận hành</h2>
            </div>
            <FontAwesomeIcon icon={faTriangleExclamation} />
          </div>
          <div className="attention-list">
            {attention.map((item) => (
              <Link className={`attention-row attention-row--${item.severity}`} to={item.path} key={item.key}>
                <span>{item.label}</span>
                <b>{formatNumber(item.count)}</b>
              </Link>
            ))}
          </div>
        </section>

        <section className="overview-panel">
          <div className="overview-panel-heading">
            <div>
              <span>Question bank</span>
              <h2>Review status</h2>
            </div>
            <FontAwesomeIcon icon={faClipboardCheck} />
          </div>
          <dl className="overview-breakdown">
            <div>
              <dt>Draft</dt>
              <dd>{formatNumber(overview?.questions?.draft)}</dd>
            </div>
            <div>
              <dt>Needs revision</dt>
              <dd>{formatNumber(overview?.questions?.needs_revision)}</dd>
            </div>
            <div>
              <dt>Rejected</dt>
              <dd>{formatNumber(overview?.questions?.rejected)}</dd>
            </div>
            <div>
              <dt>Published</dt>
              <dd>{formatNumber(overview?.questions?.published)}</dd>
            </div>
          </dl>
        </section>

        <section className="overview-panel overview-panel--wide">
          <div className="overview-panel-heading">
            <div>
              <span>Job lỗi gần đây</span>
              <h2>Retry queue</h2>
            </div>
            <Link to="/quan-ly-job?status=retryable">Mở job</Link>
          </div>
          <div className="overview-table-wrap">
            <table className="overview-table">
              <thead>
                <tr>
                  <th>Loại</th>
                  <th>Đối tượng</th>
                  <th>Cập nhật</th>
                  <th>Lỗi</th>
                </tr>
              </thead>
              <tbody>
                {recentJobs.map((job) => (
                  <tr key={`${job.kind}:${job.id}`}>
                    <td>
                      <strong>{job.type || job.kind}</strong>
                      <small>{compactId(job.id)}</small>
                    </td>
                    <td>{job.entity?.label || compactId(job.entity?.id)}</td>
                    <td>{formatDateTime(job.updated_at || job.finished_at || job.started_at || job.queued_at)}</td>
                    <td className="overview-error-cell">{job.error_message || 'Không có'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && recentJobs.length === 0 && <p className="overview-empty">Không có job cần retry.</p>}
          </div>
        </section>

        <section className="overview-panel overview-panel--wide">
          <div className="overview-panel-heading">
            <div>
              <span>Audit gần đây</span>
              <h2>Thay đổi hệ thống</h2>
            </div>
            <Link to="/nhat-ky-he-thong">Mở audit</Link>
          </div>
          <div className="audit-list-compact">
            {recentAudit.map((item) => (
              <article key={item.id}>
                <strong>{item.action}</strong>
                <span>{item.entity?.type || 'entity'} · {compactId(item.entity?.id)}</span>
                <small>{formatDateTime(item.created_at)}</small>
              </article>
            ))}
            {!loading && recentAudit.length === 0 && <p className="overview-empty">Chưa có audit log.</p>}
          </div>
        </section>
      </section>
    </main>
  );
}

export default AdminOverviewPage;
