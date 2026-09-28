import { useEffect, useMemo, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faCheck } from '@fortawesome/free-solid-svg-icons';
import { listQuestionVersions } from '../../api/questions';
import { difficultyLabel, questionTypeLabel } from '../../constants/generationEnums';
import {
  ISSUE_SEVERITY,
  bloomText,
  correctAnswerKeys,
  isResubmission,
  questionTypeKey,
  refId,
  reviewIssuesOf,
} from './reviewModel';
import { baselineReview, diffVersions } from './versionDiff';

const REVIEW_DECISION_TEXT = {
  APPROVED: 'đã duyệt',
  NEEDS_REVISION: 'yêu cầu sửa',
  REJECTED: 'từ chối',
};

function WordSegments({ segments, side }) {
  return segments.map((segment, index) => {
    if (segment.type === 'same') return <span key={index}>{segment.text}</span>;
    const Tag = side === 'before' ? 'del' : 'ins';
    return <Tag key={index} className={`rv-diff-${segment.type}`}>{segment.text}</Tag>;
  });
}

function ChangeBody({ change }) {
  if (change.kind === 'sources') {
    return (
      <div className="ad-change-values">
        <div className="is-old" aria-label="Nguồn bị bỏ">
          {change.removed.length ? change.removed.map((item) => <p key={item}>− {item}</p>) : <p>(không bỏ nguồn nào)</p>}
        </div>
        <div className="is-new" aria-label="Nguồn thêm mới">
          {change.added.length ? change.added.map((item) => <p key={item}>+ {item}</p>) : <p>(không thêm nguồn nào)</p>}
        </div>
      </div>
    );
  }
  if (change.kind === 'text' && change.words) {
    return (
      <div className="ad-change-values">
        <pre className="is-old" aria-label="Trước">{change.before ? <WordSegments segments={change.words.before} side="before" /> : '(trống)'}</pre>
        <pre className="is-new" aria-label="Sau">{change.after ? <WordSegments segments={change.words.after} side="after" /> : '(trống)'}</pre>
      </div>
    );
  }
  return (
    <div className="ad-change-values">
      <pre className="is-old" aria-label="Trước">{change.before || '(trống)'}</pre>
      <pre className="is-new" aria-label="Sau">{change.after || '(trống)'}</pre>
    </div>
  );
}

function optionsOf(data) {
  return Object.entries(data?.question_data?.options || data?.options || {});
}

function severityLabel(value) {
  return ISSUE_SEVERITY.find((item) => item.value === value)?.label || 'Vừa';
}

