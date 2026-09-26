import { useEffect, useMemo, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faPlus, faTrashCan } from '@fortawesome/free-solid-svg-icons';
import { Notice } from '../../components/workspace/Feedback';
import {
  DEFAULT_REVIEW_COMMENT_TEMPLATES,
  encodeSavedReviewTemplates,
  parseSavedReviewTemplates,
  reviewTemplateStorageKey,
  templatesForDecision,
} from '../../utils/reviewCommentTemplates';
import {
  CRITERION_RATINGS,
  ISSUE_SEVERITY,
  REVIEW_CRITERIA,
  differsFromAi,
  formatScore,
  isAwaitingSecondary,
  isBlockedFromSecondary,
  isEvaluationBusy,
  needsOverride,
  pageRangeLabel,
} from './reviewModel';

function readTemplates(user) {
  try {
    return parseSavedReviewTemplates(localStorage.getItem(reviewTemplateStorageKey(user)));
  } catch {
    return [];
  }
}

function writeTemplates(user, templates) {
  try {
    localStorage.setItem(reviewTemplateStorageKey(user), encodeSavedReviewTemplates(templates));
  } catch {
    // Trình duyệt chặn lưu trữ: mẫu chỉ tồn tại trong phiên hiện tại.
  }
}

function SourceSelect({ sources, value, onChange, label }) {
  if (!sources.length) return null;
  return (
    <select className="ws-select rv-mini-select" value={value} onChange={(event) => onChange(event.target.value)} aria-label={label}>
      <option value="">Không gắn nguồn</option>
      {sources.map((source, index) => (
        <option key={source.chunk_id || index} value={source.chunk_id || ''}>
          Nguồn {source.citation_order || index + 1}, {pageRangeLabel(source.page_range)}
        </option>
      ))}
    </select>
  );
}

/**
 * Phiếu kiểm duyệt đặt ngay trong cột phải của Bàn duyệt (không dùng modal).
 * Trạng thái phiếu do trang cha giữ để tự lưu nháp và gửi đi.
 */
