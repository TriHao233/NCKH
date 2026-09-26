import { useState } from 'react';
import { faRobot } from '@fortawesome/free-solid-svg-icons';
import { difficultyLabel } from '../../constants/generationEnums';
import { EmptyState, Notice, SkeletonRows } from '../../components/workspace/Feedback';
import {
  answerGuardrailInsights,
  evaluationInsights,
  metadataGuardrailInsights,
} from '../../utils/reviewAiSuggestions';
import {
  EVALUATION_STATUS_LABEL,
  QUALITY_LABEL,
  REVIEW_CRITERIA,
  evaluationModeLabel,
  formatDateTime,
  formatPercent,
  formatScore,
} from './reviewModel';

const AI_ACTION_LABEL = {
  APPROVE: 'AI đề xuất duyệt',
  NEEDS_REVISION: 'AI đề xuất yêu cầu sửa',
  REJECT: 'AI đề xuất từ chối',
};

const SEVERITY = {
  LOW: { label: 'Lỗi nhẹ', tone: 'info' },
  MEDIUM: { label: 'Lỗi vừa', tone: 'warn' },
  HIGH: { label: 'Lỗi nghiêm trọng', tone: 'danger' },
};

const OPTION_VERDICT = {
  SUPPORTED: { label: 'Nguồn ủng hộ', tone: 'success' },
  CONTRADICTED: { label: 'Mâu thuẫn nguồn', tone: 'danger' },
  NOT_IN_SOURCE: { label: 'Không có trong nguồn', tone: 'warn' },
  AMBIGUOUS: { label: 'Chưa rõ', tone: '' },
};

function textList(value) {
  const values = Array.isArray(value) ? value : (value ? [value] : []);
  return values.map((item) => String(item || '').trim()).filter(Boolean);
}

/** Gom kết quả AI mới nhất và các cờ cảnh báo thành một mô tả dễ dùng cho giao diện. */
export function summarizeEvaluation(question, evaluations) {
  const latest = evaluations?.[0] || null;
  const summary = question?.quality_summary || {};
  const hasError = Boolean(summary.error);
  const evidence = summary.evidence || latest?.evidence || {};
  const feedback = latest?.feedback || summary.feedback || {};
  const scores = hasError ? {} : (latest?.scores || {});
  const merged = latest ? { ...latest, evidence, feedback, scores } : null;
  return {
    latest,
    hasError,
    error: summary.error || null,
    evidence,
    feedback,
    scores,
    weights: latest?.policy?.weights || {},
    overall: hasError ? undefined : (scores.overall ?? summary.overall_score),
    color: hasError ? undefined : (latest?.color || summary.color),
    insights: evaluationInsights(merged, REVIEW_CRITERIA),
    answerGuardrail: answerGuardrailInsights(merged),
    metadataGuardrail: metadataGuardrailInsights(merged),
    modelLabel: summary.evaluator_model_code || latest?.evaluator_model?.model_name || latest?.evaluator_model?.model_code || '--',
    evaluatedAt: latest?.created_at || summary.evaluated_at,
  };
}

