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

function optionsOf(data) {
  return Object.entries(data?.question_data?.options || data?.options || {});
}

function severityLabel(value) {
  return ISSUE_SEVERITY.find((item) => item.value === value)?.label || 'Vừa';
}

/** So sánh phiên bản hiện tại với phiên bản trước để thấy giảng viên đã sửa gì. */
function diffVersions(previous, current) {
  if (!previous || !current) return [];
  const changes = [];
  if ((previous.content || '') !== (current.content || '')) {
    changes.push({ key: 'content', label: 'Nội dung câu hỏi', before: previous.content, after: current.content });
  }
  const before = previous.question_data || {};
  const after = current.question_data || {};
  const keys = new Set([...Object.keys(before.options || {}), ...Object.keys(after.options || {})]);
  [...keys].sort().forEach((key) => {
    const oldValue = String(before.options?.[key] ?? '');
    const newValue = String(after.options?.[key] ?? '');
    if (oldValue !== newValue) changes.push({ key: `opt-${key}`, label: `Phương án ${key}`, before: oldValue, after: newValue });
  });
  if (String(before.correct_answer || '') !== String(after.correct_answer || '')) {
    changes.push({ key: 'answer', label: 'Đáp án đúng', before: before.correct_answer, after: after.correct_answer });
  }
  if (String(before.explanation || '') !== String(after.explanation || '')) {
    changes.push({ key: 'explanation', label: 'Giải thích', before: before.explanation, after: after.explanation });
  }
  return changes;
}

function QuestionPane({ question, reviews }) {
  const correct = new Set(correctAnswerKeys(question));
  const typeKey = questionTypeKey(question);
  const difficulty = difficultyLabel(question.classification?.difficulty);
  const options = optionsOf(question);
  const previousRequest = useMemo(
    () => (isResubmission(question) ? reviews.find((review) => review.decision === 'NEEDS_REVISION') : null),
    [reviews, question],
  );
  const isResubmitted = Boolean(previousRequest);
  const hasNewVersion = isResubmitted && Number(previousRequest.question_version) < Number(question.current_version);

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
    const previousVersion = previousRequest?.question_version;
    const older = sorted.filter((item) => Number(item.version) < Number(current?.version));
    const previous = sorted.find((item) => Number(item.version) === Number(previousVersion))
      || older[older.length - 1];
    return diffVersions(previous, current);
  }, [versions, question.current_version, previousRequest]);

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
            {showChanges ? 'Ẩn thay đổi' : 'Xem thay đổi so với lần trước'}
          </button>
        )}
      </div>

      {isResubmitted && (
        <div className="rv-previous">
          <h4>{hasNewVersion ? 'Lần trước đã yêu cầu sửa' : 'Lần trước đã yêu cầu sửa, giảng viên gửi lại chưa đổi nội dung'}</h4>
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
          {versions && changes.length === 0 && <p className="ws-hint">Không thấy khác biệt về nội dung, đáp án hay giải thích.</p>}
          {changes.map((change) => (
            <div className="rv-change" key={change.key}>
              <span className="ws-label">{change.label}</span>
              <div className="ad-change-values">
                <pre className="is-old" aria-label="Trước">{change.before || '(trống)'}</pre>
                <pre className="is-new" aria-label="Sau">{change.after || '(trống)'}</pre>
              </div>
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
