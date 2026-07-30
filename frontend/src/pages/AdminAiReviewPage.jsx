import React, { useEffect, useMemo, useRef, useState } from 'react';
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

const AI_REVIEW_STATUSES = new Set([
  'NOT_STARTED',
  'QUEUED',
  'PROCESSING',
  'RUNNING',
  'PASSED',
  'FAILED',
  'ERROR',
  'STALE',
]);
const COMPLETED_REVIEW_STATUSES = new Set(['APPROVED', 'NEEDS_REVISION', 'REJECTED']);
const RISK_EVALUATION_STATUSES = new Set(['FAILED', 'ERROR', 'STALE']);

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
  return (
    question
    && question.review_status === 'PENDING'
    && !isEvaluationBusy(question)
    && question.evaluation_status !== 'PASSED'
  );
}

function modelRuntimeLabel(code) {
  const normalized = String(code || 'deepseek-r1').toLowerCase();
  if (normalized === 'gemini') return 'Gemini API';
  if (normalized.startsWith('ollama:')) {
    return `${normalized.slice('ollama:'.length)} · Ollama cục bộ`;
  }
  if (normalized.includes('deepseek') || normalized.includes('qwen')) {
    return `${code || 'deepseek-r1'} · Ollama cục bộ`;
  }
  return code || 'Mô hình mặc định';
}

function matchesStatusFilter(question, filter) {
  if (filter === 'pending') return question.review_status === 'PENDING';
  if (filter === 'unscored') {
    return question.review_status === 'PENDING'
      && question.evaluation_status === 'NOT_STARTED';
  }
  if (filter === 'processing') {
    return question.review_status === 'PENDING' && isEvaluationBusy(question);
  }
  if (filter === 'risk') {
    return question.review_status === 'PENDING'
      && RISK_EVALUATION_STATUSES.has(question.evaluation_status);
  }
  if (filter === 'completed') return COMPLETED_REVIEW_STATUSES.has(question.review_status);
  return true;
}

