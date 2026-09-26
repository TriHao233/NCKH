import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faArrowRight, faCircleCheck, faRotateRight } from '@fortawesome/free-solid-svg-icons';
import { getAdminOverview } from '../api/adminOverview';
import { getReviewDashboard, listQuestions } from '../api/questions';
import WorkspaceHero from '../components/workspace/WorkspaceHero';
import { EmptyState, ErrorState, SkeletonRows } from '../components/workspace/Feedback';
import { auditActionLabel, auditEntityLabel, compactId, formatNumber } from '../features/admin/adminLabels';
import { formatDateTime, formatPercent } from '../features/review/reviewModel';
import '../css/workspace.css';
import '../css/AdminPages.css';

const KIND_TEXT = {
  document: 'tài liệu (OCR/cắt đoạn)',
  generation: 'sinh câu hỏi',
  evaluation: 'đánh giá AI',
};

function formatLatency(value) {
  if (typeof value !== 'number') return '--';
  return value >= 1000 ? `${(value / 1000).toFixed(1)} giây` : `${Math.round(value)} ms`;
}

function formatCost(value) {
  if (typeof value !== 'number') return '--';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: value > 0 && value < 1 ? 4 : 2 }).format(value);
}

/** Danh sách việc cần xử lý, mỗi dòng dẫn tới đúng trang đã lọc. */
function buildAttention(overview, dashboard, staleUnassigned) {
  const items = [];
  const breakdown = overview?.jobs?.breakdown || [];
  breakdown.forEach((row) => {
    if (row.failed) {
      items.push({ key: `fail-${row.key}`, tone: 'danger', text: `${formatNumber(row.failed)} tác vụ ${KIND_TEXT[row.key] || row.label} lỗi`, to: `/quan-ly-job?type=${row.key}&status=retryable` });
    }
  });
  if (!breakdown.length && overview?.jobs?.failed) {
    items.push({ key: 'fail', tone: 'danger', text: `${formatNumber(overview.jobs.failed)} tác vụ lỗi`, to: '/quan-ly-job?status=retryable' });
  }
  const publicationsFailed = overview?.moodle?.publications?.failed || 0;
  if (publicationsFailed) items.push({ key: 'moodle', tone: 'danger', text: `${formatNumber(publicationsFailed)} lần đồng bộ Moodle lỗi`, to: '/quan-ly-moodle?status=FAILED' });
  const documentsFailed = overview?.documents?.failed || 0;
  if (documentsFailed) items.push({ key: 'docs', tone: 'danger', text: `${formatNumber(documentsFailed)} tài liệu xử lý lỗi`, to: '/quan-ly-tai-lieu' });
  if (staleUnassigned) items.push({ key: 'stale-review', tone: 'warn', text: `${formatNumber(staleUnassigned)} câu chờ duyệt quá 48 giờ chưa ai nhận`, to: '/kiem-duyet?tab=unassigned' });
  const lockExpired = dashboard?.workload?.lock_expired || 0;
  if (lockExpired) items.push({ key: 'lock', tone: 'warn', text: `${formatNumber(lockExpired)} câu bị giữ quá hạn khoá`, to: '/kiem-duyet?tab=overdue' });
  const longRunning = overview?.jobs?.long_running || 0;
  if (longRunning) items.push({ key: 'long', tone: 'warn', text: `${formatNumber(longRunning)} tác vụ chạy quá lâu`, to: '/quan-ly-job?stale_only=true' });
  return items;
}

