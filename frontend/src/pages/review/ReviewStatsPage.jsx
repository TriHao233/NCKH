import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faRotateRight } from '@fortawesome/free-solid-svg-icons';
import { getReviewDashboard, getReviewPolicy, updateReviewPolicy } from '../../api/questions';
import WorkspaceHero from '../../components/workspace/WorkspaceHero';
import { EmptyState, ErrorState, Notice, SkeletonRows } from '../../components/workspace/Feedback';
import { useReviewLookups } from '../../features/review/reviewData';
import { REVIEW_CRITERIA, formatPercent, reviewDurationLabel } from '../../features/review/reviewModel';
import '../../css/workspace.css';
import '../../css/ReviewPage.css';
import '../../css/ReviewDesk.css';

function hoursText(value) {
  const duration = reviewDurationLabel(value);
  return duration ? `${duration}/câu` : 'chưa đủ dữ liệu thời gian';
}

const REVIEWER_FLAG_LABEL = {
  HIGH_OVERRIDE: 'Hay duyệt khác AI',
  HIGH_BULK: 'Duyệt hàng loạt nhiều',
  SLA_BREACHED: 'Giữ câu trễ hạn',
  NO_SUBJECTS: 'Chưa gán học phần',
};

const REVIEWER_FLAG_TONE = {
  HIGH_OVERRIDE: 'warn',
  HIGH_BULK: 'warn',
  SLA_BREACHED: 'danger',
  NO_SUBJECTS: 'outline',
};

function ReviewPolicyCard({ subjects }) {
  const [policy, setPolicy] = useState(null);
  const [form, setForm] = useState(null);
  const [state, setState] = useState({ saving: false, error: '', saved: false });

  useEffect(() => {
    getReviewPolicy()
      .then((value) => {
        setPolicy(value);
        setForm({
          secondaryOnOverride: Boolean(value.secondary_on_override),
          belowScore: typeof value.secondary_below_score === 'number' ? String(value.secondary_below_score) : '',
          subjectIds: value.secondary_subject_ids || [],
        });
      })
      .catch((err) => setState({ saving: false, error: err.message || 'Không tải được chính sách.', saved: false }));
  }, []);

  if (!form) {
    return state.error ? <Notice tone="error">{state.error}</Notice> : <SkeletonRows rows={2} lines={1} />;
  }

  const toggleSubject = (id) => {
    const next = new Set(form.subjectIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setForm({ ...form, subjectIds: [...next] });
  };

  const save = async (event) => {
    event.preventDefault();
    const raw = form.belowScore.trim().replace(',', '.');
    const score = raw === '' ? null : Number(raw);
    if (score !== null && !(score >= 0 && score <= 1)) {
      setState({ saving: false, error: 'Ngưỡng điểm AI phải nằm trong khoảng 0 đến 1.', saved: false });
      return;
    }
    setState({ saving: true, error: '', saved: false });
    try {
      const saved = await updateReviewPolicy({
        secondary_on_override: form.secondaryOnOverride,
        secondary_below_score: score,
        secondary_subject_ids: form.subjectIds,
      });
      setPolicy(saved);
      setState({ saving: false, error: '', saved: true });
    } catch (err) {
      setState({ saving: false, error: err.message || 'Không lưu được chính sách.', saved: false });
    }
  };

  return (
    <form onSubmit={save}>
      <label className="ws-check">
        <input
          type="checkbox"
          checked={form.secondaryOnOverride}
          onChange={(event) => setForm({ ...form, secondaryOnOverride: event.target.checked })}
        />
        Bắt buộc duyệt lần 2 khi người duyệt duyệt khác gợi ý AI (override)
      </label>
      <label className="ws-field" style={{ maxWidth: 360 }}>
        <span>Bắt buộc duyệt lần 2 khi điểm AI dưới (0 đến 1, để trống là tắt)</span>
        <input
          className="ws-input"
          inputMode="decimal"
          placeholder="Ví dụ 0.7"
          value={form.belowScore}
          onChange={(event) => setForm({ ...form, belowScore: event.target.value })}
        />
      </label>
      <div className="ws-field">
        <span>Học phần luôn phải duyệt hai lần</span>
        {subjects.length === 0 ? (
          <p className="ws-hint">Chưa có học phần.</p>
        ) : (
          <div className="ad-permission-grid">
            {subjects.map((subject) => {
              const id = String(subject.id || subject._id);
              return (
                <label className="ws-check" key={id}>
                  <input type="checkbox" checked={form.subjectIds.includes(id)} onChange={() => toggleSubject(id)} />
                  {[subject.subject_code, subject.subject_name].filter(Boolean).join(' - ')}
                </label>
              );
            })}
          </div>
        )}
      </div>
      {state.error && <Notice tone="error">{state.error}</Notice>}
      {state.saved && <Notice tone="success">Đã lưu. Áp dụng cho các lần duyệt từ bây giờ.</Notice>}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12 }}>
        <button type="submit" className="btn btn--primary" disabled={state.saving}>
          {state.saving ? 'Đang lưu...' : 'Lưu chính sách'}
        </button>
        {policy?.updated_at && <small className="ws-muted">Cập nhật lần cuối {new Date(policy.updated_at).toLocaleString('vi-VN')}</small>}
      </div>
    </form>
  );
}

