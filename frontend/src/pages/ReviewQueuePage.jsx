import React, { useEffect, useMemo, useState } from 'react';
import {
  autoEvaluateQuestion,
  listQuestionEvaluations,
  listQuestionMoodlePublications,
  listQuestionReviews,
  listQuestions,
  publishQuestionToMoodle,
  reviewQuestion,
} from '../api/questions';
import { BLOOM_LEVELS, QUESTION_TYPES, questionTypeLabel } from '../constants/generationEnums';
import '../css/ReviewQueuePage.css';

const REVIEW_STATUS_LABEL = {
  all: 'Tất cả',
  PENDING: 'Chờ duyệt',
  APPROVED: 'Đã duyệt',
  NEEDS_REVISION: 'Cần sửa',
  REJECTED: 'Từ chối',
};

const COLOR_LABEL = {
  all: 'Mọi màu',
  GREEN: 'GREEN',
  YELLOW: 'YELLOW',
  RED: 'RED',
};

function score(value) {
  return typeof value === 'number' ? value.toFixed(2) : '--';
}

function assessmentType(question) {
  return String(question?.classification?.assessment_type || '').toLowerCase();
}

function refId(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  return value.id || value._id || '';
}

function ReviewQueuePage() {
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('PENDING');
  const [typeFilter, setTypeFilter] = useState('all');
  const [bloomFilter, setBloomFilter] = useState('all');
  const [colorFilter, setColorFilter] = useState('all');
  const [minScore, setMinScore] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [selected, setSelected] = useState(null);
  const [evaluations, setEvaluations] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [publications, setPublications] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [busyId, setBusyId] = useState('');
  const [bulkBusy, setBulkBusy] = useState(false);

  const fetchQuestions = async () => {
    setLoading(true);
    setError('');
    try {
      const result = await listQuestions({ page: 1, pageSize: 200 });
      setQuestions(result.items || []);
    } catch (err) {
      setError(err.message || 'Không tải được hàng đợi kiểm duyệt');
    } finally {
      setLoading(false);
    }
  };

  const loadHistory = async (question) => {
    setSelected(question);
    setHistoryLoading(true);
    try {
      const [evaluationResult, reviewResult, publicationResult] = await Promise.all([
        listQuestionEvaluations(question.id),
        listQuestionReviews(question.id),
        listQuestionMoodlePublications(question.id),
      ]);
      setEvaluations(evaluationResult.items || []);
      setReviews(reviewResult.items || []);
      setPublications(publicationResult.items || []);
    } catch (err) {
      setError(err.message || 'Không tải được lịch sử câu hỏi');
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    fetchQuestions();
  }, []);

  useEffect(() => {
    if (!selected) return;
    const fresh = questions.find((item) => item.id === selected.id);
    if (fresh) setSelected(fresh);
  }, [questions, selected]);

  const filteredQuestions = useMemo(() => {
    const search = searchInput.trim().toLowerCase();
    const min = minScore === '' ? null : Number(minScore);
    return questions.filter((question) => {
      if (statusFilter !== 'all' && question.review_status !== statusFilter) return false;
      if (typeFilter !== 'all' && assessmentType(question) !== typeFilter) return false;
      if (bloomFilter !== 'all' && question.classification?.bloom?.level !== Number(bloomFilter)) return false;
      if (colorFilter !== 'all' && question.quality_summary?.color !== colorFilter) return false;
      if (min !== null && Number.isFinite(min) && (question.quality_summary?.overall_score ?? -1) < min) return false;
      if (search && !`${question.question_code} ${question.content}`.toLowerCase().includes(search)) return false;
      return true;
    });
  }, [questions, statusFilter, typeFilter, bloomFilter, colorFilter, minScore, searchInput]);

  const summary = useMemo(() => ({
    pending: questions.filter((item) => item.review_status === 'PENDING').length,
    passed: questions.filter((item) => item.evaluation_status === 'PASSED').length,
    green: questions.filter((item) => item.quality_summary?.color === 'GREEN').length,
    publishable: questions.filter((item) => item.review_status === 'APPROVED' && item.publication_status !== 'PUBLISHED').length,
  }), [questions]);

  const refreshAfterAction = async (question) => {
    await fetchQuestions();
    await loadHistory(question);
  };

  const runEvaluation = async (question) => {
    setBusyId(question.id);
    try {
      await autoEvaluateQuestion(question.id, {
        expected_version: question.current_version,
        evaluator_model_code: 'qwen',
        fallback_to_heuristic: true,
      });
      await refreshAfterAction(question);
    } catch (err) {
      alert('AI evaluation thất bại: ' + err.message);
    } finally {
      setBusyId('');
    }
  };

  const submitReview = async (question, decision) => {
    const note = window.prompt(`Ghi chú ${REVIEW_STATUS_LABEL[decision]} cho ${question.question_code}:`, '');
    if (note === null) return;
    const payload = {
      expected_version: question.current_version,
      decision,
      note,
    };
    if (decision === 'APPROVED' && question.evaluation_status !== 'PASSED') {
      const reason = window.prompt('Câu hỏi chưa pass AI evaluation. Nhập lý do override:', '');
      if (!reason?.trim()) return;
      payload.override = {
        applied: true,
        score: question.quality_summary?.overall_score ?? 0.8,
        color: question.quality_summary?.color || 'YELLOW',
        reason: reason.trim(),
      };
    }
    setBusyId(question.id);
    try {
      await reviewQuestion(question.id, payload);
      await refreshAfterAction(question);
    } catch (err) {
      alert('Kiểm duyệt thất bại: ' + err.message);
    } finally {
      setBusyId('');
    }
  };

  const publish = async (question) => {
    setBusyId(question.id);
    try {
      await publishQuestionToMoodle(question.id, {
        expected_version: question.current_version,
        mock: true,
      });
      await refreshAfterAction(question);
    } catch (err) {
      alert('Đồng bộ Moodle thất bại: ' + err.message);
    } finally {
      setBusyId('');
    }
  };

  const runBulkEvaluate = async () => {
    const targets = filteredQuestions.filter((question) => question.evaluation_status !== 'PASSED').slice(0, 10);
    if (targets.length === 0) return;
    if (!window.confirm(`Chạy AI evaluation cho ${targets.length} câu đang lọc?`)) return;
    setBulkBusy(true);
    try {
      for (const question of targets) {
        await autoEvaluateQuestion(question.id, {
          expected_version: question.current_version,
          evaluator_model_code: 'qwen',
          fallback_to_heuristic: true,
        });
      }
      await fetchQuestions();
    } catch (err) {
      alert('Batch evaluation dừng lại: ' + err.message);
    } finally {
      setBulkBusy(false);
    }
  };

  const runBulkApproveGreen = async () => {
    const targets = filteredQuestions
      .filter((question) => question.evaluation_status === 'PASSED' && question.quality_summary?.color === 'GREEN')
      .slice(0, 10);
    if (targets.length === 0) return;
    const note = window.prompt(`Duyệt ${targets.length} câu GREEN đang lọc. Ghi chú chung:`, 'Batch approve GREEN questions');
    if (note === null) return;
    setBulkBusy(true);
    try {
      for (const question of targets) {
        await reviewQuestion(question.id, {
          expected_version: question.current_version,
          decision: 'APPROVED',
          note,
        });
      }
      await fetchQuestions();
    } catch (err) {
      alert('Batch approve dừng lại: ' + err.message);
    } finally {
      setBulkBusy(false);
    }
  };

  const latestEvaluation = evaluations[0];
  const latestEvidence = latestEvaluation?.evidence || {};
  const latestScores = latestEvaluation?.scores || {};

  return (
    <main className="review-page">
      <section className="review-toolbar">
        <div className="review-toolbar__title">
          <span>Reviewer queue</span>
          <h1>Kiểm duyệt câu hỏi</h1>
        </div>
        <div className="review-actions">
          <button type="button" className="btn btn--outline" disabled={bulkBusy} onClick={runBulkEvaluate}>
            AI đánh giá hàng loạt
          </button>
          <button type="button" className="btn btn--primary" disabled={bulkBusy} onClick={runBulkApproveGreen}>
            Duyệt GREEN
          </button>
        </div>
      </section>

      <section className="review-summary">
        <button type="button" onClick={() => setStatusFilter('PENDING')}>
          <b>{summary.pending}</b>
          <span>Chờ duyệt</span>
        </button>
        <button type="button" onClick={() => setColorFilter('GREEN')}>
          <b>{summary.green}</b>
          <span>GREEN</span>
        </button>
        <button type="button" onClick={() => setMinScore('0.8')}>
          <b>{summary.passed}</b>
          <span>AI đạt</span>
        </button>
        <button type="button" onClick={() => setStatusFilter('APPROVED')}>
          <b>{summary.publishable}</b>
          <span>Chờ Moodle</span>
        </button>
      </section>

      <section className="review-layout">
        <div className="review-list-panel">
          <div className="review-filters">
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              {Object.entries(REVIEW_STATUS_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
              <option value="all">Mọi dạng câu hỏi</option>
              {QUESTION_TYPES.map((type) => (
                <option key={type.backend} value={type.backend}>{type.label}</option>
              ))}
            </select>
            <select value={bloomFilter} onChange={(event) => setBloomFilter(event.target.value)}>
              <option value="all">Mọi Bloom</option>
              {BLOOM_LEVELS.map((level) => (
                <option key={level.level} value={level.level}>{level.label}</option>
              ))}
            </select>
            <select value={colorFilter} onChange={(event) => setColorFilter(event.target.value)}>
              {Object.entries(COLOR_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <input
              type="number"
              min="0"
              max="1"
              step="0.05"
              placeholder="Score tối thiểu"
              value={minScore}
              onChange={(event) => setMinScore(event.target.value)}
            />
            <input
              placeholder="Tìm mã hoặc nội dung..."
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
            />
          </div>

          {error && <p className="review-error">{error}</p>}
          {loading ? (
            <p className="review-empty">Đang tải hàng đợi...</p>
          ) : (
            <div className="review-list">
              {filteredQuestions.map((question) => (
                <article
                  key={question.id}
                  className={`review-row ${selected?.id === question.id ? 'review-row--active' : ''}`}
                  onClick={() => loadHistory(question)}
                >
                  <div>
                    <div className="review-row__meta">
                      <span>{question.question_code}</span>
                      <span>{questionTypeLabel(assessmentType(question))}</span>
                      <span>{question.classification?.bloom?.name || 'Bloom --'}</span>
                      {(question.clos || []).slice(0, 2).map((clo) => (
                        <span className="review-clo-chip" key={refId(clo.id || clo)}>
                          {clo.code || clo.clo_code || 'CLO'}
                        </span>
                      ))}
                    </div>
                    <p>{question.content}</p>
                  </div>
                  <div className="review-row__status">
                    <b className={`quality-${question.quality_summary?.color || 'NONE'}`}>
                      {score(question.quality_summary?.overall_score)}
                    </b>
                    <span>{question.quality_summary?.color || question.evaluation_status}</span>
                    <small>{REVIEW_STATUS_LABEL[question.review_status] || question.review_status}</small>
                  </div>
                </article>
              ))}
              {filteredQuestions.length === 0 && <p className="review-empty">Không có câu hỏi phù hợp bộ lọc.</p>}
            </div>
          )}
        </div>

        <aside className="review-detail-panel">
          {!selected ? (
            <p className="review-empty">Chọn một câu hỏi để xem evidence, source và lịch sử.</p>
          ) : (
            <>
              <div className="detail-head">
                <span>{selected.question_code}</span>
                <h2>{selected.content}</h2>
                {(selected.clos || []).length > 0 && (
                  <div className="detail-clo-list">
                    {selected.clos.map((clo) => (
                      <span key={refId(clo.id || clo)}>
                        <b>{clo.code || clo.clo_code || 'CLO'}</b>
                        {clo.description ? ` - ${clo.description}` : ''}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="detail-actions">
                <button type="button" disabled={busyId === selected.id} onClick={() => runEvaluation(selected)}>AI đánh giá</button>
                <button type="button" disabled={busyId === selected.id} onClick={() => submitReview(selected, 'APPROVED')}>Duyệt</button>
                <button type="button" disabled={busyId === selected.id} onClick={() => submitReview(selected, 'NEEDS_REVISION')}>Cần sửa</button>
                <button type="button" disabled={busyId === selected.id} onClick={() => submitReview(selected, 'REJECTED')}>Từ chối</button>
                <button
                  type="button"
                  disabled={busyId === selected.id || selected.review_status !== 'APPROVED' || selected.publication_status === 'PUBLISHED'}
                  onClick={() => publish(selected)}
                >
                  Moodle
                </button>
              </div>

              {historyLoading ? (
                <p className="review-empty">Đang tải evidence...</p>
              ) : (
                <>
                  <section className="score-grid">
                    {['faithfulness', 'contextual_relevancy', 'answer_relevancy', 'bloom_alignment', 'clo_alignment'].map((key) => (
                      <div key={key}>
                        <span>{key}</span>
                        <b>{score(latestScores[key])}</b>
                      </div>
                    ))}
                  </section>

                  <section className="evidence-block">
                    <h3>Evidence</h3>
                    <p>{latestEvidence.supporting_excerpt || latestEvidence.source_excerpt || 'Chưa có evidence.'}</p>
                    {latestEvidence.reasoning && <span>{latestEvidence.reasoning}</span>}
                    {latestEvidence.fallback_reason && <span>Fallback: {latestEvidence.fallback_reason}</span>}
                  </section>

                  <section className="evidence-block">
                    <h3>Source chunks</h3>
                    {(selected.sources || []).slice(0, 3).map((source, index) => (
                      <p key={source.chunk_id || index}>{source.context_excerpt || source.chunk_id}</p>
                    ))}
                    {(selected.sources || []).length === 0 && <p>Không có source chunk.</p>}
                  </section>

                  <section className="history-grid">
                    <div>
                      <h3>Review history</h3>
                      {reviews.slice(0, 4).map((review) => (
                        <p key={review.id || review._id}><b>{review.decision}</b> {review.note || ''}</p>
                      ))}
                      {reviews.length === 0 && <p>Chưa có review.</p>}
                    </div>
                    <div>
                      <h3>Moodle</h3>
                      {publications.slice(0, 4).map((publication) => (
                        <p key={publication.id || publication._id}><b>{publication.status}</b> {publication.moodle_question_ref_id}</p>
                      ))}
                      {publications.length === 0 && <p>Chưa publish.</p>}
                    </div>
                  </section>
                </>
              )}
            </>
          )}
        </aside>
      </section>
    </main>
  );
}

export default ReviewQueuePage;
