import React, { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  autoEvaluateQuestion,
  getQuestion,
  listQuestionEvaluations,
  listQuestions,
  reviewQuestion,
} from '../api/questions';
import { questionTypeLabel } from '../constants/generationEnums';
import '../css/AdminAiReviewPage.css';

const EVALUATION_STATUS_LABEL = {
  NOT_STARTED: 'Chưa đánh giá',
  QUEUED: 'Chờ AI đánh giá',
  PROCESSING: 'Đang đánh giá',
  RUNNING: 'Đang đánh giá',
  PASSED: 'Đạt AI',
  FAILED: 'Chưa đạt AI',
  ERROR: 'AI lỗi',
  STALE: 'Cần đánh giá lại',
};

const REVIEW_STATUS_LABEL = {
  DRAFT: 'Nháp',
  PENDING: 'Chờ duyệt',
  APPROVED: 'Đã duyệt',
  NEEDS_REVISION: 'Cần sửa',
  REJECTED: 'Từ chối',
};

const COLOR_LABEL = {
  GREEN: 'Đạt tốt',
  YELLOW: 'Cần xem lại',
  RED: 'Rủi ro cao',
};

const AI_REVIEW_STATUSES = new Set(['QUEUED', 'PROCESSING', 'RUNNING', 'PASSED', 'FAILED', 'ERROR', 'STALE']);

const SCORE_COMPONENTS = [
  { key: 'faithfulness', label: 'Bám sát nguồn' },
  { key: 'contextual_relevancy', label: 'Phù hợp ngữ cảnh' },
  { key: 'answer_relevancy', label: 'Đáp án phù hợp' },
  { key: 'bloom_alignment', label: 'Đúng Bloom' },
  { key: 'clo_alignment', label: 'Đúng CLO' },
];

function formatScore(value) {
  return typeof value === 'number' ? value.toFixed(2) : '--';
}

function formatDate(value) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--';
  return date.toLocaleString('vi-VN');
}

function evaluationModeLabel(mode) {
  if (mode === 'local_llm') return 'AI cục bộ';
  if (mode === 'heuristic_fallback') return 'Đánh giá dự phòng';
  if (mode === 'heuristic') return 'Chấm nhanh nội bộ';
  return mode || '--';
}

function evaluationStatusLabel(value) {
  return EVALUATION_STATUS_LABEL[value] || value || '--';
}

function reviewStatusLabel(value) {
  return REVIEW_STATUS_LABEL[value] || value || '--';
}

function qualityColorLabel(value) {
  return COLOR_LABEL[value] || value || '--';
}

function evaluatorModelLabel(model = {}, fallback = '') {
  return model.model_code || model.model_name || fallback || '--';
}

function isEvaluationBusy(question) {
  return ['QUEUED', 'PROCESSING', 'RUNNING'].includes(question?.evaluation_status);
}

function canQueueEvaluation(question) {
  return question && !isEvaluationBusy(question) && question.evaluation_status !== 'PASSED';
}

function questionSummary(question) {
  const quality = question?.quality_summary || {};
  if (typeof quality.overall_score === 'number') {
    return `${formatScore(quality.overall_score)} · ${qualityColorLabel(quality.color)}`;
  }
  return evaluationStatusLabel(question?.evaluation_status);
}

function AdminAiReviewPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('active');
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [selected, setSelected] = useState(null);
  const [evaluations, setEvaluations] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [busyId, setBusyId] = useState('');
  const [message, setMessage] = useState('');
  const [openedDeepLinkId, setOpenedDeepLinkId] = useState('');
  const [checkingAll, setCheckingAll] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setSearchTerm(searchInput.trim()), 350);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const fetchAiQuestions = async () => {
    setLoading(true);
    setError('');
    try {
      const evaluationStatus = Array.from(AI_REVIEW_STATUSES).join(',');
      const first = await listQuestions({
        page: 1,
        pageSize: 100,
        search: searchTerm || undefined,
        evaluationStatus,
      });
      const items = [...(first.items || [])];
      const total = first.total || items.length;
      for (let page = 2; items.length < total; page += 1) {
        const next = await listQuestions({
          page,
          pageSize: 100,
          search: searchTerm || undefined,
          evaluationStatus,
        });
        const pageItems = next.items || [];
        if (!pageItems.length) break;
        items.push(...pageItems);
      }
      setQuestions(items);
      return items;
    } catch (err) {
      setError(err.message || 'Không tải được danh sách thẩm định AI');
      return [];
    } finally {
      setLoading(false);
    }
  };

  const loadEvaluationHistory = async (question) => {
    if (!question) return;
    setSelected(question);
    setHistoryLoading(true);
    setMessage('');
    try {
      const result = await listQuestionEvaluations(question.id);
      setEvaluations(result.items || []);
    } catch (err) {
      setMessage(err.message || 'Không tải được kết quả AI');
      setEvaluations([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    fetchAiQuestions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchTerm]);

  useEffect(() => {
    if (!selected) return;
    const fresh = questions.find((question) => question.id === selected.id);
    if (fresh && fresh !== selected) setSelected(fresh);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questions]);

  useEffect(() => {
    if (!questions.some((question) => isEvaluationBusy(question))) return undefined;
    const intervalId = window.setInterval(async () => {
      const items = await fetchAiQuestions();
      if (selected?.id) {
        const fresh = items.find((question) => question.id === selected.id);
        if (fresh) await loadEvaluationHistory(fresh);
      }
    }, 5000);
    return () => window.clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questions, selected?.id, searchTerm]);

  useEffect(() => {
    const questionId = new URLSearchParams(location.search).get('questionId') || '';
    if (!questionId || openedDeepLinkId === questionId) return;
    const openLinkedQuestion = async () => {
      try {
        const items = questions.length ? questions : await fetchAiQuestions();
        const localQuestion = items.find((question) => question.id === questionId);
        const question = localQuestion || await getQuestion(questionId);
        await loadEvaluationHistory(question);
        setOpenedDeepLinkId(questionId);
      } catch (err) {
        setMessage(err.message || 'Không mở được câu hỏi AI');
        setOpenedDeepLinkId(questionId);
      }
    };
    openLinkedQuestion();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search, questions, openedDeepLinkId]);

  const counts = useMemo(() => ({
    active: questions.filter((item) => item.review_status !== 'APPROVED').length,
    processing: questions.filter((item) => isEvaluationBusy(item)).length,
    passed: questions.filter((item) => item.evaluation_status === 'PASSED' && item.review_status !== 'APPROVED').length,
    failed: questions.filter((item) => ['FAILED', 'ERROR', 'STALE'].includes(item.evaluation_status)).length,
    approved: questions.filter((item) => item.review_status === 'APPROVED').length,
  }), [questions]);

  const filtered = useMemo(() => {
    const normalizedSearch = searchTerm.toLowerCase();
    return questions.filter((item) => {
      if (statusFilter === 'active' && item.review_status === 'APPROVED') return false;
      if (statusFilter === 'processing' && !isEvaluationBusy(item)) return false;
      if (statusFilter === 'passed' && !(item.evaluation_status === 'PASSED' && item.review_status !== 'APPROVED')) return false;
      if (statusFilter === 'failed' && !['FAILED', 'ERROR', 'STALE'].includes(item.evaluation_status)) return false;
      if (statusFilter === 'approved' && item.review_status !== 'APPROVED') return false;
      if (!normalizedSearch) return true;
      return [
        item.question_code,
        item.content,
        item.explanation,
      ].filter(Boolean).some((value) => String(value).toLowerCase().includes(normalizedSearch));
    });
  }, [questions, searchTerm, statusFilter]);

  const latestEvaluation = evaluations[0];
  const qualitySummary = selected?.quality_summary || {};
  const latestScores = latestEvaluation?.scores || qualitySummary.scores || {};
  const latestEvidence = latestEvaluation?.evidence || qualitySummary.evidence || {};
  const latestWeights = latestEvaluation?.policy?.weights || qualitySummary.policy?.weights || {};
  const latestModel = latestEvaluation?.evaluator_model || {};
  const overallScore = latestScores.overall ?? qualitySummary.overall_score;
  const evaluationColor = latestEvaluation?.color || qualitySummary.color;

  const refreshSelection = async (questionId) => {
    const items = await fetchAiQuestions();
    const fresh = items.find((item) => item.id === questionId) || selected;
    if (fresh) await loadEvaluationHistory(fresh);
  };

  const runEvaluation = async (question) => {
    setBusyId(question.id);
    setMessage('');
    try {
      await autoEvaluateQuestion(question.id, {
        expected_version: question.current_version,
        fallback_to_heuristic: false,
      });
      setMessage('Đã đưa câu hỏi vào hàng đợi AI đánh giá.');
      await refreshSelection(question.id);
    } catch (err) {
      setMessage(err.message || 'Đánh giá AI thất bại');
    } finally {
      setBusyId('');
    }
  };

  const fetchAllPendingQuestions = async () => {
    const first = await listQuestions({ page: 1, pageSize: 100, reviewStatus: 'PENDING' });
    const items = [...(first.items || [])];
    const total = first.total || items.length;
    for (let page = 2; items.length < total; page += 1) {
      const next = await listQuestions({ page, pageSize: 100, reviewStatus: 'PENDING' });
      const pageItems = next.items || [];
      if (!pageItems.length) break;
      items.push(...pageItems);
    }
    return items;
  };

  const checkAllPending = async () => {
    setCheckingAll(true);
    setMessage('');
    try {
      const pending = await fetchAllPendingQuestions();
      const targets = pending.filter(canQueueEvaluation);
      if (targets.length === 0) {
        setMessage('Không có câu hỏi đang chờ duyệt nào cần kiểm tra AI.');
        return;
      }
      if (!window.confirm(`Đưa ${targets.length} câu hỏi đang chờ duyệt vào hàng đợi kiểm tra AI?`)) {
        return;
      }
      const outcomes = await Promise.allSettled(targets.map((question) => autoEvaluateQuestion(question.id, {
        expected_version: question.current_version,
        fallback_to_heuristic: false,
      })));
      const failed = outcomes.filter((outcome) => outcome.status === 'rejected').length;
      setMessage(failed > 0
        ? `Đã đưa ${targets.length - failed}/${targets.length} câu hỏi vào hàng đợi AI (${failed} lỗi).`
        : `Đã đưa toàn bộ ${targets.length} câu hỏi vào hàng đợi kiểm tra AI.`);
      await fetchAiQuestions();
    } catch (err) {
      setMessage(err.message || 'Kiểm tra toàn bộ thất bại');
    } finally {
      setCheckingAll(false);
    }
  };

  const approveQuestion = async (question) => {
    setBusyId(question.id);
    setMessage('');
    const needsOverride = question.evaluation_status !== 'PASSED';
    const overrideReason = needsOverride
      ? `Admin cho phép sử dụng sau khi xem kết quả AI: ${questionSummary(question)}.`
      : '';
    try {
      await reviewQuestion(question.id, {
        expected_version: question.current_version,
        decision: 'APPROVED',
        note: needsOverride
          ? 'Admin duyệt sau khi xem xét kết quả thẩm định AI, dù AI chưa đánh dấu đạt.'
          : 'Admin duyệt sau khi câu hỏi đạt thẩm định AI.',
        override: {
          applied: needsOverride,
          score: typeof question.quality_summary?.overall_score === 'number'
            ? question.quality_summary.overall_score
            : null,
          color: ['RED', 'YELLOW', 'GREEN'].includes(question.quality_summary?.color)
            ? question.quality_summary.color
            : null,
          reason: overrideReason,
        },
        review_form: {
          checklist: SCORE_COMPONENTS.map((component) => ({
            key: component.key,
            label: component.label,
            passed: true,
            note: '',
          })),
          criterion_assessments: SCORE_COMPONENTS.map((component) => ({
            key: component.key,
            label: component.label,
            rating: 'PASS',
            note: '',
            source_chunk_id: null,
            page_number: null,
          })),
          overall_note: needsOverride
            ? 'Admin quyết định duyệt sau khi cân nhắc kết quả kiểm thử chất lượng của AI.'
            : 'Đạt thẩm định AI và sẵn sàng sử dụng trong ngân hàng câu hỏi.',
          revision_issues: [],
        },
      });
      setMessage('Đã duyệt câu hỏi. Câu hỏi đã sẵn sàng trong tab Câu hỏi.');
      await refreshSelection(question.id);
    } catch (err) {
      setMessage(err.message || 'Duyệt câu hỏi thất bại');
    } finally {
      setBusyId('');
    }
  };

  const requestRevision = async (question) => {
    const reason = window.prompt('Nhập lý do cần chỉnh sửa câu hỏi:', 'Cần rà soát lại theo kết quả thẩm định AI.');
    if (reason === null) return;
    const detail = reason.trim() || 'Cần rà soát lại theo kết quả thẩm định AI.';
    setBusyId(question.id);
    setMessage('');
    try {
      await reviewQuestion(question.id, {
        expected_version: question.current_version,
        decision: 'NEEDS_REVISION',
        note: detail,
        review_form: {
          checklist: SCORE_COMPONENTS.map((component) => ({
            key: component.key,
            label: component.label,
            passed: false,
            note: '',
          })),
          overall_note: detail,
          revision_issues: [{
            title: 'Cần chỉnh sửa sau thẩm định AI',
            severity: 'MEDIUM',
            detail,
          }],
        },
      });
      setMessage('Đã trả câu hỏi về trạng thái cần sửa.');
      await refreshSelection(question.id);
    } catch (err) {
      setMessage(err.message || 'Trả về cần sửa thất bại');
    } finally {
      setBusyId('');
    }
  };

  return (
    <main className="admin-ai-review-page">
      <section className="ai-review-toolbar">
        <div className="ai-review-toolbar__title">
          <span>Quản trị AI</span>
          <h1>Thẩm định bằng AI</h1>
          <p>AI cung cấp điểm và minh chứng tham khảo; Admin hoặc Reviewer vẫn là người quyết định trạng thái sử dụng.</p>
        </div>
        <div className="ai-review-actions">
          <button type="button" className="btn btn--outline" onClick={() => navigate('/quan-ly')}>
            Câu hỏi
          </button>
          <button type="button" className="btn btn--outline" onClick={checkAllPending} disabled={checkingAll || loading}>
            {checkingAll ? 'Đang kiểm tra...' : 'Kiểm tra toàn bộ'}
          </button>
          <button type="button" className="btn btn--primary" onClick={fetchAiQuestions} disabled={loading}>
            {loading ? 'Đang tải' : 'Làm mới'}
          </button>
        </div>
      </section>

      <section className="ai-review-summary" aria-label="Tổng quan thẩm định AI">
        <button type="button" className={statusFilter === 'active' ? 'active' : ''} onClick={() => setStatusFilter('active')}>
          <b>{counts.active}</b>
          <span>Cần xử lý</span>
        </button>
        <button type="button" className={statusFilter === 'processing' ? 'active' : ''} onClick={() => setStatusFilter('processing')}>
          <b>{counts.processing}</b>
          <span>Đang kiểm tra</span>
        </button>
        <button type="button" className={statusFilter === 'passed' ? 'active' : ''} onClick={() => setStatusFilter('passed')}>
          <b>{counts.passed}</b>
          <span>AI đạt</span>
        </button>
        <button type="button" className={statusFilter === 'failed' ? 'active' : ''} onClick={() => setStatusFilter('failed')}>
          <b>{counts.failed}</b>
          <span>Cần xem lại</span>
        </button>
        <button type="button" className={statusFilter === 'approved' ? 'active' : ''} onClick={() => setStatusFilter('approved')}>
          <b>{counts.approved}</b>
          <span>Đã duyệt</span>
        </button>
      </section>

      <section className="ai-review-layout">
        <div className="ai-review-list-panel">
          <div className="ai-review-filters">
            <input
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Tìm mã hoặc nội dung câu hỏi"
            />
          </div>

          {error && <p className="ai-review-error">{error}</p>}
          {message && <p className="ai-review-message">{message}</p>}

          {loading ? (
            <p className="ai-review-empty">Đang tải danh sách thẩm định AI...</p>
          ) : filtered.length === 0 ? (
            <p className="ai-review-empty">Chưa có câu hỏi nào trong nhóm này.</p>
          ) : (
            <div className="ai-review-list">
              {filtered.map((question) => (
                <button
                  type="button"
                  key={question.id}
                  className={`ai-review-row ${selected?.id === question.id ? 'ai-review-row--active' : ''}`}
                  onClick={() => loadEvaluationHistory(question)}
                >
                  <div>
                    <strong>{question.question_code}</strong>
                    <span>{questionTypeLabel(question.question_type)} · Version {question.current_version}</span>
                  </div>
                  <p>{question.content}</p>
                  <div className="ai-review-row__meta">
                    <span>{evaluationStatusLabel(question.evaluation_status)}</span>
                    <span>{reviewStatusLabel(question.review_status)}</span>
                    <b className={`quality-${question.quality_summary?.color || 'NONE'}`}>{questionSummary(question)}</b>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <aside className="ai-review-detail-panel">
          {!selected ? (
            <p className="ai-review-empty">Chọn một câu hỏi để xem kết quả thẩm định AI.</p>
          ) : (
            <>
              <div className="ai-review-detail-head">
                <div>
                  <span>{selected.question_code}</span>
                  <h2>{questionTypeLabel(selected.question_type)}</h2>
                </div>
                <button type="button" className="btn btn--outline" onClick={() => navigate(`/quan-ly?questionId=${selected.id}`)}>
                  Mở bên Câu hỏi
                </button>
              </div>

              <div className="ai-review-question">
                <p>{selected.content}</p>
                {selected.explanation && <small>{selected.explanation}</small>}
              </div>

              <div className="ai-review-detail-actions">
                <button type="button" disabled={busyId === selected.id || !canQueueEvaluation(selected)} onClick={() => runEvaluation(selected)}>
                  {['FAILED', 'ERROR', 'STALE'].includes(selected.evaluation_status) ? 'Thử lại AI' : 'Chạy AI'}
                </button>
                <button
                  type="button"
                  className="primary"
                  disabled={busyId === selected.id || isEvaluationBusy(selected) || selected.review_status !== 'PENDING'}
                  onClick={() => approveQuestion(selected)}
                >
                  Duyệt
                </button>
                <button
                  type="button"
                  disabled={busyId === selected.id || selected.review_status !== 'PENDING'}
                  onClick={() => requestRevision(selected)}
                >
                  Cần sửa
                </button>
              </div>

              {historyLoading ? (
                <p className="ai-review-empty">Đang tải kết quả AI...</p>
              ) : (
                <section className="ai-evaluation-panel">
                  <div className="ai-evaluation-total">
                    <div>
                      <span>Tổng điểm</span>
                      <b className={`quality-${evaluationColor || 'NONE'}`}>{formatScore(overallScore)}</b>
                    </div>
                    <div>
                      <span>Kết luận</span>
                      <strong>{latestEvaluation ? (latestEvaluation.passed ? 'Đạt' : 'Chưa đạt') : evaluationStatusLabel(selected.evaluation_status)}</strong>
                    </div>
                    <div>
                      <span>Mức chất lượng</span>
                      <strong>{qualityColorLabel(evaluationColor)}</strong>
                    </div>
                    <div>
                      <span>Cách đánh giá</span>
                      <strong>{evaluationModeLabel(latestEvidence.mode)}</strong>
                    </div>
                  </div>

                  <div className="ai-score-grid">
                    {SCORE_COMPONENTS.map((component) => (
                      <div key={component.key}>
                        <span>{component.label}</span>
                        <b>{formatScore(latestScores[component.key])}</b>
                        <small>Trọng số {formatScore(latestWeights[component.key])}</small>
                      </div>
                    ))}
                  </div>

                  <div className="ai-evaluation-meta">
                    <span>Mô hình: <b>{evaluatorModelLabel(latestModel, qualitySummary.evaluator_model_code)}</b></span>
                    <span>Bộ tiêu chí: <b>{latestEvaluation?.policy?.name || '--'}</b></span>
                    <span>Đánh giá lúc: <b>{formatDate(latestEvaluation?.created_at || qualitySummary.evaluated_at)}</b></span>
                  </div>

                  <div className="ai-evidence-block">
                    <h3>Minh chứng AI</h3>
                    <p>{latestEvidence.supporting_excerpt || latestEvidence.source_excerpt || 'Chưa có minh chứng.'}</p>
                    {latestEvidence.reasoning && <span>{latestEvidence.reasoning}</span>}
                    {qualitySummary.error?.message && <span>Lỗi AI: {qualitySummary.error.message}</span>}
                  </div>
                </section>
              )}
            </>
          )}
        </aside>
      </section>
    </main>
  );
}

export default AdminAiReviewPage;
