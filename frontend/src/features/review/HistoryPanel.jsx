import { faClockRotateLeft } from '@fortawesome/free-solid-svg-icons';
import { EmptyState, SkeletonRows } from '../../components/workspace/Feedback';
import {
  ISSUE_SEVERITY,
  PUBLICATION_STATUS_LABEL,
  REVIEW_STATUS_LABEL,
  formatDateTime,
  refId,
  reviewIssuesOf,
} from './reviewModel';
import { userName } from './reviewData';

const DECISION_TONE = {
  APPROVED: 'success',
  NEEDS_REVISION: 'warn',
  REJECTED: 'danger',
};

function publicationError(publication) {
  const { error } = publication || {};
  if (!error) return '';
  return typeof error === 'string' ? error : (error.message || '');
}

function severityLabel(value) {
  return ISSUE_SEVERITY.find((item) => item.value === value)?.label || 'Vừa';
}

function HistoryPanel({ reviews, publications, loading, peopleById }) {
  if (loading) return <SkeletonRows rows={3} lines={2} />;

  if (reviews.length === 0 && publications.length === 0) {
    return (
      <EmptyState
        compact
        icon={faClockRotateLeft}
        title="Chưa có lịch sử"
        description="Các lần kiểm duyệt và đồng bộ Moodle của câu hỏi sẽ được ghi lại ở đây."
      />
    );
  }

  return (
    <div className="ws-split">
      <div>
        <h4 className="ws-subhead">Các lần kiểm duyệt</h4>
        {reviews.length === 0 ? (
          <p className="ws-hint">Chưa có phiếu kiểm duyệt.</p>
        ) : (
          <ol className="rv-timeline">
            {reviews.map((review) => {
              const issues = reviewIssuesOf(review);
              const tone = review.resulting_status === 'PENDING' ? '' : DECISION_TONE[review.decision];
              return (
                <li key={refId(review)} className={tone ? `is-${tone}` : ''}>
                  <header>
                    <span className={`ws-pill ${tone ? `ws-pill--${tone}` : 'ws-pill--info'}`}>
                      {review.resulting_status === 'PENDING'
                        ? 'Duyệt lần 1, chờ lần 2'
                        : (REVIEW_STATUS_LABEL[review.decision] || review.decision)}
                    </span>
                    {review.review_stage === 'SECONDARY' && <span className="ws-pill ws-pill--outline">Lần 2</span>}
                    <span className="ws-muted">{formatDateTime(review.reviewed_at)}</span>
                  </header>
                  <p className="ws-muted" style={{ fontSize: '0.8rem', margin: '4px 0 0' }}>
                    {userName(peopleById.get(refId(review.reviewer_user_id)), 'Người duyệt')}
                    {review.question_version ? `, phiên bản ${review.question_version}` : ''}
                    {review.override?.applied ? ', duyệt khác đề xuất AI' : ''}
                  </p>
                  {review.note && <p>{review.note}</p>}
                  {issues.length > 0 && (
                    <ul>
                      {issues.slice(0, 5).map((issue, index) => (
                        <li key={`${issue.title}-${index}`}>
                          {severityLabel(issue.severity)}: {issue.title || issue.detail}
                          {issue.page_number ? ` (trang ${issue.page_number})` : ''}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
      <div>
        <h4 className="ws-subhead">Đồng bộ Moodle</h4>
        {publications.length === 0 ? (
          <p className="ws-hint">Chưa đồng bộ lên Moodle lần nào.</p>
        ) : (
          <ol className="rv-timeline">
            {publications.map((publication) => (
              <li key={refId(publication)} className={publication.status === 'FAILED' ? 'is-danger' : 'is-success'}>
                <header>
                  <span className={`ws-pill ${publication.status === 'FAILED' ? 'ws-pill--danger' : 'ws-pill--success'}`}>
                    {PUBLICATION_STATUS_LABEL[publication.status] || publication.status}
                  </span>
                  {publication.external_sync === false && <span className="ws-pill ws-pill--outline">Mô phỏng</span>}
                  <span className="ws-muted">{formatDateTime(publication.published_at || publication.created_at)}</span>
                </header>
                {publicationError(publication) && <p>{publicationError(publication)}</p>}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

export default HistoryPanel;
