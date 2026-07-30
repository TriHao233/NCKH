import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faClipboardCheck,
  faDatabase,
  faPlugCircleCheck,
  faRobot,
  faRotateRight,
  faServer,
  faUsers,
} from '@fortawesome/free-solid-svg-icons';
import { getAdminOverview } from '../api/adminOverview';
import '../css/AdminOverviewPage.css';

const ATTENTION_LABELS = {
  'Job cần xử lý': 'Tác vụ lỗi',
  'Job quá ngưỡng': 'Tác vụ quá hạn',
};

const JOB_LABELS = {
  'Chunk/Index': 'Lập chỉ mục',
  OCR: 'Đọc tài liệu',
};

const AUDIT_LABELS = {
  'auth.demo_login': 'Đăng nhập demo',
  QUESTION_EVALUATED: 'Đánh giá câu hỏi',
  QUESTION_APPROVED: 'Duyệt câu hỏi',
  QUESTION_REJECTED: 'Từ chối câu hỏi',
  QUESTION_NEEDS_REVISION: 'Yêu cầu sửa',
};

const ENTITY_LABELS = {
  user: 'người dùng',
  QUESTION: 'câu hỏi',
};

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

function formatPercent(value) {
  return typeof value === 'number' ? `${Math.round(value * 100)}%` : '--';
}

