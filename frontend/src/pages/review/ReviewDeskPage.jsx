import { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faArrowLeft,
  faChevronLeft,
  faChevronRight,
  faClock,
  faLock,
  faRotateLeft,
  faUserCheck,
} from '@fortawesome/free-solid-svg-icons';
import {
  assignQuestionReview,
  autoEvaluateQuestion,
  claimQuestionReview,
  deleteQuestionReviewDraft,
  getQuestion,
  getQuestionReviewDraft,
  getQuestionSources,
  listQuestionEvaluations,
  listQuestionMoodlePublications,
  listQuestionReviews,
  releaseQuestionReview,
  reviewQuestion,
  saveQuestionReviewDraft,
} from '../../api/questions';
import { AuthContext } from '../../context/AuthContext';
import { mergeAiSuggestionsIntoDraft } from '../../utils/reviewAiSuggestions';
import Drawer from '../../components/workspace/Drawer';
import { EmptyState, Notice, SkeletonRows } from '../../components/workspace/Feedback';
import { useConfirm, useFlash } from '../../components/workspace/Dialog';
import { Tabs } from '../../components/workspace/Navigation';
import QuestionPane from '../../features/review/QuestionPane';
import SourcePanel from '../../features/review/SourcePanel';
import { AiSuggestion, summarizeEvaluation } from '../../features/review/AiPanel';
import DiscussionPanel from '../../features/review/DiscussionPanel';
import HistoryPanel from '../../features/review/HistoryPanel';
import DecisionPanel from '../../features/review/DecisionPanel';
import MoodlePublishPanel from '../../features/review/MoodlePublishPanel';
import { claimNextQuestion, useReviewLookups, userName } from '../../features/review/reviewData';
import {
  DECISION_DONE_TEXT,
  EVALUATION_STATUS_LABEL,
  QUALITY_TONE,
  REVIEW_STATUS_LABEL,
  REVIEW_STATUS_TONE,
  SECONDARY_STATUS_LABEL,
  assignmentLabel,
  assignmentOf,
  buildReviewPayload,
  canClaim,
  canDecide,
  canRelease,
  childId,
  defaultDraft,
  formatDateTime,
  formatRemaining,
  isAssignedToUser,
  isEvaluationBusy,
  isLockExpired,
  isObjectId,
  isPending,
  refId,
  restoreDraft,
  reviewIssuesOf,
  validateDraft,
} from '../../features/review/reviewModel';
import '../../css/workspace.css';
import '../../css/ReviewPage.css';
import '../../css/ReviewDesk.css';
import '../../css/AdminPages.css';

const CONTINUE_KEY = 'qbankctu:review-continue-next';

function readContinuePreference() {
  try {
    return localStorage.getItem(CONTINUE_KEY) !== 'false';
  } catch {
    return true;
  }
}

function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => (typeof window !== 'undefined' ? window.matchMedia(query).matches : true));
  useEffect(() => {
    const media = window.matchMedia(query);
    const handleChange = () => setMatches(media.matches);
    handleChange();
    media.addEventListener('change', handleChange);
    return () => media.removeEventListener('change', handleChange);
  }, [query]);
  return matches;
}

function isTypingTarget(target) {
  return target instanceof HTMLElement
    && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName));
}