function QuestionPane({ question, reviews, chapterLabel }) {
  const correct = new Set(correctAnswerKeys(question));
  const typeKey = questionTypeKey(question);
  const difficulty = difficultyLabel(question.classification?.difficulty);
  const options = optionsOf(question);
  const previousRequest = useMemo(
    () => (isResubmission(question) ? reviews.find((review) => review.decision === 'NEEDS_REVISION') : null),
    [reviews, question],
  );
  const isResubmitted = Boolean(previousRequest);
  // Mốc so sánh là phiên bản gần nhất đã có phiếu duyệt (kể cả câu đã duyệt rồi bị sửa và gửi lại).
  const baseline = useMemo(() => baselineReview(question, reviews), [question, reviews]);
  const hasNewVersion = Boolean(baseline);

  const [showChanges, setShowChanges] = useState(false);
  const [versions, setVersions] = useState(null);
  const [versionError, setVersionError] = useState('');

  useEffect(() => {
    setShowChanges(false);
    setVersions(null);
    setVersionError('');
  }, [question.id, question.current_version]);

  useEffect(() => {
    if (!showChanges || versions) return;
    listQuestionVersions(question.id)
      .then((items) => setVersions(Array.isArray(items) ? items : (items?.items || [])))
      .catch((error) => setVersionError(error.message || 'Không tải được phiên bản trước.'));
  }, [showChanges, versions, question.id]);

  const changes = useMemo(() => {
    if (!versions) return [];
    const sorted = [...versions].sort((a, b) => Number(a.version) - Number(b.version));
    const current = sorted.find((item) => Number(item.version) === Number(question.current_version)) || sorted[sorted.length - 1];
    const previousVersion = baseline?.question_version;
    const older = sorted.filter((item) => Number(item.version) < Number(current?.version));
    const previous = sorted.find((item) => Number(item.version) === Number(previousVersion))
      || older[older.length - 1];
    return diffVersions(previous, current, { chapterLabel });
  }, [versions, question.current_version, baseline, chapterLabel]);

  return (
    <section className="ws-card rv-pane">
      <div className="rv-pane__head">
        <div className="rv-row__top">
          <span className="ws-pill">{questionTypeLabel(typeKey) || 'Chưa rõ dạng'}</span>
          <span className="ws-pill">{bloomText(question)}</span>
          <span className="ws-pill ws-pill--outline">{difficulty || 'Chưa ước lượng độ khó'}</span>
          <span className="ws-pill ws-pill--outline tabular">Phiên bản {question.current_version}</span>
        </div>
        {hasNewVersion && (
          <button type="button" className="ws-link-btn" aria-pressed={showChanges} onClick={() => setShowChanges((value) => !value)}>
            {showChanges
              ? 'Ẩn thay đổi'
              : `Xem thay đổi so với phiên bản ${baseline.question_version} (${REVIEW_DECISION_TEXT[baseline.decision] || 'đã duyệt'})`}
          </button>
        )}
      </div>

      {isResubmitted && (
        <div className="rv-previous">
          <h4>
            {Number(previousRequest.question_version) < Number(question.current_version)
              ? 'Lần trước đã yêu cầu sửa'
              : 'Lần trước đã yêu cầu sửa, giảng viên gửi lại chưa đổi nội dung'}
          </h4>
          {previousRequest.note && <p>{previousRequest.note}</p>}
          {reviewIssuesOf(previousRequest).length > 0 && (
            <ul>
              {reviewIssuesOf(previousRequest).map((issue, index) => (
                <li key={`${issue.title}-${index}`}>
                  <b>{severityLabel(issue.severity)}:</b> {issue.title}
                  {issue.detail && issue.detail !== issue.title ? `. ${issue.detail}` : ''}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {showChanges && (
        <div className="rv-changes">
          {versionError && <p className="ws-field-error">{versionError}</p>}
          {!versions && !versionError && <p className="ws-hint">Đang so sánh phiên bản...</p>}
          {versions && changes.length === 0 && <p className="ws-hint">Không thấy khác biệt về nội dung, phân loại, CLO hay nguồn trích dẫn.</p>}
          {changes.map((change) => (
            <div className="rv-change" key={change.key}>
              <span className="ws-label">{change.label}</span>
              <ChangeBody change={change} />
            </div>
          ))}
        </div>
      )}

      <p className="rv-question-text">{question.content}</p>

      {options.length > 0 && (
        <ul className="rv-options" aria-label="Các phương án">
          {options.map(([key, value]) => {
            const isCorrect = correct.has(String(key).toUpperCase());
            return (
              <li key={key} className={`rv-option ${isCorrect ? 'rv-option--correct' : ''}`}>
                <span className="rv-option__key">{key}</span>
                <p>{String(value)}</p>
                {isCorrect && (
                  <span className="ws-pill ws-pill--success" aria-label="Đáp án đúng">
                    <FontAwesomeIcon icon={faCheck} />
                    <span className="ws-hide-sm">Đáp án</span>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <dl className="rv-answer-grid">
        <div>
          <dt>Đáp án đúng</dt>
          <dd className="rv-answer-key">{question.question_data?.correct_answer || '--'}</dd>
        </div>
        <div>
          <dt>Giải thích</dt>
          <dd>{question.question_data?.explanation || 'Giảng viên chưa ghi giải thích đáp án.'}</dd>
        </div>
      </dl>

      {(question.clos || []).length > 0 && (
        <div className="rv-clos">
          {(question.clos || []).map((clo) => (
            <p key={refId(clo.id || clo)}><b>{clo.code || clo.clo_code || 'CLO'}</b> {clo.description || ''}</p>
          ))}
        </div>
      )}
    </section>
  );
}

export default QuestionPane;