function formatLatency(value) {
  if (typeof value !== 'number') return '--';
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${Math.round(value)}ms`;
}

function formatCurrency(value) {
  if (typeof value !== 'number') return '--';
  return new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: value < 1 ? 4 : 2,
  }).format(value);
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

  const users = overview?.users || {};
  const questions = overview?.questions || {};
  const documents = overview?.documents || {};
  const jobs = overview?.jobs || {};
  const moodle = overview?.moodle || {};
  const attention = overview?.attention || [];
  const recentJobs = overview?.recent_jobs || [];
  const recentAudit = overview?.recent_audit || [];
  const quality = overview?.questions?.quality || {};
  const publications = overview?.moodle?.publications || {};
  const jobBreakdown = overview?.jobs?.breakdown || [];
  const modelPerformance = overview?.model_performance || [];
  const modelUsage = overview?.model_usage_summary || {};
  const attentionCount = attention.reduce(
    (sum, item) => sum + Number(item.count || 0),
    0,
  );
  const operationalIssues = (
    Number(documents.failed || 0)
    + Number(jobs.failed || 0)
    + Number(moodle.publications?.failed || 0)
  );
  const flowStops = [
    {
      key: 'bank',
      label: 'Ngân hàng',
      note: `${formatNumber(questions.total)} câu hỏi`,
      icon: faDatabase,
      path: '/quan-ly',
    },
    {
      key: 'ai',
      label: 'Thẩm định AI',
      note: Number(quality.not_evaluated || 0) > 0
        ? `${formatNumber(quality.not_evaluated)} chưa chấm`
        : 'Đã phân tầng',
      icon: faRobot,
      path: '/duyet-ai',
    },
    {
      key: 'review',
      label: 'Kiểm duyệt',
      note: Number(questions.pending || 0) > 0
        ? `${formatNumber(questions.pending)} đang chờ`
        : 'Không tồn đọng',
      icon: faClipboardCheck,
      path: '/kiem-duyet',
    },
    {
      key: 'moodle',
      label: 'Moodle',
      note: Number(publications.failed || 0) > 0
        ? `${formatNumber(publications.failed)} bản ghi lỗi`
        : `${formatNumber(publications.published)} đã ghi`,
      icon: faPlugCircleCheck,
      path: '/quan-ly-moodle',
    },
  ];

  return (
    <main className="admin-overview-page">
      <header className="overview-masthead">
        <div>
          <span className="overview-kicker">Vận hành</span>
          <h1>Tổng quan</h1>
          <p>Việc cần xử lý và trạng thái hệ thống.</p>
        </div>
        <div className="overview-masthead__brief">
          <p>
            <strong>{formatNumber(attentionCount)}</strong> việc cần xử lý
            {' · '}
            <strong>{formatNumber(operationalIssues)}</strong> sự cố
          </p>
          <button type="button" className="overview-refresh" onClick={loadOverview} disabled={loading}>
            <FontAwesomeIcon icon={faRotateRight} />
            <span>{loading ? 'Đang tải' : 'Làm mới'}</span>
          </button>
        </div>
      </header>

      {error && <p className="overview-error">{error}</p>}

      <section className="overview-route-section" aria-labelledby="overview-route-title">
        <div className="overview-section-intro">
          <span>Quy trình</span>
          <div>
            <h2 id="overview-route-title">Luồng nội dung</h2>
            <p>Mở nhanh từng bước.</p>
          </div>
        </div>

        <nav className="overview-route" aria-label="Các điểm trong luồng vận hành">
          {flowStops.map((item) => (
            <Link className={`overview-route-stop overview-route-stop--${item.key}`} key={item.key} to={item.path}>
              <span className="overview-route-stop__icon">
                <FontAwesomeIcon icon={item.icon} />
              </span>
                 <strong>{ATTENTION_LABELS[item.label] || item.label}</strong>
              <small>{item.note}</small>
            </Link>
          ))}
        </nav>

        <div className="overview-route-caption">
          <span className={`overview-pulse ${operationalIssues > 0 ? 'overview-pulse--alert' : ''}`} aria-hidden="true" />
          <p>
            <strong>{operationalIssues > 0 ? `${formatNumber(operationalIssues)} sự cố.` : 'Hệ thống ổn định.'}</strong>
            {' '}
            {formatNumber(jobs.active)} tác vụ đang chạy, {formatNumber(jobs.long_running)} quá ngưỡng.
          </p>
          <Link to="/quan-ly-job">Xem tác vụ →</Link>
        </div>
      </section>

      <section className="overview-shift">
        <aside className="overview-shift-summary">
          <span>Cần xử lý</span>
          <strong>{formatNumber(attentionCount)}</strong>
          <p>{attentionCount > 0 ? 'việc đang chờ.' : 'Không có việc khẩn.'}</p>
          <Link to="/kiem-duyet">Mở hàng đợi →</Link>
        </aside>

        <div className="overview-decision-list">
          <header>
            <div>
              <span>Theo mức độ</span>
              <h2>Ưu tiên</h2>
            </div>
            <small>{formatNumber(attention.length)} nhóm công việc</small>
          </header>
          <div>
            {attention.map((item, index) => (
              <Link className={`overview-decision-row overview-decision-row--${item.severity}`} to={item.path} key={item.key}>
                <span className="overview-decision-row__index">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <strong>{item.label}</strong>
                <b>{formatNumber(item.count)}</b>
                <span aria-hidden="true">↗</span>
              </Link>
            ))}
            {!loading && attention.length === 0 && (
              <p className="overview-empty">Không có cảnh báo cần xử lý.</p>
            )}
          </div>
        </div>
      </section>

      <section className="overview-signals">
        <div className="overview-signal">
          <header>
            <div>
              <span>Đánh giá AI</span>
              <h2>Chất lượng câu hỏi</h2>
            </div>
            <Link to="/duyet-ai">Mở AI</Link>
          </header>
          <div className="overview-spectrum" aria-label="Phân bố chất lượng AI">
            <i className="overview-spectrum__good" style={{ flexGrow: Number(quality.green || 0) + 0.2 }} />
            <i className="overview-spectrum__review" style={{ flexGrow: Number(quality.yellow || 0) + 0.2 }} />
            <i className="overview-spectrum__risk" style={{ flexGrow: Number(quality.red || 0) + 0.2 }} />
            <i className="overview-spectrum__unknown" style={{ flexGrow: Number(quality.not_evaluated || 0) + 0.2 }} />
          </div>
          <dl className="overview-signal-readout">
            <div>
              <dt>Đạt tốt</dt>
              <dd>{formatNumber(quality.green)}</dd>
            </div>
            <div>
              <dt>Cần xem lại</dt>
              <dd>{formatNumber(quality.yellow)}</dd>
            </div>
            <div>
              <dt>Rủi ro cao</dt>
              <dd>{formatNumber(quality.red)}</dd>
            </div>
            <div>
              <dt>Chưa chấm</dt>
              <dd>{formatNumber(quality.not_evaluated)}</dd>
            </div>
          </dl>
        </div>

        <div className="overview-signal">
          <header>
            <div>
              <span>Xuất bản</span>
              <h2>Trạng thái Moodle</h2>
            </div>
            <Link to="/quan-ly-moodle">Mở Moodle</Link>
          </header>
          <div className="overview-publication-line" aria-hidden="true">
            <span className="is-complete" />
            <span className={Number(publications.pending || 0) > 0 ? 'is-active' : ''} />
            <span className={Number(publications.failed || 0) > 0 ? 'is-error' : 'is-complete'} />
          </div>
          <dl className="overview-signal-readout">
            <div>
              <dt>Đã ghi</dt>
              <dd>{formatNumber(publications.published)}</dd>
            </div>
            <div>
              <dt>Lỗi</dt>
              <dd>{formatNumber(publications.failed)}</dd>
            </div>
            <div>
              <dt>Đang chờ</dt>
              <dd>{formatNumber(publications.pending)}</dd>
            </div>
            <div>
              <dt>Mô phỏng</dt>
              <dd>{formatNumber(publications.simulated)}</dd>
            </div>
          </dl>
        </div>
      </section>

      <div className="overview-section-divider">
        <span>Kỹ thuật</span>
        <p>Tác vụ, lỗi và thay đổi gần đây.</p>
      </div>

      <section className="overview-grid">
        <section className="overview-panel overview-panel--wide">
          <div className="overview-panel-heading">
            <div>
              <span>Hàng đợi</span>
              <h2>Tác vụ theo loại</h2>
            </div>
            <Link to="/quan-ly-job">Mở hàng đợi</Link>
          </div>
          <div className="overview-table-wrap">
            <table className="overview-table overview-table--compact">
              <thead>
                <tr>
                  <th>Loại</th>
                  <th>Tổng</th>
                  <th>Đang chạy</th>
                  <th>Lỗi</th>
                  <th>Quá ngưỡng</th>
                </tr>
              </thead>
              <tbody>
                {jobBreakdown.map((item) => (
                  <tr key={item.key}>
                     <td><strong>{JOB_LABELS[item.label] || item.label}</strong></td>
                    <td>{formatNumber(item.total)}</td>
                    <td>{formatNumber(item.active)}</td>
                    <td>{formatNumber(item.failed)}</td>
                    <td>{formatNumber(item.long_running)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && jobBreakdown.length === 0 && <p className="overview-empty">Chưa có tác vụ vận hành.</p>}
          </div>
        </section>

        <section className="overview-panel overview-panel--wide">
          <div className="overview-panel-heading">
            <div>
              <span>30 ngày</span>
              <h2>Mức dùng AI</h2>
            </div>
            <FontAwesomeIcon icon={faServer} />
          </div>
          <div className="model-usage-summary">
            <div>
              <span>Lượt gọi</span>
              <b>{formatNumber(modelUsage.total_requests)}</b>
            </div>
            <div>
              <span>Tokens</span>
              <b>{formatNumber(modelUsage.total_tokens)}</b>
              <small>{formatNumber(modelUsage.prompt_tokens)} vào · {formatNumber(modelUsage.completion_tokens)} ra</small>
            </div>
            <div>
              <span>Chi phí</span>
              <b>{formatCurrency(modelUsage.cost_usd)}</b>
            </div>
            <div>
              <span>Độ trễ TB</span>
              <b>{formatLatency(modelUsage.avg_latency_ms)}</b>
            </div>
          </div>
          <div className="overview-table-wrap">
            <table className="overview-table overview-table--compact">
              <thead>
                <tr>
                  <th>Mô hình</th>
                  <th>Luồng</th>
                  <th>Tổng</th>
                  <th>Hoàn tất</th>
                  <th>Lỗi</th>
                  <th>Tỉ lệ lỗi</th>
                  <th>Độ trễ TB</th>
                  <th>Token</th>
                  <th>Chi phí</th>
                </tr>
              </thead>
              <tbody>
                {modelPerformance.map((item) => (
                  <tr key={item.key}>
                    <td><strong>{item.model_code}</strong></td>
                    <td>{item.kind_label}</td>
                    <td>{formatNumber(item.total)}</td>
                    <td>{formatNumber(item.completed)}</td>
                    <td>{formatNumber(item.failed)}</td>
                    <td>{formatPercent(item.error_rate)}</td>
                    <td>{formatLatency(item.avg_latency_ms)}</td>
                    <td>
                      {formatNumber(item.total_tokens)}
                       <small>{formatNumber(item.prompt_tokens)} vào · {formatNumber(item.completion_tokens)} ra</small>
                    </td>
                    <td>{formatCurrency(item.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && modelPerformance.length === 0 && <p className="overview-empty">Chưa có dữ liệu AI trong 30 ngày.</p>}
          </div>
        </section>

        <section className="overview-panel overview-panel--wide">
          <div className="overview-panel-heading">
            <div>
              <span>Lỗi gần đây</span>
              <h2>Tác vụ cần chạy lại</h2>
            </div>
            <Link to="/quan-ly-job?status=retryable">Mở hàng đợi</Link>
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
                       <strong>{JOB_LABELS[job.type || job.kind] || job.type || job.kind}</strong>
                      <small>{compactId(job.id)}</small>
                    </td>
                    <td>{job.entity?.label || compactId(job.entity?.id)}</td>
                    <td>{formatDateTime(job.updated_at || job.finished_at || job.started_at || job.queued_at)}</td>
                    <td className="overview-error-cell">{job.error_message || 'Không có'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && recentJobs.length === 0 && <p className="overview-empty">Không có tác vụ cần chạy lại.</p>}
          </div>
        </section>

        <section className="overview-panel overview-panel--wide">
          <div className="overview-panel-heading">
            <div>
              <span>Gần đây</span>
              <h2>Thay đổi hệ thống</h2>
            </div>
            <Link to="/nhat-ky-he-thong">Mở nhật ký</Link>
          </div>
          <div className="audit-list-compact">
            {recentAudit.map((item) => (
              <article key={item.id}>
                 <strong>{AUDIT_LABELS[item.action] || item.action}</strong>
                 <span>{ENTITY_LABELS[item.entity?.type] || item.entity?.type || 'đối tượng'} · {compactId(item.entity?.id)}</span>
                <small>{formatDateTime(item.created_at)}</small>
              </article>
            ))}
            {!loading && recentAudit.length === 0 && <p className="overview-empty">Chưa có nhật ký.</p>}
          </div>
        </section>
      </section>
    </main>
  );
}

export default AdminOverviewPage;