function ReviewDeskPage() {
  const { questionId } = useParams();
  const validId = isObjectId(questionId);
  const { user } = useContext(AuthContext);
  const navigate = useNavigate();
  const location = useLocation();
  const lookups = useReviewLookups();
  const { flash, show: showFlash, clear: clearFlash } = useFlash();
  const [confirm, confirmDialog] = useConfirm();
  const wide = useMediaQuery('(min-width: 1280px)');
  const returnTo = location.state?.returnTo || '/kiem-duyet';
  const queue = useMemo(() => (Array.isArray(location.state?.queue) ? location.state.queue : []), [location.state]);
  const queueIndex = queue.indexOf(questionId);
  const prevId = queueIndex > 0 ? queue[queueIndex - 1] : '';
  const nextId = queueIndex >= 0 && queueIndex < queue.length - 1 ? queue[queueIndex + 1] : '';

  const [question, setQuestion] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [evaluations, setEvaluations] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [publications, setPublications] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [sourceState, setSourceState] = useState({ loading: true, error: '', viewer: null });
  const [serverDraft, setServerDraft] = useState(undefined);
  const [draft, setDraft] = useState(null);
  const [saveState, setSaveState] = useState('');
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState('');
  const [paneTab, setPaneTab] = useState('question');
  const [commentCount, setCommentCount] = useState(null);
  const [now, setNow] = useState(() => Date.now());
  const [continueNext, setContinueNext] = useState(readContinuePreference);
  const [assignDrawer, setAssignDrawer] = useState(null);
  const draftDirtyRef = useRef(false);
  const lastSavedRef = useRef('');
  const autoClaimRef = useRef('');

  useEffect(() => {
    if (location.state?.flash) showFlash(location.state.flash.tone, location.state.flash.message);
    // Chỉ đọc thông báo chuyển tiếp một lần cho mỗi lần điều hướng.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(timer);
  }, []);

  const refreshQuestion = useCallback(async () => {
    const fresh = await getQuestion(questionId);
    setQuestion(fresh);
    return fresh;
  }, [questionId]);

  const refreshHistory = useCallback(async () => {
    const [evaluationResult, reviewResult, publicationResult] = await Promise.allSettled([
      listQuestionEvaluations(questionId),
      listQuestionReviews(questionId),
      listQuestionMoodlePublications(questionId),
    ]);
    setEvaluations(evaluationResult.status === 'fulfilled' ? (evaluationResult.value.items || []) : []);
    setReviews(reviewResult.status === 'fulfilled' ? (reviewResult.value.items || []) : []);
    setPublications(publicationResult.status === 'fulfilled' ? (publicationResult.value.items || []) : []);
    setHistoryLoading(false);
  }, [questionId]);

  useEffect(() => {
    if (!validId) return undefined;
    let active = true;
    setLoading(true);
    setLoadError('');
    setQuestion(null);
    setDraft(null);
    setServerDraft(undefined);
    setFormError('');
    setSaveState('');
    setHistoryLoading(true);
    setCommentCount(null);
    setPaneTab('question');
    setSourceState({ loading: true, error: '', viewer: null });
    draftDirtyRef.current = false;
    lastSavedRef.current = '';

    getQuestion(questionId)
      .then((fresh) => active && setQuestion(fresh))
      .catch((error) => active && setLoadError(error.status === 404 ? 'Câu hỏi không tồn tại hoặc đã bị xoá.' : (error.message || 'Không tải được câu hỏi.')))
      .finally(() => active && setLoading(false));
    refreshHistory();
    getQuestionSources(questionId)
      .then((viewer) => active && setSourceState({ loading: false, error: '', viewer }))
      .catch((error) => active && setSourceState({ loading: false, error: error.message || 'Không tải được nguồn tham chiếu.', viewer: null }));
    getQuestionReviewDraft(questionId)
      .then((result) => active && setServerDraft(result?.item && !result.item.is_stale ? result.item : null))
      .catch(() => active && setServerDraft(null));
    return () => {
      active = false;
    };
  }, [questionId, validId, refreshHistory]);

  // Vào từ "tự chuyển câu tiếp theo": nhận luôn câu nếu còn trống.
  useEffect(() => {
    if (!question || !location.state?.autoClaim || autoClaimRef.current === question.id) return;
    autoClaimRef.current = question.id;
    const holds = isAssignedToUser(question, user) && assignmentOf(question).status === 'IN_REVIEW' && !isLockExpired(question);
    if (holds || !canClaim(question, user) || user?.role === 'Admin') return;
    claimQuestionReview(question.id).then(setQuestion).catch(() => null);
  }, [question, location.state, user]);

  // Khởi tạo phiếu khi có quyền chấm (khôi phục nháp nếu còn khớp phiên bản).
  useEffect(() => {
    if (!question || draft || serverDraft === undefined || !canDecide(question, user, Date.now())) return;
    if (serverDraft?.draft) {
      setDraft(restoreDraft(question, serverDraft.decision || 'APPROVED', serverDraft.draft));
      setSaveState('Đã khôi phục phiếu nháp');
    } else {
      setDraft(defaultDraft(question, 'APPROVED'));
    }
  }, [question, serverDraft, draft, user]);

  // AI đang chấm: hỏi lại mỗi 5 giây tới khi có kết quả.
  useEffect(() => {
    if (!question || !isEvaluationBusy(question)) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const fresh = await refreshQuestion();
        if (!isEvaluationBusy(fresh)) {
          await refreshHistory();
          showFlash('info', `AI đã đánh giá xong: ${EVALUATION_STATUS_LABEL[fresh.evaluation_status] || fresh.evaluation_status}.`);
        }
      } catch {
        // Lỗi mạng tạm thời: lần sau thử lại.
      }
    }, 5000);
    return () => window.clearInterval(timer);
  }, [question, refreshQuestion, refreshHistory, showFlash]);

  // Tự lưu phiếu nháp sau khi ngừng gõ.
  useEffect(() => {
    if (!draft || !question || !draftDirtyRef.current) return undefined;
    const serialized = JSON.stringify(draft);
    if (serialized === lastSavedRef.current) return undefined;
    setSaveState('Đang lưu nháp...');
    const timer = window.setTimeout(async () => {
      try {
        await saveQuestionReviewDraft(question.id, { expected_version: question.current_version, decision: draft.decision, draft });
        lastSavedRef.current = serialized;
        setSaveState('Đã lưu nháp');
      } catch (error) {
        setSaveState(error.status === 409 ? 'Câu hỏi vừa được cập nhật, tải lại trang' : 'Chưa lưu được nháp');
      }
    }, 900);
    return () => window.clearTimeout(timer);
  }, [draft, question]);

  const ai = useMemo(() => summarizeEvaluation(question, evaluations), [question, evaluations]);
  const people = useMemo(() => {
    const map = new Map();
    const submitterId = refId(question?.submitted_by_user_id || question?.review_submission?.submitted_by_user_id);
    const submitter = lookups.teachersById.get(submitterId);
    if (submitter) map.set(submitterId, submitter);
    [...lookups.teachers, ...lookups.reviewers].forEach((person) => {
      const id = refId(person);
      if (id && !map.has(id)) map.set(id, person);
    });
    return Array.from(map.values());
  }, [lookups, question]);
  const peopleById = useMemo(() => new Map(people.map((person) => [refId(person), person])), [people]);

  const goTo = useCallback((id, extra = {}) => {
    navigate(`/kiem-duyet/${id}`, { state: { returnTo, queue, ...extra } });
  }, [navigate, returnTo, queue]);

  const changeDraft = (next) => {
    draftDirtyRef.current = true;
    setFormError('');
    setDraft(next);
  };

  const applyAiSuggestions = () => {
    if (!draft || !ai.latest) return;
    const merged = mergeAiSuggestionsIntoDraft(draft, { ...ai.latest, evidence: ai.evidence, feedback: ai.feedback, scores: ai.scores });
    changeDraft({
      ...merged,
      criteria: merged.criteria.map((item) => (typeof ai.scores[item.key] === 'number' ? { ...item, touched: true } : item)),
    });
  };

  const discardDraft = async () => {
    const accepted = await confirm({
      title: 'Xoá phiếu nháp',
      description: 'Mục kiểm tra, nhận xét và danh sách lỗi đang ghi sẽ bị xoá.',
      confirmLabel: 'Xoá phiếu',
      tone: 'danger',
    });
    if (!accepted) return;
    await deleteQuestionReviewDraft(questionId).catch(() => null);
    draftDirtyRef.current = false;
    lastSavedRef.current = '';
    setServerDraft(null);
    setDraft(defaultDraft(question, 'APPROVED'));
    setSaveState('');
    setFormError('');
  };

  const runAction = async (key, action, successMessage) => {
    setBusy(key);
    clearFlash();
    try {
      await action();
      if (successMessage) showFlash('success', successMessage);
      return true;
    } catch (error) {
      showFlash('error', error.message || 'Thao tác không thành công.');
      return false;
    } finally {
      setBusy('');
    }
  };

  const holding = question && isPending(question) && isAssignedToUser(question, user)
    && assignmentOf(question).status === 'IN_REVIEW' && !isLockExpired(question, now);

  const handleClaim = () => runAction('claim', async () => {
    setQuestion(await claimQuestionReview(questionId));
  }, holding ? 'Đã gia hạn khoá thêm 30 phút.' : 'Bạn đã nhận câu hỏi này.');

  const handleRelease = async () => {
    const accepted = await confirm({
      title: 'Trả câu về hàng chờ',
      description: 'Người khác có thể nhận câu này. Phiếu nháp của bạn vẫn được giữ.',
      confirmLabel: 'Trả câu',
    });
    if (!accepted) return;
    const ok = await runAction('release', async () => setQuestion(await releaseQuestionReview(questionId)));
    if (ok) navigate(returnTo);
  };

  const handleEvaluate = () => runAction('evaluate', async () => {
    await autoEvaluateQuestion(questionId, { expected_version: question.current_version, fallback_to_heuristic: false });
    await refreshQuestion();
  }, 'Đã gửi AI đánh giá lại. Kết quả sẽ tự cập nhật.');

  const submitAssign = async () => {
    const { reviewerId, note } = assignDrawer;
    setBusy('assign');
    try {
      setQuestion(await assignQuestionReview(questionId, { reviewer_user_id: reviewerId || null, note: note.trim() }));
      setAssignDrawer(null);
      showFlash('success', reviewerId ? 'Đã giao câu cho người duyệt.' : 'Đã bỏ giao, câu quay lại hàng chờ chung.');
    } catch (error) {
      setAssignDrawer((current) => ({ ...current, error: error.message || 'Không phân công được.' }));
    } finally {
      setBusy('');
    }
  };

  const moveOn = async (doneMessage) => {
    const state = { tone: 'success', message: doneMessage };
    if (nextId) {
      goTo(nextId, { autoClaim: true, flash: state });
      return;
    }
    const next = await claimNextQuestion(user, { excludeId: questionId }).catch(() => null);
    if (next) {
      navigate(`/kiem-duyet/${next.id}`, { state: { returnTo, queue: [], flash: { ...state, message: `${doneMessage} Đã nhận câu tiếp theo.` } } });
      return;
    }
    navigate(returnTo, { state: null });
  };

  const decide = async (decision) => {
    if (!draft) return;
    const candidate = { ...draft, decision };
    if (decision === 'NEEDS_REVISION' && candidate.issues.length === 0) {
      changeDraft({ ...candidate, issues: [{ id: `issue-${Date.now()}`, title: '', severity: 'MEDIUM', detail: '', source_chunk_id: '', page_number: '' }] });
      setFormError('Ghi ít nhất một lỗi cụ thể để giảng viên biết cần sửa gì, rồi bấm "Gửi yêu cầu sửa".');
      return;
    }
    const message = validateDraft(question, candidate, user, Date.now());
    if (message) {
      changeDraft(candidate);
      setFormError(message);
      return;
    }
    if (decision === 'REJECTED') {
      const accepted = await confirm({
        title: 'Từ chối câu hỏi',
        description: 'Câu hỏi sẽ không được đưa vào ngân hàng. Giảng viên nhận được lý do bạn ghi.',
        confirmLabel: 'Từ chối',
        tone: 'danger',
      });
      if (!accepted) return;
    }
    setDraft(candidate);
    setBusy('submit');
    setFormError('');
    clearFlash();
    try {
      await reviewQuestion(questionId, buildReviewPayload(question, candidate));
      draftDirtyRef.current = false;
      await deleteQuestionReviewDraft(questionId).catch(() => null);
      const doneMessage = `${DECISION_DONE_TEXT[decision]} ${question.question_code}.`;
      if (continueNext) {
        await moveOn(doneMessage);
        return;
      }
      setDraft(null);
      setServerDraft(null);
      await Promise.all([refreshQuestion(), refreshHistory()]);
      showFlash('success', doneMessage);
    } catch (error) {
      setFormError(error.status === 409
        ? 'Câu hỏi vừa được giảng viên cập nhật. Tải lại trang để chấm phiên bản mới.'
        : (error.message || 'Không chốt được kết quả.'));
      refreshQuestion().catch(() => null);
    } finally {
      setBusy('');
    }
  };

  // Phím tắt: A duyệt, R yêu cầu sửa, J/K câu sau/trước, Esc về Hộp việc.
  const decideRef = useRef(decide);
  decideRef.current = decide;
  useEffect(() => {
    const handleKey = (event) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || isTypingTarget(event.target)) return;
      if (document.querySelector('.ws-dialog-backdrop, .ws-drawer-backdrop, .ws-more__menu')) return;
      const key = event.key.toLowerCase();
      if (key === 'j' && nextId) goTo(nextId);
      else if (key === 'k' && prevId) goTo(prevId);
      else if (key === 'escape') navigate(returnTo);
      else if (key === 'a' && draft) decideRef.current('APPROVED');
      else if (key === 'r' && draft) decideRef.current('NEEDS_REVISION');
      else return;
      event.preventDefault();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [nextId, prevId, goTo, navigate, returnTo, draft]);

  const toggleContinue = (value) => {
    setContinueNext(value);
    try {
      localStorage.setItem(CONTINUE_KEY, String(value));
    } catch {
      // Không lưu được lựa chọn thì chỉ áp dụng cho phiên này.
    }
  };

  if (!validId) return <Navigate to="/kiem-duyet" replace />;

  const backLink = (
    <Link to={returnTo} className="rv-back">
      <FontAwesomeIcon icon={faArrowLeft} />
      Hộp việc
    </Link>
  );

  if (loading) {
    return (
      <main className="ws-page rv-desk-page">
        <header className="rv-deskbar"><div className="container">{backLink}<SkeletonRows rows={1} lines={2} /></div></header>
        <section className="ws-body"><div className="container"><div className="ws-card"><SkeletonRows rows={4} lines={3} /></div></div></section>
      </main>
    );
  }

  if (loadError || !question) {
    return (
      <main className="ws-page rv-desk-page">
        <section className="ws-body">
          <div className="container">
            {backLink}
            <div className="ws-card">
              <EmptyState
                title="Không mở được câu hỏi"
                description={loadError || 'Câu hỏi có thể đã bị xoá hoặc bạn không có quyền xem.'}
                action={<Link to="/kiem-duyet" className="btn btn--primary">Về Hộp việc</Link>}
              />
            </div>
          </div>
        </section>
      </main>
    );
  }

  const assignment = assignmentOf(question);
  const pending = isPending(question);
  const decideAllowed = canDecide(question, user, now);
  const lockMinutes = assignment.lockExpiresAt ? (new Date(assignment.lockExpiresAt).getTime() - now) / 60000 : null;
  const submitter = question.review_submission?.submitted_by
    || lookups.teachersById.get(refId(question.submitted_by_user_id));
  const reviewer = lookups.reviewersById.get(assignment.reviewerUserId);
  const subject = lookups.subjectsById.get(refId(question.subject_id || question.classification?.subject));
  const chapter = (subject?.chapters || []).find((item) => childId(item) === refId(question.classification?.chapter));
  const subjectLabel = question.subject?.code || subject?.subject_code || question.subject?.name || 'Chưa gắn học phần';
  const latestReview = reviews[0];
  const sources = sourceState.viewer?.items || [];
  const isAdminUser = user?.role === 'Admin';

  const sourceCard = (
    <section className="ws-card rv-pane">
      <div className="ws-card-title" style={{ marginBottom: 12 }}>
        <h3>Nguồn tham chiếu</h3>
        <span>{sourceState.loading ? 'Đang tải...' : `${sources.length} đoạn trích`}</span>
      </div>
      <SourcePanel
        questionId={questionId}
        viewer={sourceState.viewer}
        loading={sourceState.loading}
        error={sourceState.error}
        active={wide || paneTab === 'source'}
      />
    </section>
  );

  return (
    <main className="ws-page rv-desk-page">
      <header className="rv-deskbar">
        <div className="container">
          <div className="rv-deskbar__top">
            {backLink}
            <div className="rv-deskbar__nav">
              <button type="button" className="ws-icon-btn" disabled={!prevId} onClick={() => goTo(prevId)} aria-label="Câu trước" title={prevId ? 'Câu trước (K)' : 'Không có câu trước trong danh sách'}>
                <FontAwesomeIcon icon={faChevronLeft} />
              </button>
              <span className="ws-hint tabular">{queueIndex >= 0 ? `${queueIndex + 1}/${queue.length}` : ''}</span>
              <button type="button" className="ws-icon-btn" disabled={!nextId} onClick={() => goTo(nextId)} aria-label="Câu sau" title={nextId ? 'Câu sau (J)' : 'Không có câu sau trong danh sách'}>
                <FontAwesomeIcon icon={faChevronRight} />
              </button>
            </div>
          </div>
          <div className="rv-deskbar__main">
            <div style={{ minWidth: 0 }}>
              <h1 className="rv-deskbar__title">
                Bàn duyệt <span className="ws-code">{question.question_code}</span>
              </h1>
              <div className="ws-meta">
                <span><b>{subjectLabel}</b>{chapter ? `, ${chapter.chapter_code || chapter.chapter_name}` : ''}</span>
                {(question.clos || []).length > 0 && <span>{question.clos.map((clo) => clo.code || clo.clo_code).filter(Boolean).join(', ')}</span>}
                <span>Giảng viên: <b>{userName(submitter, 'chưa ghi nhận')}</b></span>
                {(question.review_submission?.submitted_at || question.submitted_at) && (
                  <span>Gửi lúc {formatDateTime(question.review_submission?.submitted_at || question.submitted_at)}</span>
                )}
              </div>
              <div className="rv-hero-pills">
                <span className={`ws-pill ws-pill--${REVIEW_STATUS_TONE[question.review_status] || 'outline'}`}>
                  {REVIEW_STATUS_LABEL[question.review_status] || question.review_status}
                </span>
                <span className={`ws-pill ${QUALITY_TONE[ai.color] ? `ws-pill--${QUALITY_TONE[ai.color]}` : ''}`}>
                  {EVALUATION_STATUS_LABEL[question.evaluation_status] || 'Chưa đánh giá'}
                </span>
                {question.secondary_review?.status && !['NOT_REQUIRED', 'CANCELLED'].includes(question.secondary_review.status) && (
                  <span className="ws-pill ws-pill--info">{SECONDARY_STATUS_LABEL[question.secondary_review.status]}</span>
                )}
              </div>
            </div>
            {pending && (
              <div className="rv-deskbar__lock">
                {holding ? (
                  <span className={`rv-lock ${lockMinutes !== null && lockMinutes < 5 ? 'rv-lock--warn' : ''}`}>
                    <FontAwesomeIcon icon={faClock} />
                    Bạn đang giữ, {formatRemaining(assignment.lockExpiresAt, now)}
                    <button type="button" className="ws-link-btn" onClick={handleClaim} disabled={Boolean(busy)}>Gia hạn</button>
                  </span>
                ) : (
                  <span className="rv-lock">
                    <FontAwesomeIcon icon={faLock} />
                    {assignmentLabel(question, user, now)}
                    {assignment.reviewerUserId && !isAssignedToUser(question, user) ? `: ${userName(reviewer, 'người khác')}` : ''}
                  </span>
                )}
                <div className="rv-action-row">
                  {!holding && canClaim(question, user, now) && (
                    <button type="button" className="btn btn--primary" onClick={handleClaim} disabled={Boolean(busy)}>
                      {busy === 'claim' ? 'Đang nhận...' : 'Nhận câu'}
                    </button>
                  )}
                  {canRelease(question, user) && (
                    <button type="button" className="btn btn--outline" onClick={handleRelease} disabled={Boolean(busy)}>
                      <FontAwesomeIcon icon={faRotateLeft} />
                      Trả câu
                    </button>
                  )}
                  {isAdminUser && (
                    <button
                      type="button"
                      className="btn btn--outline"
                      disabled={Boolean(busy)}
                      onClick={() => setAssignDrawer({ reviewerId: assignment.reviewerUserId || '', note: '', error: '' })}
                    >
                      <FontAwesomeIcon icon={faUserCheck} />
                      Giao cho...
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      <section className="ws-body rv-desk-body">
        <div className="container">
          {flash && <div style={{ marginBottom: 16 }}><Notice tone={flash.tone} onDismiss={clearFlash}>{flash.message}</Notice></div>}
          <div className={`rv-desk ${wide ? 'rv-desk--3' : 'rv-desk--2'}`}>
            {wide && <div className="rv-desk__source">{sourceCard}</div>}

            <div className="rv-desk__main">
              {!wide && (
                <Tabs
                  label="Nội dung"
                  value={paneTab}
                  onChange={setPaneTab}
                  items={[
                    { value: 'question', label: 'Câu hỏi' },
                    { value: 'source', label: 'Nguồn', count: sourceState.loading ? undefined : sources.length },
                  ]}
                />
              )}
              <div hidden={!wide && paneTab !== 'question'}>
                <QuestionPane question={question} reviews={reviews} />
              </div>
              {!wide && <div hidden={paneTab !== 'source'}>{sourceCard}</div>}

              <details className="rv-fold" open={!pending || undefined}>
                <summary>Trao đổi{commentCount ? <span className="ws-tab-count">{commentCount}</span> : null}</summary>
                <div className="rv-fold__body">
                  <DiscussionPanel questionId={questionId} user={user} people={people} confirm={confirm} onCountChange={setCommentCount} />
                </div>
              </details>
              <details className="rv-fold">
                <summary>Lịch sử{reviews.length ? <span className="ws-tab-count">{reviews.length}</span> : null}</summary>
                <div className="rv-fold__body">
                  <HistoryPanel reviews={reviews} publications={publications} loading={historyLoading} peopleById={peopleById} />
                </div>
              </details>
            </div>

            <aside className="rv-desk__decision ws-side--sticky" aria-label="Quyết định">
              <section className="ws-card">
                <AiSuggestion question={question} ai={ai} loading={historyLoading} onRetry={pending ? handleEvaluate : undefined} retrying={busy === 'evaluate'} />
                <hr className="ws-divider" />
                {pending ? (
                  decideAllowed && draft ? (
                    <DecisionPanel
                      question={question}
                      user={user}
                      draft={draft}
                      onDraftChange={changeDraft}
                      onDecide={decide}
                      submitting={busy === 'submit'}
                      error={formError}
                      saveState={saveState}
                      aiScores={ai.scores}
                      sources={sources}
                      continueNext={continueNext}
                      onContinueNextChange={toggleContinue}
                      onApplyAi={applyAiSuggestions}
                      canApplyAi={Boolean(ai.latest) && !ai.hasError}
                      onDiscard={discardDraft}
                    />
                  ) : (
                    <div className="rv-locked">
                      <p>
                        {canClaim(question, user, now)
                          ? 'Bấm "Nhận câu" ở thanh trên để giữ quyền chấm trong 30 phút, tránh trùng việc với người duyệt khác.'
                          : `${userName(reviewer, 'Người duyệt khác')} đang xử lý câu này. Bạn vẫn đọc được nội dung và trao đổi.`}
                      </p>
                    </div>
                  )
                ) : (
                  <div className="rv-decision">
                    <div className="rv-section-head">
                      <span className="ws-label">Kết luận</span>
                      <span className={`ws-pill ws-pill--${REVIEW_STATUS_TONE[question.review_status] || 'outline'}`}>
                        {REVIEW_STATUS_LABEL[question.review_status] || question.review_status}
                      </span>
                    </div>
                    {latestReview ? (
                      <>
                        <p className="ws-hint" style={{ margin: 0 }}>
                          {userName(peopleById.get(refId(latestReview.reviewer_user_id)), 'Người duyệt')}, {formatDateTime(latestReview.reviewed_at)}
                        </p>
                        {latestReview.note && <p style={{ margin: 0, fontSize: '0.9rem', lineHeight: 1.6 }}>{latestReview.note}</p>}
                        {reviewIssuesOf(latestReview).length > 0 && (
                          <p className="ws-hint" style={{ margin: 0 }}>{reviewIssuesOf(latestReview).length} lỗi đã gửi giảng viên.</p>
                        )}
                      </>
                    ) : (
                      <p className="ws-hint" style={{ margin: 0 }}>Chưa có phiếu kiểm duyệt.</p>
                    )}
                    {question.review_status === 'APPROVED' && (
                      <>
                        <hr className="ws-divider" />
                        <MoodlePublishPanel
                          question={question}
                          user={user}
                          publications={publications}
                          onPublished={() => Promise.all([refreshQuestion(), refreshHistory()])}
                        />
                      </>
                    )}
                    {nextId && (
                      <button type="button" className="btn btn--outline" onClick={() => goTo(nextId)}>Câu tiếp theo</button>
                    )}
                  </div>
                )}
              </section>
            </aside>
          </div>
        </div>
      </section>

      <Drawer
        open={Boolean(assignDrawer)}
        title="Giao cho người duyệt"
        subtitle={question.question_code}
        onClose={() => setAssignDrawer(null)}
        busy={busy === 'assign'}
        as="form"
        onSubmit={submitAssign}
        footer={(
          <>
            <button type="button" className="btn btn--outline" onClick={() => setAssignDrawer(null)} disabled={busy === 'assign'}>Huỷ</button>
            <button type="submit" className="btn btn--primary" disabled={busy === 'assign'}>{busy === 'assign' ? 'Đang lưu...' : 'Lưu phân công'}</button>
          </>
        )}
      >
        {assignDrawer && (
          <>
            <label className="ws-field">
              <span>Người duyệt</span>
              <select className="ws-select" value={assignDrawer.reviewerId} onChange={(event) => setAssignDrawer({ ...assignDrawer, reviewerId: event.target.value })}>
                <option value="">Bỏ giao, trả về hàng chờ chung</option>
                {lookups.reviewers.map((option) => <option key={refId(option)} value={refId(option)}>{userName(option)}</option>)}
                {assignDrawer.reviewerId && !lookups.reviewersById.has(assignDrawer.reviewerId) && (
                  <option value={assignDrawer.reviewerId}>Người duyệt hiện tại (không còn hoạt động)</option>
                )}
              </select>
              <small>Người được giao nhận thông báo và giữ câu trong 30 phút.</small>
            </label>
            <label className="ws-field">
              <span>Ghi chú</span>
              <textarea className="ws-textarea" maxLength={500} value={assignDrawer.note} onChange={(event) => setAssignDrawer({ ...assignDrawer, note: event.target.value })} />
            </label>
            {assignDrawer.error && <Notice tone="error">{assignDrawer.error}</Notice>}
          </>
        )}
      </Drawer>
      {confirmDialog}
    </main>
  );
}

export default ReviewDeskPage;
