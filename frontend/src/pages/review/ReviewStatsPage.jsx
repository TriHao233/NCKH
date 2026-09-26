import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faRotateRight } from '@fortawesome/free-solid-svg-icons';
import { getReviewDashboard } from '../../api/questions';
import WorkspaceHero from '../../components/workspace/WorkspaceHero';
import { EmptyState, ErrorState, SkeletonRows } from '../../components/workspace/Feedback';
import { REVIEW_CRITERIA, formatPercent } from '../../features/review/reviewModel';
import '../../css/workspace.css';
import '../../css/ReviewPage.css';
import '../../css/ReviewDesk.css';

function hoursText(value) {
  return typeof value === 'number' ? `${value.toFixed(1).replace('.', ',')} giờ/câu` : 'chưa đủ dữ liệu thời gian';
}

function ReviewStatsPage() {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setDashboard(await getReviewDashboard());
    } catch (err) {
      setError(err.message || 'Không tải được số liệu kiểm duyệt.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const workload = dashboard?.workload || {};
  const performance = dashboard?.performance || {};
  const calibration = dashboard?.calibration || {};
  const decisions = dashboard?.decisions || {};
  const subjects = dashboard?.subjects || [];
  const scopeText = dashboard?.scope === 'all_reviewers' ? 'toàn bộ người duyệt' : 'các phiếu do bạn chốt';

  return (
    <main className="ws-page review-stats-page">
      <WorkspaceHero
        badge="Người duyệt"
        title="Hiệu suất kiểm duyệt"
        description={`Số liệu 30 ngày gần nhất của ${scopeText}, và mức thống nhất giữa người duyệt với gợi ý AI.`}
        actions={(
          <button type="button" className="btn btn--outline" onClick={load} disabled={loading}>
            <FontAwesomeIcon icon={faRotateRight} />
            Làm mới
          </button>
        )}
      />
      <section className="ws-body">
        <div className="container ws-main">
          {loading && !dashboard ? (
            <div className="ws-card"><SkeletonRows rows={5} lines={2} /></div>
          ) : error ? (
            <div className="ws-card"><ErrorState message={error} onRetry={load} /></div>
          ) : (
            <>
              <section className="ws-card">
                <p className="rv-summary-line">
                  30 ngày: <b className="tabular">{performance.reviews_30d || 0}</b> lượt duyệt,
                  {' '}tỷ lệ duyệt <b className="tabular">{formatPercent(performance.approval_rate)}</b>,
                  {' '}trung bình <b>{hoursText(performance.average_review_hours)}</b>.
                  {' '}Tuần này <b className="tabular">{performance.reviews_7d || 0}</b> lượt.
                </p>
              </section>

              <div className="ws-split">
                <section className="ws-card">
                  <div className="ws-card-head">
                    <div className="ws-card-title">
                      <h2>Khối lượng hiện tại</h2>
                      <span>Câu đang chờ kiểm duyệt</span>
                    </div>
                    <Link className="ws-card-link" to="/kiem-duyet">Mở Hộp việc</Link>
                  </div>
                  <div className="ws-table-wrap">
                    <table className="ws-table">
                      <tbody>
                        <tr><td>Chưa ai nhận</td><td className="ws-num">{workload.unassigned || 0}</td></tr>
                        <tr><td>Đã giao, chưa bắt đầu</td><td className="ws-num">{workload.assigned || 0}</td></tr>
                        <tr><td>Đang xử lý</td><td className="ws-num">{workload.in_review || 0}</td></tr>
                        <tr><td>Quá hạn giữ câu</td><td className="ws-num">{workload.lock_expired || 0}</td></tr>
                        <tr><td>Của tôi</td><td className="ws-num">{workload.mine || 0}</td></tr>
                        <tr><td><strong>Tổng chờ duyệt</strong></td><td className="ws-num"><strong>{workload.pending || 0}</strong></td></tr>
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="ws-card">
                  <div className="ws-card-title" style={{ marginBottom: 18 }}>
                    <h2>Kết luận 30 ngày</h2>
                    <span>{performance.override_count || 0} lần duyệt khác gợi ý AI, {performance.revision_issues || 0} lỗi đã gửi giảng viên</span>
                  </div>
                  <div className="ws-table-wrap">
                    <table className="ws-table">
                      <tbody>
                        <tr><td>Duyệt</td><td className="ws-num">{decisions.APPROVED || 0}</td></tr>
                        <tr><td>Yêu cầu sửa</td><td className="ws-num">{decisions.NEEDS_REVISION || 0}</td></tr>
                        <tr><td>Từ chối</td><td className="ws-num">{decisions.REJECTED || 0}</td></tr>
                      </tbody>
                    </table>
                  </div>
                </section>
              </div>

              <section className="ws-card">
                <div className="ws-card-title" style={{ marginBottom: 14 }}>
                  <h2>Mức thống nhất với AI</h2>
                  <span>
                    Cùng kết luận {formatPercent(calibration.agreement_rate)} trên {calibration.sample_size || 0} phiếu.
                    {' '}AI đề xuất xem lại nhưng vẫn duyệt: {calibration.ai_failed_but_approved || 0}.
                    {' '}AI đề xuất đạt nhưng giữ lại: {calibration.ai_passed_but_not_approved || 0}.
                  </span>
                </div>
                <div className="ws-table-wrap">
                  <table className="ws-table">
                    <thead>
                      <tr>
                        <th>Tiêu chí</th>
                        <th>Mức thống nhất</th>
                        <th className="ws-num">Số mẫu</th>
                        <th className="ws-num">Số lệch</th>
                      </tr>
                    </thead>
                    <tbody>
                      {REVIEW_CRITERIA.map((criterion) => {
                        const item = calibration.criteria?.[criterion.key] || {};
                        const rate = typeof item.agreement_rate === 'number' ? item.agreement_rate : null;
                        return (
                          <tr key={criterion.key}>
                            <td>{criterion.label}</td>
                            <td style={{ minWidth: 200 }}>
                              <div className="rv-inline-bar">
                                <span style={{ width: `${(rate || 0) * 100}%` }} />
                              </div>
                              <small>{formatPercent(rate)}</small>
                            </td>
                            <td className="ws-num">{item.sample_size || 0}</td>
                            <td className="ws-num">{item.disagreements || 0}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="ws-card">
                <div className="ws-card-title" style={{ marginBottom: 14 }}>
                  <h2>Theo học phần</h2>
                  <span>Số phiếu kiểm duyệt trong 30 ngày</span>
                </div>
                {subjects.length === 0 ? (
                  <EmptyState compact title="Chưa có dữ liệu" description="Số liệu theo học phần xuất hiện sau khi có phiếu kiểm duyệt." />
                ) : (
                  <div className="ws-table-wrap">
                    <table className="ws-table">
                      <thead><tr><th>Học phần</th><th className="ws-num">Số phiếu</th></tr></thead>
                      <tbody>
                        {subjects.map((subject) => (
                          <tr key={subject.subject_id || subject.label}><td>{subject.label}</td><td className="ws-num">{subject.reviewed}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </section>
    </main>
  );
}

export default ReviewStatsPage;