function shortHours(value) {
  return reviewDurationLabel(value) || '--';
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
  const reviewers = dashboard?.reviewers || [];
  const isAdminScope = dashboard?.scope === 'all_reviewers';
  const lookups = useReviewLookups();
  const subjectCodes = (ids) => (ids || []).map((id) => lookups.subjectsById.get(id)?.subject_code || '?').join(', ');
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
                        <tr>
                          <td>Trễ hạn duyệt{workload.sla_hours ? ` (quá ${workload.sla_hours} giờ)` : ''}</td>
                          <td className="ws-num">
                            {workload.sla_breached
                              ? <Link to="/kiem-duyet?tab=late"><span className="ws-pill ws-pill--danger tabular">{workload.sla_breached}</span></Link>
                              : 0}
                          </td>
                        </tr>
                        <tr><td>Của tôi</td><td className="ws-num">{workload.mine || 0}</td></tr>
                        <tr><td><strong>Tổng chờ duyệt</strong></td><td className="ws-num"><strong>{workload.pending || 0}</strong></td></tr>
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="ws-card">
                  <div className="ws-card-title" style={{ marginBottom: 18 }}>
                    <h2>Kết luận 30 ngày</h2>
                    <span>
                      {performance.override_count || 0} lần duyệt khác gợi ý AI, {performance.revision_issues || 0} lỗi đã gửi giảng viên
                      {performance.bulk_count ? `, ${performance.bulk_count} phiếu duyệt hàng loạt` : ''}
                    </span>
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
                    Cùng kết luận {formatPercent(calibration.agreement_rate)} trên {calibration.sample_size || 0} phiếu
                    {' '}(không tính phiếu duyệt hàng loạt).
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

              {isAdminScope && (
                <section className="ws-card">
                  <div className="ws-card-title" style={{ marginBottom: 14 }}>
                    <h2>Chính sách duyệt lần 2</h2>
                    <span>Khi điều kiện khớp, lần duyệt đạt đầu tiên tự chuyển sang chờ một người duyệt khác xác nhận.</span>
                  </div>
                  <ReviewPolicyCard subjects={lookups.subjects || []} />
                </section>
              )}

              {isAdminScope && (
                <section className="ws-card">
                  <div className="ws-card-title" style={{ marginBottom: 14 }}>
                    <h2>Theo người duyệt</h2>
                    <span>
                      Khối lượng đang giữ và chất lượng kết luận 30 ngày. Cảnh báo chỉ xét khi có từ 5 phiếu.
                      {' '}<Link to="/quan-ly-nguoi-dung">Gán học phần phụ trách</Link>
                    </span>
                  </div>
                  {reviewers.length === 0 ? (
                    <EmptyState compact title="Chưa có người duyệt" description="Tạo tài khoản vai trò Người duyệt ở trang Người dùng." />
                  ) : (
                    <div className="ws-table-wrap">
                      <table className="ws-table">
                        <thead>
                          <tr>
                            <th>Người duyệt</th>
                            <th>Phụ trách</th>
                            <th className="ws-num">Đang giữ</th>
                            <th className="ws-num">Phiếu 30 ngày</th>
                            <th className="ws-num">Tỷ lệ duyệt</th>
                            <th className="ws-num">Khác AI (override)</th>
                            <th className="ws-num">Khớp AI</th>
                            <th className="ws-num">Thời gian TB</th>
                            <th>Cảnh báo</th>
                          </tr>
                        </thead>
                        <tbody>
                          {reviewers.map((row) => (
                            <tr key={row.user_id}>
                              <td>
                                {row.display_name}
                                <small>
                                  {row.role === 'Admin' ? 'Quản trị' : 'Người duyệt'}
                                  {row.is_active ? '' : ' · đã khoá'}
                                </small>
                              </td>
                              <td>
                                {(row.review_subject_ids || []).length
                                  ? subjectCodes(row.review_subject_ids)
                                  : <span className="ws-muted">Mọi học phần</span>}
                              </td>
                              <td className="ws-num">
                                {row.holding}
                                {row.holding_sla_breached ? <small>{row.holding_sla_breached} trễ hạn</small> : null}
                              </td>
                              <td className="ws-num">
                                {row.reviews_30d}
                                {row.bulk_count ? <small>{row.bulk_count} hàng loạt</small> : null}
                              </td>
                              <td className="ws-num">{formatPercent(row.approval_rate)}</td>
                              <td className="ws-num">
                                {formatPercent(row.override_rate)}
                                {row.override_count ? <small>{row.override_count} phiếu</small> : null}
                              </td>
                              <td className="ws-num">
                                {formatPercent(row.ai_agreement_rate)}
                                {row.ai_sample_size ? <small>{row.ai_sample_size} mẫu</small> : null}
                              </td>
                              <td className="ws-num">{shortHours(row.average_review_hours)}</td>
                              <td>
                                {row.flags.length === 0
                                  ? <span className="ws-muted">--</span>
                                  : row.flags.map((flag) => (
                                    <span key={flag} className={`ws-pill ws-pill--${REVIEWER_FLAG_TONE[flag] || 'warn'}`}>
                                      {REVIEWER_FLAG_LABEL[flag] || flag}
                                    </span>
                                  ))}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              )}

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