function DecisionPanel({
  question,
  user,
  draft,
  onDraftChange,
  onDecide,
  submitting,
  error,
  saveState,
  aiScores,
  sources,
  continueNext,
  onContinueNextChange,
  onApplyAi,
  canApplyAi,
  onDiscard,
}) {
  const [customTemplates, setCustomTemplates] = useState(() => readTemplates(user));
  const [compareOpen, setCompareOpen] = useState(false);

  useEffect(() => {
    setCustomTemplates(readTemplates(user));
  }, [user]);

  const mode = draft.decision;
  const templates = useMemo(
    () => templatesForDecision([...DEFAULT_REVIEW_COMMENT_TEMPLATES, ...customTemplates], mode),
    [customTemplates, mode],
  );
  const secondaryBlocked = isBlockedFromSecondary(question, user);
  const awaitingSecondary = isAwaitingSecondary(question);
  const aiBusy = isEvaluationBusy(question);
  const checkedCount = (draft.checklist || []).filter((item) => item.passed).length;

  const update = (patch) => onDraftChange({ ...draft, ...patch });
  const updateCriterion = (key, patch) => update({
    criteria: draft.criteria.map((item) => (item.key === key ? { ...item, ...patch, touched: true } : item)),
  });
  const updateIssue = (id, patch) => update({
    issues: draft.issues.map((issue) => (issue.id === id ? { ...issue, ...patch } : issue)),
  });
  const addIssue = () => update({
    issues: [...draft.issues, { id: `issue-${Date.now()}`, title: '', severity: 'MEDIUM', detail: '', source_chunk_id: '', page_number: '' }],
  });

  const applyTemplate = (template) => {
    const current = String(draft.overallNote || '').trim();
    update({ overallNote: current ? `${current}\n${template.body}` : template.body });
  };

  const saveTemplate = () => {
    const body = String(draft.overallNote || '').trim();
    if (!body) return;
    const next = [
      { id: `tpl-${Date.now()}`, title: body.split('\n')[0].slice(0, 60), body, decision: mode, updated_at: new Date().toISOString() },
      ...customTemplates,
    ].slice(0, 20);
    setCustomTemplates(next);
    writeTemplates(user, next);
  };

  const removeTemplate = (id) => {
    const next = customTemplates.filter((template) => template.id !== id);
    setCustomTemplates(next);
    writeTemplates(user, next);
  };

  const aiLine = question.evaluation_status === 'PASSED'
    ? 'AI đề xuất đạt.'
    : question.evaluation_status === 'FAILED'
      ? 'AI đề xuất xem lại. Nếu vẫn duyệt, bạn cần ghi lý do.'
      : 'Chưa có gợi ý AI hợp lệ. Bạn tự đánh giá theo danh sách kiểm tra.';

  return (
    <div className="rv-decision">
      <div className="ws-field">
        <div className="rv-section-head">
          <span className="ws-label">Danh sách kiểm tra</span>
          <span className="ws-hint tabular">{checkedCount}/{draft.checklist.length}</span>
        </div>
        <ul className="rv-checklist">
          {draft.checklist.map((item) => (
            <li key={item.key}>
              <label className="ws-check">
                <input
                  type="checkbox"
                  checked={item.passed}
                  onChange={(event) => update({
                    checklist: draft.checklist.map((entry) => (entry.key === item.key ? { ...entry, passed: event.target.checked } : entry)),
                  })}
                />
                <span>{item.label}</span>
              </label>
            </li>
          ))}
        </ul>
      </div>

      <div className="ws-field">
        <label className="ws-label" htmlFor="review-note">{mode === 'REJECTED' ? 'Lý do từ chối' : 'Nhận xét gửi giảng viên'}</label>
        {templates.length > 0 && (
          <div className="rv-templates">
            {templates.map((template) => (
              <span key={template.id} className="rv-template-wrap">
                <button type="button" className="rv-template" title={template.body} onClick={() => applyTemplate(template)}>
                  {template.title}
                </button>
                {!template.built_in && (
                  <button type="button" className="rv-template-remove" aria-label={`Xoá mẫu ${template.title}`} onClick={() => removeTemplate(template.id)}>
                    <FontAwesomeIcon icon={faTrashCan} />
                  </button>
                )}
              </span>
            ))}
          </div>
        )}
        <textarea
          id="review-note"
          className="ws-textarea"
          value={draft.overallNote}
          maxLength={2000}
          onChange={(event) => update({ overallNote: event.target.value })}
          placeholder={mode === 'APPROVED' ? 'Không bắt buộc khi duyệt' : 'Giảng viên sẽ thấy nhận xét này'}
        />
        <div className="rv-section-head">
          <button type="button" className="rv-note-link" onClick={saveTemplate} disabled={!String(draft.overallNote || '').trim()}>
            Lưu làm mẫu nhận xét
          </button>
          <span className="rv-save-state" aria-live="polite">{saveState}</span>
        </div>
      </div>

      {(mode === 'NEEDS_REVISION' || draft.issues.length > 0) && (
        <div className="ws-field">
          <div className="rv-section-head">
            <span className="ws-label">Lỗi cần giảng viên sửa{mode === 'NEEDS_REVISION' ? ' (bắt buộc)' : ''}</span>
            <button type="button" className="btn btn--outline btn--sm" onClick={addIssue} disabled={draft.issues.length >= 20}>
              <FontAwesomeIcon icon={faPlus} />
              Thêm lỗi
            </button>
          </div>
          {draft.issues.length === 0 && <small>Liệt kê từng điểm cần sửa để giảng viên xử lý nhanh.</small>}
          <div className="rv-issues">
            {draft.issues.map((issue, index) => (
              <div className="rv-issue" key={issue.id}>
                <input
                  className="ws-input"
                  value={issue.title}
                  maxLength={160}
                  onChange={(event) => updateIssue(issue.id, { title: event.target.value })}
                  placeholder={`Lỗi ${index + 1}, ví dụ: Phương án B cũng đúng`}
                  aria-label={`Tiêu đề lỗi ${index + 1}`}
                />
                <select className="ws-select" value={issue.severity} onChange={(event) => updateIssue(issue.id, { severity: event.target.value })} aria-label={`Mức độ lỗi ${index + 1}`}>
                  {ISSUE_SEVERITY.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
                <button type="button" className="ws-icon-btn ws-icon-btn--danger" onClick={() => update({ issues: draft.issues.filter((entry) => entry.id !== issue.id) })} aria-label={`Xoá lỗi ${index + 1}`}>
                  <FontAwesomeIcon icon={faTrashCan} />
                </button>
                <textarea
                  className="ws-textarea"
                  value={issue.detail}
                  maxLength={1000}
                  onChange={(event) => updateIssue(issue.id, { detail: event.target.value })}
                  placeholder="Mô tả và cách sửa gợi ý"
                  aria-label={`Chi tiết lỗi ${index + 1}`}
                />
                <div className="rv-issue__meta">
                  <SourceSelect sources={sources} value={issue.source_chunk_id} onChange={(value) => updateIssue(issue.id, { source_chunk_id: value })} label={`Nguồn lỗi ${index + 1}`} />
                  <input
                    className="ws-input"
                    type="number"
                    min="1"
                    inputMode="numeric"
                    value={issue.page_number}
                    onChange={(event) => updateIssue(issue.id, { page_number: event.target.value })}
                    placeholder="Trang"
                    aria-label={`Trang lỗi ${index + 1}`}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {needsOverride(question, draft) && (
        <label className="ws-field">
          <span>Lý do duyệt khác gợi ý AI (bắt buộc)</span>
          <textarea
            className="ws-textarea"
            value={draft.overrideReason}
            maxLength={500}
            onChange={(event) => update({ overrideReason: event.target.value })}
            placeholder="Ví dụ: Đã đối chiếu trang 12, đáp án đúng; AI thiếu ngữ cảnh."
          />
        </label>
      )}

      <div className="rv-compare">
        <button type="button" className="rv-compare__toggle" aria-expanded={compareOpen} onClick={() => setCompareOpen((value) => !value)}>
          So sánh chi tiết với AI theo 5 tiêu chí
          <span className="ws-hint">{compareOpen ? 'Thu gọn' : 'Mở'}</span>
        </button>
        {compareOpen && (
          <div className="rv-criteria">
            <p className="ws-hint" style={{ margin: 0 }}>
              Tiêu chí bạn không chấm sẽ tự lấy theo kết luận (Duyệt: Đạt, còn lại: Xem lại).
              {canApplyAi && (
                <>
                  {' '}
                  <button type="button" className="ws-link-btn" onClick={onApplyAi}>Điền theo gợi ý AI</button>
                </>
              )}
            </p>
            {REVIEW_CRITERIA.map((criterion) => {
              const item = draft.criteria.find((entry) => entry.key === criterion.key) || {};
              return (
                <div className="rv-criterion" key={criterion.key}>
                  <header>
                    <div>
                      <b>{criterion.label}</b>
                      <small>{criterion.description}</small>
                    </div>
                    <div className="rv-criterion__ai">AI<b>{formatScore(aiScores?.[criterion.key])}</b></div>
                  </header>
                  <div className="rv-rating" role="radiogroup" aria-label={`Đánh giá ${criterion.label}`}>
                    {CRITERION_RATINGS.map((rating) => (
                      <button
                        key={rating.value}
                        type="button"
                        data-rating={rating.value}
                        aria-pressed={item.touched ? item.rating === rating.value : false}
                        onClick={() => updateCriterion(criterion.key, { rating: rating.value })}
                      >
                        {rating.label}
                      </button>
                    ))}
                  </div>
                  <input
                    className="ws-input"
                    value={item.note || ''}
                    maxLength={1000}
                    onChange={(event) => updateCriterion(criterion.key, { note: event.target.value, rating: item.rating })}
                    placeholder="Nhận xét cho tiêu chí (không bắt buộc)"
                    aria-label={`Nhận xét ${criterion.label}`}
                  />
                  <SourceSelect sources={sources} value={item.source_chunk_id || ''} onChange={(value) => updateCriterion(criterion.key, { source_chunk_id: value, rating: item.rating })} label={`Nguồn cho ${criterion.label}`} />
                </div>
              );
            })}
          </div>
        )}
      </div>

      {!awaitingSecondary && (
        <div className="ws-field">
          <label className="ws-check">
            <input type="checkbox" checked={Boolean(draft.secondaryRequired)} onChange={(event) => update({ secondaryRequired: event.target.checked })} />
            Cần người thứ hai duyệt lại (vòng 2) khi duyệt
          </label>
          {draft.secondaryRequired && (
            <textarea
              className="ws-textarea"
              value={draft.secondaryReason}
              maxLength={500}
              onChange={(event) => update({ secondaryReason: event.target.value })}
              placeholder="Lý do cần duyệt vòng 2"
              aria-label="Lý do cần duyệt vòng 2"
            />
          )}
        </div>
      )}
      {awaitingSecondary && (
        <Notice tone="info">
          {secondaryBlocked
            ? 'Bạn đã duyệt vòng 1 câu này. Chỉ có thể yêu cầu sửa hoặc từ chối; cần người khác duyệt vòng 2.'
            : 'Đây là lượt duyệt vòng 2. Duyệt sẽ đưa câu hỏi vào ngân hàng chính thức.'}
        </Notice>
      )}

      {error && <Notice tone="error">{error}</Notice>}

      <div className="rv-decide">
        <p className="rv-decide__hint">
          {aiLine}
          {differsFromAi(question, mode) && <b> Kết luận đang chọn khác gợi ý AI.</b>}
        </p>
        <button
          type="button"
          className="btn btn--primary"
          disabled={submitting || secondaryBlocked || aiBusy}
          title={secondaryBlocked ? 'Bạn đã duyệt vòng 1, cần người khác duyệt vòng 2' : (aiBusy ? 'Chờ AI đánh giá xong' : 'Phím tắt A')}
          onClick={() => onDecide('APPROVED')}
        >
          {submitting && mode === 'APPROVED' ? 'Đang lưu...' : 'Duyệt'}
        </button>
        <div className="rv-decide__row">
          <button
            type="button"
            className={`btn btn--outline ${mode === 'NEEDS_REVISION' ? 'is-active' : ''}`}
            disabled={submitting}
            title="Phím tắt R"
            onClick={() => onDecide('NEEDS_REVISION')}
          >
            {submitting && mode === 'NEEDS_REVISION' ? 'Đang gửi...' : (mode === 'NEEDS_REVISION' ? 'Gửi yêu cầu sửa' : 'Yêu cầu sửa')}
          </button>
          <button type="button" className="btn btn--danger" disabled={submitting} onClick={() => onDecide('REJECTED')}>
            {submitting && mode === 'REJECTED' ? 'Đang lưu...' : 'Từ chối'}
          </button>
        </div>
        <label className="ws-check" style={{ fontSize: '0.82rem' }}>
          <input type="checkbox" checked={continueNext} onChange={(event) => onContinueNextChange(event.target.checked)} />
          Tự chuyển sang câu tiếp theo sau khi quyết định
        </label>
        <div className="rv-section-head">
          <span className="rv-kbd-hint">
            <kbd className="ws-kbd">A</kbd> duyệt <kbd className="ws-kbd">R</kbd> yêu cầu sửa <kbd className="ws-kbd">J</kbd>/<kbd className="ws-kbd">K</kbd> câu sau/trước <kbd className="ws-kbd">Esc</kbd> về Hộp việc
          </span>
        </div>
        <button type="button" className="ws-link-btn" style={{ alignSelf: 'flex-start' }} onClick={onDiscard} disabled={submitting}>
          Xoá phiếu nháp
        </button>
      </div>
    </div>
  );
}

export default DecisionPanel;