function AiPanel({ question, ai, loading }) {
  if (loading) return <SkeletonRows rows={3} lines={2} />;

  const statusLabel = EVALUATION_STATUS_LABEL[question.evaluation_status] || 'Chưa đánh giá';
  if (!ai.latest && !ai.error) {
    return (
      <EmptyState
        compact
        icon={faRobot}
        title={statusLabel}
        description={['QUEUED', 'PROCESSING', 'RUNNING'].includes(question.evaluation_status)
          ? 'AI đang chấm câu hỏi này. Kết quả sẽ hiện ở đây khi hoàn tất.'
          : 'Câu hỏi chưa có kết quả AI. Bạn vẫn có thể tự đánh giá theo 5 tiêu chí.'}
      />
    );
  }

  const action = String(ai.feedback.action || '').toUpperCase();
  const severity = SEVERITY[String(ai.feedback.severity || '').toUpperCase()];
  const weakKeys = new Set(ai.insights.weakCriteria.map((item) => item.key));
  const missing = textList(ai.feedback.missing);
  const risks = textList(ai.evidence.risks);
  const citations = Array.isArray(ai.evidence.citations) ? ai.evidence.citations : [];
  const retrieval = ai.evidence.retrieval || {};

  return (
    <div>
      {ai.error?.message && (
        <div style={{ marginBottom: 14 }}>
          <Notice tone="error">
            {ai.error.code === 'INSUFFICIENT_EVIDENCE'
              ? `Không chấm được vì thiếu nguồn: ${ai.error.message}`
              : ai.error.code === 'EVIDENCE_VALIDATION_FAILED'
                ? `Minh chứng AI không hợp lệ: ${ai.error.message}`
                : `AI gặp lỗi: ${ai.error.message}`}
          </Notice>
        </div>
      )}

      <div className="rv-ai-headline">
        <div className={`rv-ai-score rv-ai-score--${ai.color || 'NONE'}`}>
          <b>{formatScore(ai.overall)}</b>
          <small>{ai.color ? QUALITY_LABEL[ai.color] : statusLabel}</small>
        </div>
        <div className="rv-ai-summary">
          <h4>
            {AI_ACTION_LABEL[action] || (ai.latest?.passed ? 'AI đề xuất đạt' : 'AI đề xuất người duyệt xem lại')}
            {severity && <span className={`ws-pill ws-pill--${severity.tone}`} style={{ marginLeft: 8 }}>{severity.label}</span>}
          </h4>
          <p>{ai.feedback.summary || ai.evidence.reasoning || 'AI không kèm phần giải thích tổng quát.'}</p>
        </div>
      </div>

      {ai.answerGuardrail.applied && (
        <div style={{ marginBottom: 14 }}>
          <Notice tone="warn">
            Hệ thống đã chặn kết luận tự động về đáp án. Đối chiếu từng phương án với nguồn:
            {' '}
            {ai.answerGuardrail.issues.join('; ')}
          </Notice>
        </div>
      )}
      {ai.metadataGuardrail.applied && (
        <div style={{ marginBottom: 14 }}>
          <Notice tone="warn">Thiếu thông tin sư phạm bắt buộc: {ai.metadataGuardrail.issues.join('; ')}</Notice>
        </div>
      )}

      <div className="rv-criteria-scores">
        {REVIEW_CRITERIA.map((criterion) => (
          <div key={criterion.key} className={weakKeys.has(criterion.key) ? 'is-weak' : ''}>
            <span>{criterion.label}</span>
            <b>{formatScore(ai.scores[criterion.key])}</b>
            <small>Trọng số {formatPercent(ai.weights[criterion.key])}</small>
          </div>
        ))}
      </div>

      {ai.insights.uniformScores && (
        <Notice tone="info">Điểm các tiêu chí gần như bằng nhau. Nên đối chiếu minh chứng thay vì chỉ dựa vào tổng điểm.</Notice>
      )}

      {ai.answerGuardrail.optionChecks.length > 0 && (
        <div className="rv-ai-section">
          <h4 className="ws-subhead">Kiểm chứng từng phương án</h4>
          <div className="rv-option-checks">
            {ai.answerGuardrail.optionChecks.map((item) => {
              const verdict = OPTION_VERDICT[item.verdict] || { label: item.verdict || 'Chưa kết luận', tone: '' };
              return (
                <article className="rv-option-check" key={item.key}>
                  <header>
                    <span className="rv-option__key" style={{ width: 24, height: 24 }}>{item.key}</span>
                    <span className={`ws-pill ${verdict.tone ? `ws-pill--${verdict.tone}` : ''}`}>{verdict.label}</span>
                  </header>
                  <p>{item.excerpt || 'AI không kèm trích dẫn.'}</p>
                  {item.inferredFromComplement && <p>Suy ra từ phương án {item.inferredFromComplement}.</p>}
                </article>
              );
            })}
          </div>
        </div>
      )}

      {missing.length > 0 && (
        <div className="rv-ai-section">
          <h4 className="ws-subhead">Nội dung còn thiếu</h4>
          <ul>{missing.slice(0, 6).map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}
      {risks.length > 0 && (
        <div className="rv-ai-section">
          <h4 className="ws-subhead">Rủi ro cần đối chiếu</h4>
          <ul>{risks.slice(0, 6).map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}

      {(citations.length > 0 || ai.evidence.supporting_excerpt) && (
        <div className="rv-ai-section">
          <h4 className="ws-subhead">Minh chứng AI trích dẫn</h4>
          {retrieval.status && (
            <p className="ws-hint" style={{ margin: '0 0 10px' }}>
              Truy xuất nguồn: {retrieval.status === 'SUFFICIENT' ? 'đủ bằng chứng' : 'chưa đủ bằng chứng'},
              {' '}
              {retrieval.eligible_count ?? 0}/{retrieval.result_count ?? 0} đoạn đạt ngưỡng.
            </p>
          )}
          <div className="rv-citations">
            {citations.length === 0 && (
              <article className="rv-citation"><blockquote>{ai.evidence.supporting_excerpt}</blockquote></article>
            )}
            {citations.map((citation, index) => (
              <article className="rv-citation" key={`${citation.chunk_id || 'c'}-${index}`}>
                <header>
                  <span className="ws-code">{citation.chunk_id ? `#${String(citation.chunk_id).slice(-6)}` : `S${index + 1}`}</span>
                  {citation.verified && <span className="ws-pill ws-pill--success">Đã xác minh</span>}
                  {(citation.page_start || citation.page_end) && (
                    <span className="ws-muted">
                      Trang {citation.page_start || citation.page_end}
                      {citation.page_end && citation.page_end !== citation.page_start ? `-${citation.page_end}` : ''}
                    </span>
                  )}
                </header>
                {citation.claim && <p style={{ margin: 0 }}>{citation.claim}</p>}
                {citation.exact_quote && <blockquote>{citation.exact_quote}</blockquote>}
              </article>
            ))}
          </div>
        </div>
      )}

      <hr className="ws-divider" />
      <dl className="ws-kv">
        <div><dt>Mô hình chấm</dt><dd>{ai.modelLabel}</dd></div>
        <div><dt>Cách chấm</dt><dd>{evaluationModeLabel(ai.evidence.mode)}</dd></div>
        <div><dt>Thời điểm</dt><dd>{formatDateTime(ai.evaluatedAt)}</dd></div>
        <div>
          <dt>AI ước lượng độ khó</dt>
          <dd>{difficultyLabel(ai.evidence.assessed_difficulty) || '--'}</dd>
        </div>
      </dl>
    </div>
  );
}

export default AiPanel;

/**
 * Gợi ý AI dạng rút gọn cho cột quyết định: màu, điểm, kết luận, tiêu chí đạt/chưa đạt.
 * Mở rộng để xem minh chứng. Chỉ khi AI lỗi, cũ hoặc thiếu minh chứng mới hiện "AI đánh giá lại".
 */
export function AiSuggestion({ question, ai, loading, onRetry, retrying }) {
  const [expanded, setExpanded] = useState(false);
  const status = question.evaluation_status;
  const busy = ['QUEUED', 'PROCESSING', 'RUNNING'].includes(status);
  const retryable = ['ERROR', 'STALE', 'INSUFFICIENT_EVIDENCE', 'EVIDENCE_VALIDATION_FAILED', 'NOT_STARTED'].includes(status);
  const passMin = ai.insights.passMin;

  return (
    <section className="rv-ai-compact" aria-label="Gợi ý AI">
      <div className="rv-ai-compact__head">
        <div className={`rv-ai-chip rv-ai-chip--${ai.color || 'NONE'}`}>
          <b className="tabular">{formatScore(ai.overall)}</b>
          <span>{ai.color ? QUALITY_LABEL[ai.color] : 'Chưa có điểm'}</span>
        </div>
        <div style={{ minWidth: 0 }}>
          <strong>
            {busy
              ? 'AI đang đánh giá'
              : (ai.latest ? (ai.latest.passed ? 'AI đề xuất đạt' : 'AI đề xuất xem lại') : (EVALUATION_STATUS_LABEL[status] || 'Chưa đánh giá'))}
          </strong>
          <small>Chỉ là gợi ý, bạn là người quyết định.</small>
        </div>
      </div>
      {loading ? (
        <SkeletonRows rows={1} lines={2} />
      ) : (
        <>
          {ai.latest && !ai.hasError && (
            <ul className="rv-ai-criteria">
              {REVIEW_CRITERIA.map((criterion) => {
                const value = ai.scores[criterion.key];
                const known = typeof value === 'number';
                const ok = known && value >= passMin;
                return (
                  <li key={criterion.key} className={known ? (ok ? 'is-ok' : 'is-weak') : ''}>
                    <span>{criterion.label}</span>
                    <b className="tabular">{formatScore(value)}</b>
                  </li>
                );
              })}
            </ul>
          )}
          {retryable && onRetry && (
            <button type="button" className="ws-link-btn" onClick={onRetry} disabled={retrying}>
              {retrying ? 'Đang gửi...' : (status === 'NOT_STARTED' ? 'Gửi AI đánh giá' : 'AI đánh giá lại')}
            </button>
          )}
          {(ai.latest || ai.error) && (
            <button type="button" className="ws-link-btn" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)} style={{ marginLeft: retryable ? 12 : 0 }}>
              {expanded ? 'Thu gọn minh chứng' : 'Xem minh chứng'}
            </button>
          )}
          {expanded && (
            <div className="rv-ai-compact__details">
              <AiPanel question={question} ai={ai} loading={false} />
            </div>
          )}
        </>
      )}
    </section>
  );
}