function AdminOverviewPage() {
  const [overview, setOverview] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [staleUnassigned, setStaleUnassigned] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    const [overviewResult, dashboardResult, staleResult] = await Promise.allSettled([
      getAdminOverview(),
      getReviewDashboard(),
      listQuestions({ page: 1, pageSize: 1, reviewStatus: 'PENDING', assignmentStatus: 'UNASSIGNED', waitingHoursMin: 48 }),
    ]);
    if (overviewResult.status === 'fulfilled') setOverview(overviewResult.value);
    else setError(overviewResult.reason?.message || 'Không tải được tổng quan hệ thống.');
    setDashboard(dashboardResult.status === 'fulfilled' ? dashboardResult.value : null);
    setStaleUnassigned(staleResult.status === 'fulfilled' ? (staleResult.value.total || 0) : 0);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const questions = overview?.questions || {};
  const documents = overview?.documents || {};
  const usage = overview?.model_usage_summary || {};
  const models = overview?.model_performance || [];
  const recentAudit = (overview?.recent_audit || []).slice(0, 5);
  const attention = buildAttention(overview, dashboard, staleUnassigned);

  const stages = [
    { key: 'docs', label: 'Tài liệu đang xử lý', value: documents.processing, meta: `${formatNumber(documents.ready)} tài liệu sẵn sàng`, to: '/quan-ly-tai-lieu' },
    { key: 'draft', label: 'Câu nháp', value: questions.draft, meta: 'Giảng viên đang soạn', to: '/quan-ly' },
    { key: 'pending', label: 'Chờ duyệt', value: questions.pending, meta: `${formatNumber(dashboard?.workload?.unassigned)} chưa ai nhận`, to: '/kiem-duyet?tab=all', focus: true },
    { key: 'revision', label: 'Cần sửa', value: questions.needs_revision, meta: 'Chờ giảng viên sửa và gửi lại', to: '/kiem-duyet?tab=processed' },
    { key: 'approved', label: 'Đã duyệt', value: questions.approved, meta: `${formatNumber(questions.rejected)} câu bị từ chối`, to: '/kiem-duyet?tab=processed' },
    { key: 'moodle', label: 'Đã lên Moodle', value: questions.published, meta: `${formatNumber(Math.max(0, (questions.approved || 0) - (questions.published || 0)))} câu chờ đồng bộ`, to: '/kiem-duyet?tab=moodle' },
  ];

  return (
    <main className="ws-page overview-workspace-page">
      <WorkspaceHero
        badge="Quản trị viên"
        title="Tổng quan"
        description="Việc cần xử lý ngay và dòng chảy câu hỏi từ tài liệu tới Moodle."
        actions={(
          <button type="button" className="btn btn--outline" onClick={load} disabled={loading}>
            <FontAwesomeIcon icon={faRotateRight} />
            Làm mới
          </button>
        )}
      />

      <section className="ws-body">
        <div className="container ws-main">
          {loading && !overview ? (
            <div className="ws-card"><SkeletonRows rows={4} lines={2} /></div>
          ) : error && !overview ? (
            <div className="ws-card"><ErrorState message={error} onRetry={load} /></div>
          ) : (
            <>
              <section className="ws-card">
                <div className="ws-card-title" style={{ marginBottom: 12 }}>
                  <h2>Cần xử lý ngay</h2>
                </div>
                {attention.length === 0 ? (
                  <p className="ad-all-clear"><FontAwesomeIcon icon={faCircleCheck} /> Không có việc cần xử lý.</p>
                ) : (
                  <div className="ad-attention">
                    {attention.map((item) => (
                      <Link key={item.key} to={item.to} className={item.tone === 'danger' ? 'is-danger' : 'is-warning'}>
                        <span>{item.text}</span>
                        <FontAwesomeIcon icon={faArrowRight} />
                      </Link>
                    ))}
                  </div>
                )}
              </section>

              <nav className="ad-pipeline ad-pipeline--6" aria-label="Pipeline câu hỏi">
                {stages.map((stage) => (
                  <Link key={stage.key} to={stage.to} className={`ad-stage ${stage.focus && stage.value ? 'ad-stage--focus' : ''}`}>
                    <span className="ad-stage__label">{stage.label}</span>
                    <span className="ad-stage__value">{formatNumber(stage.value)}</span>
                    <span className="ad-stage__meta">{stage.meta}</span>
                  </Link>
                ))}
              </nav>

              <div className="ws-split">
                <section className="ws-card">
                  <div className="ws-card-head">
                    <div className="ws-card-title">
                      <h2>Sử dụng mô hình 30 ngày</h2>
                      <span>{formatNumber(usage.total_requests)} lượt gọi, {formatNumber(usage.total_tokens)} token, chi phí {formatCost(usage.cost_usd)}</span>
                    </div>
                    <Link className="ws-card-link" to="/cau-hinh-ai">Cấu hình AI</Link>
                  </div>
                  {models.length === 0 ? (
                    <EmptyState compact title="Chưa có lượt gọi mô hình" description="Số liệu xuất hiện sau khi giảng viên sinh câu hỏi hoặc AI đánh giá câu hỏi." />
                  ) : (
                    <div className="ws-table-wrap">
                      <table className="ws-table">
                        <thead><tr><th>Mô hình</th><th className="ws-num">Lượt</th><th className="ws-num">Token</th><th className="ws-num">Độ trễ TB</th><th className="ws-num">Lỗi</th><th className="ws-num">Chi phí</th></tr></thead>
                        <tbody>
                          {models.map((item) => (
                            <tr key={item.key}>
                              <td><strong>{item.model_name || item.model_code}</strong><small>{item.kind_label}</small></td>
                              <td className="ws-num">{formatNumber(item.total)}</td>
                              <td className="ws-num">{formatNumber(item.total_tokens)}</td>
                              <td className="ws-num">{formatLatency(item.avg_latency_ms)}</td>
                              <td className="ws-num">{formatPercent(item.error_rate)}</td>
                              <td className="ws-num">{formatCost(item.cost_usd)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>

                <section className="ws-card">
                  <div className="ws-card-head">
                    <div className="ws-card-title">
                      <h2>Thay đổi gần đây</h2>
                    </div>
                    <Link className="ws-card-link" to="/nhat-ky-he-thong">Xem nhật ký</Link>
                  </div>
                  {recentAudit.length === 0 ? (
                    <p className="ws-hint" style={{ margin: 0 }}>Chưa có hoạt động.</p>
                  ) : (
                    <ul className="ad-feed">
                      {recentAudit.map((item) => (
                        <li key={item.id}>
                          <span className="ad-sentence">
                            <b>{item.actor?.user_name || 'Hệ thống'}</b> đã {auditActionLabel(item.action).toLowerCase()} {auditEntityLabel(item.entity?.type).toLowerCase()} {item.entity?.label || compactId(item.entity?.id)}
                          </span>
                          <small>{formatDateTime(item.created_at)}</small>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </div>
            </>
          )}
        </div>
      </section>
    </main>
  );
}

export default AdminOverviewPage;
