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

const ADMIN_WORKSPACES = [
  {
    label: 'Điều phối kiểm duyệt',
    description: 'Phân công, theo dõi quá hạn và xử lý hàng đợi câu hỏi.',
    path: '/kiem-duyet',
    icon: faClipboardCheck,
  },
  {
    label: 'Thẩm định AI',
    description: 'Xem cảnh báo chất lượng và quyết định các trường hợp cần can thiệp.',
    path: '/duyet-ai',
    icon: faServer,
  },
  {
    label: 'Người dùng & quyền',
    description: 'Quản lý tài khoản, vai trò và trạng thái hoạt động.',
    path: '/quan-ly-nguoi-dung',
    icon: faUsers,
  },
  {
    label: 'Danh mục đào tạo',
    description: 'Quản lý môn học, chương, CLO và cấu trúc ngân hàng.',
    path: '/danh-muc',
    icon: faBookOpen,
  },
  {
    label: 'Tác vụ hệ thống',
    description: 'Theo dõi job đang chạy, lỗi và các tác vụ cần chạy lại.',
    path: '/quan-ly-job',
    icon: faDatabase,
  },
  {
    label: 'Moodle & tích hợp',
    description: 'Kiểm tra cấu hình đích và lịch sử xuất bản.',
    path: '/quan-ly-moodle',
    icon: faPlugCircleCheck,
  },
];

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
    const attentionCount = (overview?.attention || []).reduce(
      (sum, item) => sum + Number(item.count || 0),
      0,
    );
    const operationalIssues = (
      Number(documents.failed || 0)
      + Number(jobs.failed || 0)
      + Number(moodle.publications?.failed || 0)
    );
    return [
      {
        key: 'attention',
        label: 'Cần xử lý ngay',
        value: attentionCount,
        detail: 'Các mục đang chặn hoặc có nguy cơ quá hạn',
        icon: faTriangleExclamation,
        path: overview?.attention?.[0]?.path || '/kiem-duyet',
      },
      {
        key: 'review',
        label: 'Hàng đợi kiểm duyệt',
        value: questions.pending,
        detail: `${formatNumber(questions.needs_revision)} cần sửa · ${formatNumber(questions.approved)} đã duyệt`,
        icon: faClipboardCheck,
        path: '/kiem-duyet',
      },
      {
        key: 'operations',
        label: 'Sự cố vận hành',
        value: operationalIssues,
        detail: `${formatNumber(jobs.active)} job đang chạy · ${formatNumber(jobs.long_running)} quá ngưỡng`,
        icon: faServer,
        path: '/quan-ly-job',
      },
      {
        key: 'users',
        label: 'Tài khoản hoạt động',
        value: users.active,
        detail: `${formatNumber(users.teachers)} giảng viên · ${formatNumber(users.reviewers)} người duyệt`,
        icon: faUsers,
        path: '/quan-ly-nguoi-dung',
      },
    ];
  }, [overview]);

  const attention = overview?.attention || [];
  const recentJobs = overview?.recent_jobs || [];
  const recentAudit = overview?.recent_audit || [];
  const quality = overview?.questions?.quality || {};
  const publications = overview?.moodle?.publications || {};
  const jobBreakdown = overview?.jobs?.breakdown || [];
  const modelPerformance = overview?.model_performance || [];
  const modelUsage = overview?.model_usage_summary || {};

  return (
    <main className="admin-overview-page">
      <section className="overview-header">
        <div>
          <span>TRUNG TÂM QUẢN TRỊ · QBankCTU</span>
          <h1>Trung tâm điều hành</h1>
          <p>Một màn hình để nắm ưu tiên kiểm duyệt, sức khỏe hệ thống và các điểm cần can thiệp.</p>
        </div>
        <button type="button" className="overview-primary-button" onClick={loadOverview} disabled={loading}>
          <FontAwesomeIcon icon={faRotateRight} />
          <span>{loading ? 'Đang tải' : 'Làm mới'}</span>
        </button>
      </section>

      {error && <p className="overview-error">{error}</p>}

      <section className="overview-stats" aria-label="Ưu tiên quản trị">
        {stats.map((item) => (
          <Link className={`overview-stat overview-stat--${item.key}`} key={item.key} to={item.path}>
            <FontAwesomeIcon icon={item.icon} />
            <div>
              <span>{item.label}</span>
              <b>{formatNumber(item.value)}</b>
              <small>{item.detail}</small>
            </div>
            <em>Mở khu vực →</em>
          </Link>
        ))}
      </section>

      <section className="overview-workspaces" aria-labelledby="admin-workspaces-title">
        <div className="overview-section-heading">
          <div>
            <span>Khu vực quản trị</span>
            <h2 id="admin-workspaces-title">Chọn đúng nơi để xử lý công việc</h2>
          </div>
          <Link to="/nhat-ky-he-thong">Xem nhật ký hệ thống</Link>
        </div>
        <div className="overview-workspace-grid">
          {ADMIN_WORKSPACES.map((workspace) => (
            <Link to={workspace.path} className="overview-workspace" key={workspace.path}>
              <FontAwesomeIcon icon={workspace.icon} />
              <div>
                <b>{workspace.label}</b>
                <span>{workspace.description}</span>
              </div>
              <strong aria-hidden="true">→</strong>
            </Link>
          ))}
        </div>
      </section>

      <section className="overview-grid">
        <section className="overview-panel overview-panel--attention">
          <div className="overview-panel-heading">
            <div>
              <span>Ưu tiên hôm nay</span>
              <h2>Cần xử lý ngay</h2>
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
            {!loading && attention.length === 0 && (
              <p className="overview-empty">Không có cảnh báo cần xử lý.</p>
            )}
          </div>
        </section>

        <section className="overview-panel">
          <div className="overview-panel-heading">
            <div>
              <span>Ngân hàng câu hỏi</span>
              <h2>Trạng thái kiểm duyệt</h2>
            </div>
            <FontAwesomeIcon icon={faClipboardCheck} />
          </div>
          <dl className="overview-breakdown overview-breakdown--three">
            <div>
              <dt>Nháp</dt>
              <dd>{formatNumber(overview?.questions?.draft)}</dd>
            </div>
            <div>
              <dt>Chờ duyệt</dt>
              <dd>{formatNumber(overview?.questions?.pending)}</dd>
            </div>
            <div>
              <dt>Đã duyệt</dt>
              <dd>{formatNumber(overview?.questions?.approved)}</dd>
            </div>
            <div>
              <dt>Cần sửa</dt>
              <dd>{formatNumber(overview?.questions?.needs_revision)}</dd>
            </div>
            <div>
              <dt>Từ chối</dt>
              <dd>{formatNumber(overview?.questions?.rejected)}</dd>
            </div>
            <div>
              <dt>Đã ghi Moodle</dt>
              <dd>{formatNumber(overview?.questions?.published)}</dd>
            </div>
          </dl>
        </section>

        <section className="overview-panel">
          <div className="overview-panel-heading">
            <div>
              <span>Chất lượng AI</span>
              <h2>Phân tầng đánh giá</h2>
            </div>
            <FontAwesomeIcon icon={faClipboardCheck} />
          </div>
          <dl className="overview-breakdown">
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
        </section>

        <section className="overview-panel">
          <div className="overview-panel-heading">
            <div>
              <span>Mô phỏng Moodle</span>
              <h2>Trạng thái ghi nhận</h2>
            </div>
            <FontAwesomeIcon icon={faPlugCircleCheck} />
          </div>
          <dl className="overview-breakdown">
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
        </section>

        <div className="overview-section-divider overview-panel--wide">
          <span>Chi tiết vận hành</span>
          <p>Dành cho việc theo dõi kỹ thuật, phân tích lỗi và truy vết.</p>
        </div>

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
                    <td><strong>{item.label}</strong></td>
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
              <span>30 ngày gần nhất</span>
              <h2>Sử dụng mô hình, token và chi phí</h2>
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
              <small>{formatNumber(modelUsage.prompt_tokens)} in · {formatNumber(modelUsage.completion_tokens)} out</small>
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
                      <small>{formatNumber(item.prompt_tokens)} in · {formatNumber(item.completion_tokens)} out</small>
                    </td>
                    <td>{formatCurrency(item.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && modelPerformance.length === 0 && <p className="overview-empty">Chưa có dữ liệu model trong 30 ngày.</p>}
          </div>
        </section>

        <section className="overview-panel overview-panel--wide">
          <div className="overview-panel-heading">
            <div>
              <span>Tác vụ lỗi gần đây</span>
              <h2>Hàng đợi cần chạy lại</h2>
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
            {!loading && recentJobs.length === 0 && <p className="overview-empty">Không có tác vụ cần chạy lại.</p>}
          </div>
        </section>

        <section className="overview-panel overview-panel--wide">
          <div className="overview-panel-heading">
            <div>
              <span>Nhật ký gần đây</span>
              <h2>Thay đổi hệ thống</h2>
            </div>
            <Link to="/nhat-ky-he-thong">Mở nhật ký</Link>
          </div>
          <div className="audit-list-compact">
            {recentAudit.map((item) => (
              <article key={item.id}>
                <strong>{item.action}</strong>
                <span>{item.entity?.type || 'đối tượng'} · {compactId(item.entity?.id)}</span>
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