function riskRank(question) {
  if (question.evaluation_status === 'ERROR') return 0;
  if (question.evaluation_status === 'FAILED') return 1;
  if (question.evaluation_status === 'STALE') return 2;
  if (question.evaluation_status === 'NOT_STARTED') return 3;
  if (isEvaluationBusy(question)) return 4;
  if (question.evaluation_status === 'PASSED') return 5;
  return 6;
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
  const [statusFilter, setStatusFilter] = useState('pending');
  const [qualityFilter, setQualityFilter] = useState('all');
  const [sortOrder, setSortOrder] = useState('risk');
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [selected, setSelected] = useState(null);
  const [evaluations, setEvaluations] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [busyId, setBusyId] = useState('');
  const [message, setMessage] = useState('');
  const [openedDeepLinkId, setOpenedDeepLinkId] = useState('');
  const [checkingAll, setCheckingAll] = useState(false);
  const [actionDialog, setActionDialog] = useState(null);
  const [actionReason, setActionReason] = useState('');
  const [dialogError, setDialogError] = useState('');
  const [approvalChecklist, setApprovalChecklist] = useState(
    () => Object.fromEntries(SCORE_COMPONENTS.map((component) => [component.key, false])),
  );
  const evaluationRequestRef = useRef(0);

  useEffect(() => {
    const timer = setTimeout(() => setSearchTerm(searchInput.trim()), 350);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const fetchAiQuestions = async () => {
    setLoading(true);
    setError('');
    try {
      const result = await listQuestions({ page: 1, pageSize: 100, search: searchTerm || undefined });
      const items = (result.items || []).filter((item) => (
        AI_REVIEW_STATUSES.has(item.evaluation_status)
        && item.review_status !== 'DRAFT'
      ));
      setQuestions(items);
      return items;
    } catch (err) {
      setError(err.message || 'Không tải được danh sách duyệt AI');
      return [];
    } finally {
      setLoading(false);
    }
  };

  const loadEvaluationHistory = async (question) => {
    if (!question) return;
    const requestId = evaluationRequestRef.current + 1;
    evaluationRequestRef.current = requestId;
    setSelected(question);
    setHistoryLoading(true);
    setMessage('');
    try {
      const result = await listQuestionEvaluations(question.id);
      if (evaluationRequestRef.current !== requestId) return;
      setEvaluations(result.items || []);
    } catch (err) {
      if (evaluationRequestRef.current !== requestId) return;
      setMessage(err.message || 'Không tải được kết quả AI');
      setEvaluations([]);
    } finally {
      if (evaluationRequestRef.current === requestId) setHistoryLoading(false);
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
    if (!actionDialog) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const closeOnEscape = (event) => {
      if (event.key === 'Escape' && !busyId && !checkingAll) {
        setActionDialog(null);
        setDialogError('');
      }
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', closeOnEscape);
    };
  }, [actionDialog, busyId, checkingAll]);

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
    pending: questions.filter((item) => item.review_status === 'PENDING').length,
    unscored: questions.filter((item) => (
      item.review_status === 'PENDING' && item.evaluation_status === 'NOT_STARTED'
    )).length,
    processing: questions.filter((item) => (
      item.review_status === 'PENDING' && isEvaluationBusy(item)
    )).length,
    risk: questions.filter((item) => (
      item.review_status === 'PENDING'
      && RISK_EVALUATION_STATUSES.has(item.evaluation_status)
    )).length,
    completed: questions.filter((item) => COMPLETED_REVIEW_STATUSES.has(item.review_status)).length,
  }), [questions]);

  const filtered = useMemo(() => {
    const normalizedSearch = searchTerm.toLowerCase();
    const items = questions.filter((item) => {
      if (!matchesStatusFilter(item, statusFilter)) return false;
      const scoreValue = item.quality_summary?.overall_score;
      if (qualityFilter === 'UNSCORED' && typeof scoreValue === 'number') return false;
      if (
        ['GREEN', 'YELLOW', 'RED'].includes(qualityFilter)
        && item.quality_summary?.color !== qualityFilter
      ) return false;
      if (!normalizedSearch) return true;
      return [
        item.question_code,
        item.content,
        item.explanation,
      ].filter(Boolean).some((value) => String(value).toLowerCase().includes(normalizedSearch));
    });
    return [...items].sort((left, right) => {
      const leftScore = left.quality_summary?.overall_score;
      const rightScore = right.quality_summary?.overall_score;
      if (sortOrder === 'score_asc') {
        return (typeof leftScore === 'number' ? leftScore : 2)
          - (typeof rightScore === 'number' ? rightScore : 2);
      }
      if (sortOrder === 'score_desc') {
        return (typeof rightScore === 'number' ? rightScore : -1)
          - (typeof leftScore === 'number' ? leftScore : -1);
      }
      if (sortOrder === 'newest') {
        return new Date(right.updated_at || right.created_at || 0)
          - new Date(left.updated_at || left.created_at || 0);
      }
      const rankDifference = riskRank(left) - riskRank(right);
      if (rankDifference !== 0) return rankDifference;
      return (typeof leftScore === 'number' ? leftScore : 2)
        - (typeof rightScore === 'number' ? rightScore : 2);
    });
  }, [qualityFilter, questions, searchTerm, sortOrder, statusFilter]);

  useEffect(() => {
    if (filtered.length === 0) {
      setSelected(null);
      setEvaluations([]);
      return;
    }
    if (!selected || !filtered.some((question) => question.id === selected.id)) {
      loadEvaluationHistory(filtered[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtered, selected]);

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

  const applyDefaultFilters = () => {
    setStatusFilter('pending');
    setQualityFilter('all');
    setSortOrder('risk');
    setSearchInput('');
    setSearchTerm('');
  };

  const openActionDialog = (type, question = null, targets = []) => {
    setActionDialog({ type, question, targets });
    setActionReason('');
    setDialogError('');
    setApprovalChecklist(
      Object.fromEntries(SCORE_COMPONENTS.map((component) => [component.key, false])),
    );
  };

  const closeActionDialog = () => {
    if (busyId || checkingAll) return;
    setActionDialog(null);
    setDialogError('');
  };

  const runEvaluation = async (question) => {
    setBusyId(question.id);
    setMessage('');
    setDialogError('');
    try {
      await autoEvaluateQuestion(question.id, {
        expected_version: question.current_version,
        fallback_to_heuristic: false,
      });
      setMessage('Đã đưa câu hỏi vào hàng đợi AI đánh giá.');
      setActionDialog(null);
      await refreshSelection(question.id);
    } catch (err) {
      setDialogError(err.message || 'Đánh giá AI thất bại');
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

  const prepareBulkEvaluation = async () => {
    setCheckingAll(true);
    setMessage('');
    try {
      const pending = await fetchAllPendingQuestions();
      const targets = pending.filter(canQueueEvaluation);
      if (targets.length === 0) {
        setMessage('Không có câu hỏi đang chờ duyệt nào cần kiểm tra AI.');
        return;
      }
      openActionDialog('bulk-evaluate', null, targets);
    } catch (err) {
      setMessage(err.message || 'Không tải được câu hỏi cần kiểm tra');
    } finally {
      setCheckingAll(false);
    }
  };

  const runBulkEvaluation = async (targets) => {
    setCheckingAll(true);
    setDialogError('');
    setMessage('');
    try {
      const outcomes = await Promise.allSettled(targets.map((question) => autoEvaluateQuestion(question.id, {
        expected_version: question.current_version,
        fallback_to_heuristic: false,
      })));
      const failed = outcomes.filter((outcome) => outcome.status === 'rejected').length;
      setMessage(failed > 0
        ? `Đã đưa ${targets.length - failed}/${targets.length} câu hỏi vào hàng đợi AI (${failed} lỗi).`
        : `Đã đưa toàn bộ ${targets.length} câu hỏi vào hàng đợi kiểm tra AI.`);
      setActionDialog(null);
      await fetchAiQuestions();
    } catch (err) {
      setDialogError(err.message || 'Kiểm tra toàn bộ thất bại');
    } finally {
      setCheckingAll(false);
    }
  };

  const approveQuestion = async (question, checklist, reason) => {
    setBusyId(question.id);
    setDialogError('');
    setMessage('');
    const needsOverride = question.evaluation_status !== 'PASSED';
    const overrideReason = needsOverride
      ? reason.trim()
      : '';
    try {
      await reviewQuestion(question.id, {
        expected_version: question.current_version,
        decision: 'APPROVED',
        note: needsOverride
          ? reason.trim()
          : 'Đã duyệt sau thẩm định AI.',
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
            passed: Boolean(checklist[component.key]),
            note: '',
          })),
          overall_note: needsOverride
            ? reason.trim()
            : 'Đạt thẩm định AI và sẵn sàng sử dụng trong ngân hàng câu hỏi.',
          revision_issues: [],
        },
      });
      setMessage('Đã duyệt câu hỏi. Câu hỏi đã sẵn sàng trong tab Câu hỏi.');
      setActionDialog(null);
      await refreshSelection(question.id);
    } catch (err) {
      setDialogError(err.message || 'Duyệt câu hỏi thất bại');
    } finally {
      setBusyId('');
    }
  };

  const requestRevision = async (question, reason) => {
    const detail = reason.trim();
    setBusyId(question.id);
    setDialogError('');
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
      setActionDialog(null);
      await refreshSelection(question.id);
    } catch (err) {
      setDialogError(err.message || 'Trả về cần sửa thất bại');
    } finally {
      setBusyId('');
    }
  };

  const rejectQuestion = async (question, reason) => {
    const detail = reason.trim();
    setBusyId(question.id);
    setDialogError('');
    setMessage('');
    try {
      await reviewQuestion(question.id, {
        expected_version: question.current_version,
        decision: 'REJECTED',
        note: detail,
        review_form: {
          checklist: SCORE_COMPONENTS.map((component) => ({
            key: component.key,
            label: component.label,
            passed: false,
            note: '',
          })),
          overall_note: detail,
          revision_issues: [],
        },
      });
      setMessage('Đã từ chối câu hỏi và lưu lý do vào lịch sử kiểm duyệt.');
      setActionDialog(null);
      await refreshSelection(question.id);
    } catch (err) {
      setDialogError(err.message || 'Từ chối câu hỏi thất bại');
    } finally {
      setBusyId('');
    }
  };

  const submitActionDialog = async () => {
    if (!actionDialog) return;
    const { type, question, targets } = actionDialog;
    if (type === 'evaluate') {
      await runEvaluation(question);
      return;
    }
    if (type === 'bulk-evaluate') {
      await runBulkEvaluation(targets);
      return;
    }
    if (type === 'approve') {
      const unchecked = SCORE_COMPONENTS.filter(
        (component) => !approvalChecklist[component.key],
      );
      if (unchecked.length > 0) {
        setDialogError('Hãy xác nhận đủ 5 tiêu chí.');
        return;
      }
      if (question.evaluation_status !== 'PASSED' && !actionReason.trim()) {
        setDialogError('Cần ghi rõ lý do khi duyệt một câu hỏi chưa đạt AI.');
        return;
      }
      await approveQuestion(question, approvalChecklist, actionReason);
      return;
    }
    if (!actionReason.trim()) {
      setDialogError(
        type === 'revision'
          ? 'Cần ghi rõ nội dung giảng viên phải chỉnh sửa.'
          : 'Cần ghi rõ lý do từ chối câu hỏi.',
      );
      return;
    }
    if (type === 'revision') {
      await requestRevision(question, actionReason);
    } else if (type === 'reject') {
      await rejectQuestion(question, actionReason);
    }
  };

  const hasCustomFilters = (
    statusFilter !== 'pending'
    || qualityFilter !== 'all'
    || sortOrder !== 'risk'
    || Boolean(searchInput)
  );
  const dialogQuestion = actionDialog?.question;
  const dialogNeedsOverride = (
    actionDialog?.type === 'approve'
    && dialogQuestion?.evaluation_status !== 'PASSED'
  );
  const dialogTitle = {
    evaluate: dialogQuestion && ['FAILED', 'ERROR', 'STALE'].includes(dialogQuestion.evaluation_status)
      ? 'Chạy lại đánh giá AI'
      : 'Chạy đánh giá AI',
    'bulk-evaluate': 'Kiểm tra AI các câu đang chờ',
    approve: 'Duyệt câu hỏi',
    revision: 'Yêu cầu chỉnh sửa',
    reject: 'Từ chối câu hỏi',
  }[actionDialog?.type] || 'Xác nhận hành động';
  const dialogConfirmLabel = {
    evaluate: 'Gửi AI đánh giá',
    'bulk-evaluate': 'Đưa vào hàng đợi',
    approve: 'Xác nhận duyệt',
    revision: 'Gửi yêu cầu chỉnh sửa',
    reject: 'Xác nhận từ chối',
  }[actionDialog?.type] || 'Xác nhận';

  return (
    <main className="admin-ai-review-page">
      <section className="ai-review-toolbar">
        <div className="ai-review-toolbar__title">
          <span>Đánh giá AI</span>
          <h1>Thẩm định câu hỏi</h1>
          <p>Xem điểm, minh chứng và xử lý cảnh báo.</p>
        </div>
        <div className="ai-review-actions">
          <button type="button" className="btn btn--outline" onClick={() => navigate('/quan-ly')}>
            Ngân hàng
          </button>
          <button type="button" className="btn btn--outline" onClick={prepareBulkEvaluation} disabled={checkingAll || loading}>
            {checkingAll ? 'Đang kiểm tra...' : 'Gửi câu chưa chấm'}
          </button>
          <button type="button" className="btn btn--primary" onClick={fetchAiQuestions} disabled={loading}>
            {loading ? 'Đang tải' : 'Làm mới'}
          </button>
        </div>
      </section>

      <section className="ai-review-summary" aria-label="Tổng quan duyệt AI">
        <button
          type="button"
          aria-pressed={statusFilter === 'pending'}
          className={statusFilter === 'pending' ? 'active' : ''}
          onClick={() => setStatusFilter('pending')}
        >
          <span>Chờ duyệt</span>
          <b>{counts.pending}</b>
        </button>
        <button
          type="button"
          aria-pressed={statusFilter === 'unscored'}
          className={statusFilter === 'unscored' ? 'active' : ''}
          onClick={() => setStatusFilter('unscored')}
        >
          <span>Chưa có điểm AI</span>
          <b>{counts.unscored}</b>
        </button>
        <button
          type="button"
          aria-pressed={statusFilter === 'processing'}
          className={statusFilter === 'processing' ? 'active' : ''}
          onClick={() => setStatusFilter('processing')}
        >
          <span>Đang chấm</span>
          <b>{counts.processing}</b>
        </button>
        <button
          type="button"
          aria-pressed={statusFilter === 'risk'}
          className={statusFilter === 'risk' ? 'active' : ''}
          onClick={() => setStatusFilter('risk')}
        >
          <span>AI cảnh báo</span>
          <b>{counts.risk}</b>
        </button>
        <button
          type="button"
          aria-pressed={statusFilter === 'completed'}
          className={statusFilter === 'completed' ? 'active' : ''}
          onClick={() => setStatusFilter('completed')}
        >
          <span>Đã xử lý</span>
          <b>{counts.completed}</b>
        </button>
      </section>

      <section className="ai-review-layout">
        <div className="ai-review-list-panel">
          <div className="ai-review-list-heading">
            <div>
              <span>Hàng thẩm định</span>
              <b>{loading ? 'Đang tải...' : `${filtered.length} câu hỏi`}</b>
            </div>
          </div>
          <div className="ai-review-filters">
            <label className="ai-review-filter ai-review-filter--search">
              <span>Tìm câu hỏi</span>
              <div>
                <input
                  value={searchInput}
                  onChange={(event) => setSearchInput(event.target.value)}
                  placeholder="Mã hoặc nội dung câu hỏi"
                />
                {searchInput && (
                  <button type="button" aria-label="Xóa tìm kiếm" onClick={() => setSearchInput('')}>
                    ×
                  </button>
                )}
              </div>
            </label>
            <label className="ai-review-filter">
              <span>Mức chất lượng</span>
              <select value={qualityFilter} onChange={(event) => setQualityFilter(event.target.value)}>
                <option value="all">Mọi mức</option>
                <option value="UNSCORED">Chưa có điểm</option>
                <option value="RED">Rủi ro cao</option>
                <option value="YELLOW">Cần xem lại</option>
                <option value="GREEN">Đạt tốt</option>
              </select>
            </label>
            <label className="ai-review-filter">
              <span>Sắp xếp</span>
              <select value={sortOrder} onChange={(event) => setSortOrder(event.target.value)}>
                <option value="risk">Ưu tiên rủi ro</option>
                <option value="score_asc">Điểm thấp trước</option>
                <option value="score_desc">Điểm cao trước</option>
                <option value="newest">Mới cập nhật</option>
              </select>
            </label>
            <button
              type="button"
              className="ai-review-filter-reset"
              onClick={applyDefaultFilters}
              disabled={!hasCustomFilters}
            >
              Đặt lại
            </button>
          </div>

          {error && <p className="ai-review-error">{error}</p>}
          {message && <p className="ai-review-message" role="status">{message}</p>}

          {loading ? (
            <p className="ai-review-empty">Đang tải danh sách duyệt AI...</p>
          ) : filtered.length === 0 ? (
            <div className="ai-review-empty ai-review-empty--action">
              <b>Không có câu hỏi phù hợp</b>
              <span>Thử bỏ bớt điều kiện lọc hoặc chuyển sang nhóm trạng thái khác.</span>
              {hasCustomFilters && <button type="button" onClick={applyDefaultFilters}>Đặt lại bộ lọc</button>}
            </div>
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
                    <span>{questionTypeLabel(question.question_type)} · Bản {question.current_version}</span>
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
            <div className="ai-review-detail-empty">
              <span>AI</span>
              <h2>Chọn câu hỏi</h2>
              <p>Điểm và minh chứng sẽ hiện ở đây.</p>
            </div>
          ) : (
            <>
              <div className="ai-review-detail-head">
                <div>
                  <span>{selected.question_code}</span>
                  <h2>{questionTypeLabel(selected.question_type)}</h2>
                </div>
                <button type="button" className="btn btn--outline" onClick={() => navigate(`/quan-ly?questionId=${selected.id}`)}>
                  Mở trong ngân hàng
                </button>
              </div>

              <div className="ai-review-question">
                <p>{selected.content}</p>
                {selected.explanation && <small>{selected.explanation}</small>}
              </div>

              <div className="ai-review-detail-actions">
                <button
                  type="button"
                  disabled={busyId === selected.id || !canQueueEvaluation(selected)}
                  onClick={() => openActionDialog('evaluate', selected)}
                >
                  {['FAILED', 'ERROR', 'STALE'].includes(selected.evaluation_status)
                    ? 'Gửi AI chấm lại'
                    : 'Gửi AI đánh giá'}
                </button>
                <button
                  type="button"
                  className="primary"
                  disabled={busyId === selected.id || isEvaluationBusy(selected) || selected.review_status !== 'PENDING'}
                  onClick={() => openActionDialog('approve', selected)}
                >
                  Duyệt
                </button>
                <button
                  type="button"
                  disabled={busyId === selected.id || selected.review_status !== 'PENDING'}
                  onClick={() => openActionDialog('revision', selected)}
                >
                  Cần sửa
                </button>
                <button
                  type="button"
                  className="danger"
                  disabled={busyId === selected.id || selected.review_status !== 'PENDING'}
                  onClick={() => openActionDialog('reject', selected)}
                >
                  Từ chối
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
                      <span>Chế độ</span>
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

      {actionDialog && (
        <div className="ai-admin-dialog-backdrop">
          <form
            className="ai-admin-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="ai-admin-dialog-title"
            onSubmit={(event) => {
              event.preventDefault();
              submitActionDialog();
            }}
          >
            <header className="ai-admin-dialog__head">
              <div>
                <span>
                  {dialogQuestion?.question_code
                    || `${actionDialog.targets?.length || 0} câu hỏi`}
                </span>
                <h2 id="ai-admin-dialog-title">{dialogTitle}</h2>
              </div>
              <button type="button" aria-label="Đóng hộp thoại" onClick={closeActionDialog}>
                Đóng
              </button>
            </header>

            <div className="ai-admin-dialog__body">
              {dialogQuestion && (
                <div className="ai-admin-dialog__question">
                  <b>{dialogQuestion.content}</b>
                  <span>
                    {evaluationStatusLabel(dialogQuestion.evaluation_status)}
                    {' · '}
                    {questionSummary(dialogQuestion)}
                  </span>
                </div>
              )}

              {['evaluate', 'bulk-evaluate'].includes(actionDialog.type) && (
                <>
                  <div className="ai-admin-model-card">
                    <span>Mô hình</span>
                    <b>
                      {modelRuntimeLabel(
                        dialogQuestion?.quality_summary?.evaluator_model_code || 'deepseek-r1',
                      )}
                    </b>
                    <small>Không chấm dự phòng khi mô hình lỗi.</small>
                  </div>
                  <p className="ai-admin-dialog__hint">
                    {actionDialog.type === 'bulk-evaluate'
                      ? `${actionDialog.targets.length} câu hỏi sẽ được đưa vào hàng đợi.`
                      : 'AI chấm 5 tiêu chí. Bạn quyết định.'}
                  </p>
                </>
              )}

              {actionDialog.type === 'approve' && (
                <>
                  {dialogNeedsOverride && (
                    <div className="ai-admin-dialog__warning">
                      AI chưa đánh dấu đạt. Hệ thống sẽ lưu lý do duyệt.
                    </div>
                  )}
                  <section className="ai-admin-checklist" aria-labelledby="ai-admin-checklist-title">
                    <div>
                      <h3 id="ai-admin-checklist-title">Tiêu chí xác nhận</h3>
                      <span>
                        {Object.values(approvalChecklist).filter(Boolean).length}/{SCORE_COMPONENTS.length}
                      </span>
                    </div>
                    <p>Tự xác nhận từng mục.</p>
                    {SCORE_COMPONENTS.map((component) => (
                      <label key={component.key}>
                        <input
                          type="checkbox"
                          checked={Boolean(approvalChecklist[component.key])}
                          onChange={(event) => setApprovalChecklist((current) => ({
                            ...current,
                            [component.key]: event.target.checked,
                          }))}
                        />
                        {component.label}
                      </label>
                    ))}
                  </section>
                  {dialogNeedsOverride && (
                    <label className="ai-admin-dialog__field">
                      <span>Lý do duyệt khác đề xuất AI</span>
                      <textarea
                        value={actionReason}
                        onChange={(event) => setActionReason(event.target.value)}
                        rows={4}
                        placeholder="Nêu căn cứ chuyên môn..."
                      />
                    </label>
                  )}
                </>
              )}

              {['revision', 'reject'].includes(actionDialog.type) && (
                <label className="ai-admin-dialog__field">
                  <span>
                    {actionDialog.type === 'revision'
                      ? 'Nội dung giảng viên cần sửa'
                      : 'Lý do từ chối'}
                  </span>
                  <textarea
                    value={actionReason}
                    onChange={(event) => setActionReason(event.target.value)}
                    rows={5}
                    placeholder={actionDialog.type === 'revision'
                      ? 'Nêu lỗi và cách chỉnh...'
                      : 'Nêu lý do từ chối...'}
                    autoFocus
                  />
                </label>
              )}

              {dialogError && <p className="ai-admin-dialog__error" role="alert">{dialogError}</p>}
            </div>

            <footer className="ai-admin-dialog__foot">
              <button type="button" onClick={closeActionDialog}>Hủy</button>
              <button
                type="submit"
                className={actionDialog.type === 'reject' ? 'danger' : 'primary'}
                disabled={Boolean(busyId) || checkingAll}
              >
                {busyId || checkingAll ? 'Đang xử lý...' : dialogConfirmLabel}
              </button>
            </footer>
          </form>
        </div>
      )}
    </main>
  );
}

export default AdminAiReviewPage;
