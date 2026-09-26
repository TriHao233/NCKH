import { useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faArrowRight, faClipboardCheck, faMagnifyingGlass, faRobot } from '@fortawesome/free-solid-svg-icons';
import {
  assignQuestionReview,
  autoEvaluateQuestion,
  claimQuestionReview,
  getReviewDashboard,
  listQuestions,
  publishQuestionToMoodle,
  reviewQuestion,
} from '../../api/questions';
import { listAvailableAiModels } from '../../api/catalog';
import { AuthContext } from '../../context/AuthContext';
import { BLOOM_LEVELS, QUESTION_TYPES, questionTypeLabel } from '../../constants/generationEnums';
import WorkspaceHero from '../../components/workspace/WorkspaceHero';
import MoreMenu from '../../components/workspace/MoreMenu';
import BulkBar from '../../components/workspace/BulkBar';
import Drawer from '../../components/workspace/Drawer';
import { EmptyState, ErrorState, Notice, SkeletonRows } from '../../components/workspace/Feedback';
import { Dialog, useConfirm, useFlash } from '../../components/workspace/Dialog';
import { FilterChips, FilterToggle } from '../../components/workspace/Filters';
import { Pagination, Tabs } from '../../components/workspace/Navigation';
import { claimNextQuestion, fetchAllQuestions, useReviewLookups, userName } from '../../features/review/reviewData';
import {
  EVALUATION_RETRY_STATUSES,
  INBOX_CLIENT_FILTERS,
  EVALUATION_STATUS_LABEL,
  PUBLICATION_STATUS_LABEL,
  QUALITY_LABEL,
  QUALITY_TONE,
  REVIEW_STATUS_LABEL,
  REVIEW_STATUS_TONE,
  SECONDARY_STATUS_LABEL,
  SORT_OPTIONS,
  assignmentOf,
  buildReviewPayload,
  canClaim,
  canDecide,
  canRequestEvaluation,
  childId,
  defaultDraft,
  formatScore,
  formatWaiting,
  inboxTabsFor,
  isAssignedToUser,
  isBlockedFromSecondary,
  isObjectId,
  isPending,
  isResubmission,
  isUnassigned,
  qualityOf,
  questionTypeKey,
  refId,
} from '../../features/review/reviewModel';
import '../../css/workspace.css';
import '../../css/ReviewPage.css';
import '../../css/ReviewDesk.css';

const PAGE_SIZE = 20;
const BULK_APPROVE_LIMIT = 10;

const EMPTY_FILTERS = {
  subjectId: '',
  chapterId: '',
  cloId: '',
  questionType: '',
  bloomLevel: '',
  evaluationStatus: '',
  qualityColor: '',
  minScore: '',
  sourcePresence: '',
  secondaryStatus: '',
  creatorUserId: '',
  submittedFrom: '',
  submittedTo: '',
};

const TAB_EMPTY = {
  mine: ['Bạn chưa giữ câu nào', 'Bấm "Duyệt câu tiếp theo" để nhận câu ưu tiên cao nhất.'],
  unassigned: ['Không còn câu chưa ai nhận', 'Câu giảng viên gửi duyệt sẽ xuất hiện ở đây kèm gợi ý của AI.'],
  resubmitted: ['Chưa có câu gửi lại', 'Câu bị yêu cầu sửa và được giảng viên gửi lại sẽ nằm ở đây.'],
  overdue: ['Không có câu quá hạn', 'Câu bị giữ quá thời gian khoá sẽ hiện ở đây để người khác nhận lại.'],
  processed: ['Chưa có câu đã xử lý', 'Câu đã duyệt, yêu cầu sửa hoặc từ chối sẽ nằm ở đây.'],
  moodle: ['Không còn câu chờ lên Moodle', 'Câu đã duyệt nhưng chưa đồng bộ Moodle sẽ nằm ở đây.'],
  all: ['Hàng chờ đang trống', 'Chưa có câu nào đang chờ kiểm duyệt.'],
};

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function chapterName(question, subjectsById) {
  const chapterId = refId(question?.classification?.chapter);
  if (!chapterId) return '';
  const subject = subjectsById.get(refId(question?.subject_id || question?.classification?.subject));
  const chapter = (subject?.chapters || []).find((item) => childId(item) === chapterId);
  return chapter ? (chapter.chapter_code || chapter.chapter_name) : '';
}

function subjectShort(question, subjectsById) {
  const snapshot = question?.subject || question?.review_submission?.subject || {};
  if (snapshot.code) return snapshot.code;
  const subject = subjectsById.get(refId(question?.subject_id || question?.classification?.subject));
  return subject?.subject_code || snapshot.name || '--';
}

function ReviewInboxPage() {
  const { user } = useContext(AuthContext);
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const lookups = useReviewLookups();
  const { flash, show: showFlash, clear: clearFlash } = useFlash();
  const [confirm, confirmDialog] = useConfirm();
  const isAdminUser = user?.role === 'Admin';
  const tabs = useMemo(() => inboxTabsFor(user), [user]);

  const legacyQuestionId = searchParams.get('questionId') || '';
  const requestedTab = searchParams.get('tab') || (searchParams.get('status') === 'PENDING' ? (isAdminUser ? 'all' : 'unassigned') : '');

  const [counts, setCounts] = useState({});
  const [countsLoaded, setCountsLoaded] = useState(false);
  const [autoTab, setAutoTab] = useState('');
  const tab = tabs.some((item) => item.value === requestedTab) ? requestedTab : (autoTab || 'mine');
  const tabDef = tabs.find((item) => item.value === tab) || tabs[0];

  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState('priority');
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [selected, setSelected] = useState(() => new Set());
  const [busy, setBusy] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [assignDrawer, setAssignDrawer] = useState(null);
  const [evalDialog, setEvalDialog] = useState(null);
  const [evalModels, setEvalModels] = useState([]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setSearchTerm(searchInput.trim());
      setPage(1);
    }, 350);
    return () => window.clearTimeout(handle);
  }, [searchInput]);

  // Bộ đếm cho các tab.
  const loadCounts = useCallback(async () => {
    const [dashboard, processed, moodle, pendingAll] = await Promise.allSettled([
      getReviewDashboard(),
      listQuestions({ page: 1, pageSize: 1, reviewStatus: 'PROCESSED' }),
      listQuestions({ page: 1, pageSize: 1, reviewStatus: 'APPROVED', publicationStatus: 'NOT_PUBLISHED' }),
      fetchAllQuestions({ reviewStatus: 'PENDING' }),
    ]);
    const workload = dashboard.status === 'fulfilled' ? (dashboard.value.workload || {}) : {};
    const next = {
      mine: workload.mine,
      unassigned: pendingAll.status === 'fulfilled' ? pendingAll.value.filter(isUnassigned).length : workload.unassigned,
      overdue: workload.lock_expired,
      all: workload.pending,
      processed: processed.status === 'fulfilled' ? processed.value.total || 0 : undefined,
      moodle: moodle.status === 'fulfilled' ? moodle.value.total || 0 : undefined,
      resubmitted: pendingAll.status === 'fulfilled' ? pendingAll.value.filter(isResubmission).length : undefined,
    };
    setCounts(next);
    setCountsLoaded(true);
    return next;
  }, []);

  useEffect(() => {
    loadCounts().then((next) => {
      // Lần đầu mở: nếu chưa giữ câu nào thì vào thẳng tab "Chưa ai nhận".
      setAutoTab((current) => current || (next.mine ? 'mine' : 'unassigned'));
    });
  }, [loadCounts, refreshKey]);

  const queryFor = useCallback((extra = {}) => ({
    ...tabDef.query,
    search: searchTerm ? escapeRegex(searchTerm) : undefined,
    subjectId: filters.subjectId || undefined,
    chapterId: filters.chapterId || undefined,
    cloId: filters.cloId || undefined,
    questionType: filters.questionType || undefined,
    bloomLevel: filters.bloomLevel || undefined,
    evaluationStatus: filters.evaluationStatus || undefined,
    qualityColor: filters.qualityColor || undefined,
    minScore: filters.minScore || undefined,
    sourcePresence: filters.sourcePresence || undefined,
    secondaryStatus: filters.secondaryStatus || undefined,
    creatorUserId: filters.creatorUserId || undefined,
    submittedFrom: filters.submittedFrom || undefined,
    submittedTo: filters.submittedTo || undefined,
    sortBy: tab === 'processed' && sortBy === 'priority' ? 'updated' : sortBy,
    ...extra,
  }), [filters, searchTerm, sortBy, tab, tabDef]);

  useEffect(() => {
    if (!countsLoaded && !requestedTab) return undefined;
    let active = true;
    setLoading(true);
    setLoadError('');
    const clientFilter = INBOX_CLIENT_FILTERS[tabDef.clientFilter];
    const request = clientFilter
      ? fetchAllQuestions(queryFor()).then((items) => {
          const matched = items.filter(clientFilter);
          return { items: matched.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE), total: matched.length };
        })
      : listQuestions(queryFor({ page, pageSize: PAGE_SIZE }));
    request
      .then((result) => {
        if (!active) return;
        setRows(result.items || []);
        setTotal(result.total || 0);
      })
      .catch((error) => {
        if (!active) return;
        setRows([]);
        setTotal(0);
        setLoadError(error.message || 'Không tải được danh sách câu hỏi.');
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [queryFor, page, refreshKey, tabDef, countsLoaded, requestedTab]);

  useEffect(() => {
    setSelected(new Set());
  }, [tab, page, filters, searchTerm, refreshKey]);

  // Quay lại tab trình duyệt thì làm mới, tránh nhận nhầm câu người khác vừa giữ.
  useEffect(() => {
    const handleVisible = () => {
      if (document.visibilityState === 'visible') setRefreshKey((key) => key + 1);
    };
    document.addEventListener('visibilitychange', handleVisible);
    return () => document.removeEventListener('visibilitychange', handleVisible);
  }, []);

  const refresh = () => setRefreshKey((key) => key + 1);

  const selectTab = (value) => {
    setSearchParams({ tab: value });
    setPage(1);
  };

  const updateFilter = (key, value) => {
    setFilters((current) => ({
      ...current,
      [key]: value,
      ...(key === 'subjectId' ? { chapterId: '', cloId: '' } : {}),
    }));
    setPage(1);
  };

  const resetFilters = () => {
    setFilters(EMPTY_FILTERS);
    setSearchInput('');
    setPage(1);
  };

  const selectedSubject = lookups.subjects.find((subject) => refId(subject) === filters.subjectId);
  const chips = [
    filters.subjectId && { key: 'subjectId', label: `Học phần: ${selectedSubject?.subject_code || '...'}` },
    filters.chapterId && { key: 'chapterId', label: `Chương: ${(selectedSubject?.chapters || []).find((item) => childId(item) === filters.chapterId)?.chapter_code || '...'}` },
    filters.cloId && { key: 'cloId', label: `CLO: ${(selectedSubject?.learning_outcomes || []).find((item) => childId(item) === filters.cloId)?.clo_code || '...'}` },
    filters.questionType && { key: 'questionType', label: questionTypeLabel(filters.questionType) },
    filters.bloomLevel && { key: 'bloomLevel', label: `Bloom ${filters.bloomLevel}` },
    filters.evaluationStatus && { key: 'evaluationStatus', label: EVALUATION_STATUS_LABEL[filters.evaluationStatus] },
    filters.qualityColor && { key: 'qualityColor', label: `Chất lượng: ${QUALITY_LABEL[filters.qualityColor]}` },
    filters.minScore && { key: 'minScore', label: `Điểm AI từ ${filters.minScore}` },
    filters.sourcePresence && { key: 'sourcePresence', label: filters.sourcePresence === 'WITH_SOURCE' ? 'Có nguồn' : 'Thiếu nguồn' },
    filters.secondaryStatus && { key: 'secondaryStatus', label: SECONDARY_STATUS_LABEL[filters.secondaryStatus] },
    filters.creatorUserId && { key: 'creatorUserId', label: `Giảng viên: ${userName(lookups.teachersById.get(filters.creatorUserId), '...')}` },
    filters.submittedFrom && { key: 'submittedFrom', label: `Gửi từ ${filters.submittedFrom}` },
    filters.submittedTo && { key: 'submittedTo', label: `Gửi đến ${filters.submittedTo}` },
  ].filter(Boolean).map((chip) => ({ ...chip, onRemove: () => updateFilter(chip.key, '') }));
  const advancedCount = chips.filter((chip) => chip.key !== 'subjectId').length;
  const hasFilters = chips.length > 0 || Boolean(searchTerm);

  const returnTo = `${location.pathname}${location.search}`;
  const openQuestion = (question) => {
    navigate(`/kiem-duyet/${question.id}`, {
      state: { returnTo, queue: rows.map((item) => item.id) },
    });
  };

  const handleNext = async () => {
    setBusy('next');
    clearFlash();
    try {
      const question = await claimNextQuestion(user);
      if (!question) {
        showFlash('info', 'Hiện không còn câu nào chờ duyệt. Bạn có thể quay lại sau.');
        refresh();
        return;
      }
      navigate(`/kiem-duyet/${question.id}`, { state: { returnTo, queue: [] } });
    } catch (error) {
      showFlash('error', error.message || 'Không nhận được câu tiếp theo.');
    } finally {
      setBusy('');
    }
  };

  // ─── Chọn nhiều ──────────────────────────────────────────────
  const toggleRow = (id) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const allChecked = rows.length > 0 && rows.every((row) => selected.has(row.id));
  const toggleAll = () => setSelected(allChecked ? new Set() : new Set(rows.map((row) => row.id)));
  const selectedRows = rows.filter((row) => selected.has(row.id));

  const approvable = selectedRows
    .filter((row) => isPending(row) && row.evaluation_status === 'PASSED' && !isBlockedFromSecondary(row, user))
    .filter((row) => canDecide(row, user) || canClaim(row, user))
    .slice(0, BULK_APPROVE_LIMIT);
  const claimable = selectedRows.filter((row) => canClaim(row, user) && !(isAssignedToUser(row, user) && assignmentOf(row).status === 'IN_REVIEW'));
  const publishable = selectedRows.filter((row) => row.review_status === 'APPROVED' && row.publication_status !== 'PUBLISHED');

  const runBulk = async (key, items, action, doneLabel) => {
    setBusy(key);
    clearFlash();
    let failed = 0;
    const errors = [];
    for (const item of items) {
      try {
        await action(item);
      } catch (error) {
        failed += 1;
        if (errors.length < 2) errors.push(`${item.question_code}: ${error.message}`);
      }
    }
    setBusy('');
    showFlash(
      failed ? 'warn' : 'success',
      failed
        ? `${doneLabel} ${items.length - failed}/${items.length} câu. Lỗi: ${errors.join('; ')}`
        : `${doneLabel} ${items.length} câu.`,
    );
    refresh();
  };

  const bulkApprove = async () => {
    const accepted = await confirm({
      title: `Duyệt ${approvable.length} câu AI đề xuất đạt`,
      description: 'Mỗi câu được ghi nhận là bạn đã duyệt, với đủ mục kiểm tra và tiêu chí "Đạt". Chỉ dùng khi bạn đã xem qua các câu này.',
      confirmLabel: `Duyệt ${approvable.length} câu`,
    });
    if (!accepted) return;
    await runBulk('approve', approvable, async (question) => {
      let current = question;
      if (!canDecide(current, user)) current = await claimQuestionReview(current.id);
      const draft = defaultDraft(current, 'APPROVED');
      await reviewQuestion(current.id, buildReviewPayload(current, {
        ...draft,
        checklist: draft.checklist.map((item) => ({ ...item, passed: true })),
        overallNote: 'Duyệt theo danh sách: AI đề xuất đạt và người duyệt đã rà soát.',
      }));
    }, 'Đã duyệt');
  };

  const bulkClaim = () => runBulk('claim', claimable, (question) => claimQuestionReview(question.id), 'Đã nhận');

  const bulkPublish = async () => {
    const accepted = await confirm({
      title: `Xuất bản ${publishable.length} câu lên Moodle`,
      description: 'Các câu sẽ được đồng bộ theo điểm đồng bộ Moodle mặc định (chế độ mô phỏng).',
      confirmLabel: 'Xuất bản',
    });
    if (!accepted) return;
    await runBulk('publish', publishable, (question) => publishQuestionToMoodle(question.id, {
      expected_version: question.current_version,
      export_format: 'BOTH',
      mock: true,
    }), 'Đã xuất bản');
  };

  const submitAssign = async () => {
    const targets = assignDrawer.items;
    const reviewerId = assignDrawer.reviewerId;
    setAssignDrawer(null);
    await runBulk('assign', targets, (question) => assignQuestionReview(question.id, {
      reviewer_user_id: reviewerId || null,
      note: assignDrawer.note.trim(),
    }), reviewerId ? 'Đã giao' : 'Đã bỏ giao');
  };

  // ─── Đánh giá lại bằng AI ───────────────────────────────────
  const openEvaluate = async () => {
    setEvalDialog({ modelCode: '', scope: 'filtered', error: '' });
    try {
      const result = await listAvailableAiModels('QUESTION_EVALUATION');
      setEvalModels(result.items || []);
      setEvalDialog((current) => current && ({ ...current, modelCode: result.default_model_code || result.items?.[0]?.code || '' }));
    } catch {
      setEvalModels([]);
    }
  };

  const submitEvaluate = async () => {
    const { scope, modelCode } = evalDialog;
    setEvalDialog(null);
    setBusy('evaluate');
    try {
      const source = scope === 'failed'
        ? await fetchAllQuestions({ reviewStatus: 'PENDING', evaluationStatus: EVALUATION_RETRY_STATUSES.join(',') })
        : rows;
      const targets = source.filter(canRequestEvaluation).slice(0, scope === 'failed' ? 200 : 10);
      if (!targets.length) {
        setBusy('');
        showFlash('info', 'Không có câu nào cần AI đánh giá lại trong phạm vi đã chọn.');
        return;
      }
      await runBulk('evaluate', targets, (question) => autoEvaluateQuestion(question.id, {
        expected_version: question.current_version,
        fallback_to_heuristic: false,
        ...(modelCode ? { evaluator_model_code: modelCode } : {}),
      }), 'Đã gửi AI đánh giá lại');
    } catch (error) {
      setBusy('');
      showFlash('error', error.message || 'Không gửi được yêu cầu đánh giá.');
    }
  };

  if (isObjectId(legacyQuestionId)) {
    return <Navigate to={`/kiem-duyet/${legacyQuestionId}`} replace />;
  }

  const pendingTab = !['processed', 'moodle'].includes(tab);
  const [emptyTitle, emptyText] = TAB_EMPTY[tab] || TAB_EMPTY.all;

  return (
    <main className="ws-page review-inbox-page">
      <WorkspaceHero
        badge={isAdminUser ? 'Quản trị kiểm duyệt' : 'Người duyệt'}
        title="Hộp việc"
        description="Nhận câu, đối chiếu nguồn và gợi ý AI, rồi chốt kết quả để giảng viên sửa hoặc đưa vào ngân hàng."
        actions={(
          <>
            <MoreMenu
              items={[
                { key: 'eval', label: 'Đánh giá lại bằng AI', icon: faRobot, onClick: openEvaluate, disabled: Boolean(busy) },
              ]}
            />
            <button type="button" className="btn btn--primary" onClick={handleNext} disabled={Boolean(busy)}>
              <FontAwesomeIcon icon={faArrowRight} />
              {busy === 'next' ? 'Đang tìm câu...' : 'Duyệt câu tiếp theo'}
            </button>
          </>
        )}
      >
        <Tabs
          label="Nhóm câu hỏi"
          value={tab}
          onChange={selectTab}
          items={tabs.map((item) => ({ value: item.value, label: item.label, count: counts[item.value] }))}
        />
      </WorkspaceHero>

      <section className="ws-body">
        <div className="container ws-main">
          {flash && <Notice tone={flash.tone} onDismiss={clearFlash}>{flash.message}</Notice>}

          <section className="ws-card">
            <div className="ws-card-head">
              <div className="ws-card-title">
                <h2>{tabDef.label}</h2>
                <span className="ws-list-count tabular">
                  {loading ? 'Đang tải...' : `${rows.length} / ${total} câu đang hiển thị`}
                </span>
              </div>
              <select
                className="ws-select"
                style={{ width: 'auto' }}
                aria-label="Sắp xếp"
                value={tab === 'processed' && sortBy === 'priority' ? 'updated' : sortBy}
                onChange={(event) => {
                  setSortBy(event.target.value);
                  setPage(1);
                }}
              >
                {SORT_OPTIONS.filter((option) => tab !== 'processed' || option.value !== 'priority')
                  .map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </div>

            <div className="ws-toolbar">
              <label className="ws-search">
                <span className="ws-sr-only">Tìm câu hỏi</span>
                <FontAwesomeIcon icon={faMagnifyingGlass} />
                <input
                  className="ws-input"
                  value={searchInput}
                  onChange={(event) => setSearchInput(event.target.value)}
                  placeholder="Tìm theo mã hoặc nội dung câu hỏi"
                />
              </label>
              <select className="ws-select" aria-label="Học phần" value={filters.subjectId} onChange={(event) => updateFilter('subjectId', event.target.value)}>
                <option value="">Tất cả học phần</option>
                {lookups.subjects.map((subject) => (
                  <option key={refId(subject)} value={refId(subject)}>
                    {[subject.subject_code, subject.subject_name].filter(Boolean).join(' - ')}
                  </option>
                ))}
              </select>
              <FilterToggle open={filtersOpen} count={advancedCount} onToggle={() => setFiltersOpen((value) => !value)} />
            </div>

            {filtersOpen && (
              <div className="ws-filter-panel">
                <label className="ws-field">
                  <span>Chương</span>
                  <select className="ws-select" value={filters.chapterId} disabled={!selectedSubject} title={selectedSubject ? undefined : 'Chọn học phần trước'} onChange={(event) => updateFilter('chapterId', event.target.value)}>
                    <option value="">{selectedSubject ? 'Tất cả' : 'Chọn học phần trước'}</option>
                    {(selectedSubject?.chapters || []).map((chapter) => (
                      <option key={childId(chapter)} value={childId(chapter)}>{[chapter.chapter_code, chapter.chapter_name].filter(Boolean).join(' - ')}</option>
                    ))}
                  </select>
                </label>
                <label className="ws-field">
                  <span>CLO</span>
                  <select className="ws-select" value={filters.cloId} disabled={!selectedSubject} title={selectedSubject ? undefined : 'Chọn học phần trước'} onChange={(event) => updateFilter('cloId', event.target.value)}>
                    <option value="">{selectedSubject ? 'Tất cả' : 'Chọn học phần trước'}</option>
                    {(selectedSubject?.learning_outcomes || []).map((clo) => (
                      <option key={childId(clo)} value={childId(clo)}>{clo.clo_code}</option>
                    ))}
                  </select>
                </label>
                <label className="ws-field">
                  <span>Loại câu</span>
                  <select className="ws-select" value={filters.questionType} onChange={(event) => updateFilter('questionType', event.target.value)}>
                    <option value="">Tất cả</option>
                    {QUESTION_TYPES.map((type) => <option key={type.backend} value={type.backend}>{type.label}</option>)}
                  </select>
                </label>
                <label className="ws-field">
                  <span>Cấp Bloom</span>
                  <select className="ws-select" value={filters.bloomLevel} onChange={(event) => updateFilter('bloomLevel', event.target.value)}>
                    <option value="">Tất cả</option>
                    {BLOOM_LEVELS.map((level) => <option key={level.level} value={level.level}>{level.label}</option>)}
                  </select>
                </label>
                <label className="ws-field">
                  <span>Chất lượng theo AI</span>
                  <select className="ws-select" value={filters.qualityColor} onChange={(event) => updateFilter('qualityColor', event.target.value)}>
                    <option value="">Tất cả</option>
                    {Object.entries(QUALITY_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
                <label className="ws-field">
                  <span>Điểm AI tối thiểu</span>
                  <select className="ws-select" value={filters.minScore} onChange={(event) => updateFilter('minScore', event.target.value)}>
                    <option value="">Bất kỳ</option>
                    <option value="0.5">Từ 0.50</option>
                    <option value="0.65">Từ 0.65</option>
                    <option value="0.8">Từ 0.80</option>
                  </select>
                </label>
                <label className="ws-field">
                  <span>Trạng thái đánh giá AI</span>
                  <select className="ws-select" value={filters.evaluationStatus} onChange={(event) => updateFilter('evaluationStatus', event.target.value)}>
                    <option value="">Tất cả</option>
                    {Object.entries(EVALUATION_STATUS_LABEL).filter(([value]) => value !== 'RUNNING')
                      .map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
                <label className="ws-field">
                  <span>Giảng viên gửi</span>
                  <select className="ws-select" value={filters.creatorUserId} onChange={(event) => updateFilter('creatorUserId', event.target.value)}>
                    <option value="">Tất cả</option>
                    {lookups.teachers.map((teacher) => <option key={refId(teacher)} value={refId(teacher)}>{userName(teacher)}</option>)}
                  </select>
                </label>
                <label className="ws-field">
                  <span>Gửi duyệt từ ngày</span>
                  <input type="date" className="ws-input" value={filters.submittedFrom} max={filters.submittedTo || undefined} onChange={(event) => updateFilter('submittedFrom', event.target.value)} />
                </label>
                <label className="ws-field">
                  <span>Đến ngày</span>
                  <input type="date" className="ws-input" value={filters.submittedTo} min={filters.submittedFrom || undefined} onChange={(event) => updateFilter('submittedTo', event.target.value)} />
                </label>
                <label className="ws-field">
                  <span>Nguồn tham chiếu</span>
                  <select className="ws-select" value={filters.sourcePresence} onChange={(event) => updateFilter('sourcePresence', event.target.value)}>
                    <option value="">Tất cả</option>
                    <option value="WITH_SOURCE">Có nguồn</option>
                    <option value="MISSING_SOURCE">Thiếu nguồn</option>
                  </select>
                </label>
                <label className="ws-field">
                  <span>Vòng 2</span>
                  <select className="ws-select" value={filters.secondaryStatus} onChange={(event) => updateFilter('secondaryStatus', event.target.value)}>
                    <option value="">Tất cả</option>
                    <option value="AWAITING_SECONDARY">Chờ duyệt lần 2</option>
                    <option value="COMPLETED">Đã duyệt lần 2</option>
                  </select>
                </label>
              </div>
            )}
            <FilterChips chips={chips} onClearAll={resetFilters} />
            {lookups.failed && (
              <div style={{ marginTop: 12 }}>
                <Notice tone="warn">Một số danh mục chưa tải được nên bộ lọc có thể thiếu lựa chọn.</Notice>
              </div>
            )}

            <div style={{ marginTop: 14 }}>
              {loading ? (
                <SkeletonRows rows={6} lines={2} />
              ) : loadError ? (
                <ErrorState message={loadError} onRetry={refresh} />
              ) : rows.length === 0 ? (
                <EmptyState
                  icon={faClipboardCheck}
                  title={hasFilters ? 'Không có câu khớp bộ lọc' : emptyTitle}
                  description={hasFilters ? 'Thử bỏ bớt điều kiện lọc hoặc đổi từ khoá.' : emptyText}
                  action={hasFilters ? <button type="button" className="btn btn--outline btn--sm" onClick={resetFilters}>Xoá bộ lọc</button> : null}
                />
              ) : (
                <div className="ws-table-wrap">
                  <table className="ws-table rv-inbox-table">
                    <thead>
                      <tr>
                        <th className="ws-col-check">
                          <input type="checkbox" aria-label="Chọn tất cả trên trang" checked={allChecked} onChange={toggleAll} />
                        </th>
                        <th>Câu hỏi</th>
                        <th>Học phần</th>
                        <th>Loại</th>
                        <th>Gợi ý AI</th>
                        <th>{pendingTab ? 'Chờ' : 'Kết quả'}</th>
                        <th>{pendingTab ? 'Người giữ' : 'Moodle'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((question) => {
                        const quality = qualityOf(question);
                        const assignment = assignmentOf(question);
                        const holder = assignment.reviewerUserId
                          ? (isAssignedToUser(question, user) ? 'Bạn' : userName(lookups.reviewersById.get(assignment.reviewerUserId), 'Người khác'))
                          : '';
                        const chapter = chapterName(question, lookups.subjectsById);
                        return (
                          <tr
                            key={question.id}
                            data-clickable="true"
                            className={selected.has(question.id) ? 'is-selected' : ''}
                            onClick={() => openQuestion(question)}
                          >
                            <td className="ws-col-check" onClick={(event) => event.stopPropagation()}>
                              <input
                                type="checkbox"
                                aria-label={`Chọn ${question.question_code}`}
                                checked={selected.has(question.id)}
                                onChange={() => toggleRow(question.id)}
                              />
                            </td>
                            <td style={{ maxWidth: 420 }}>
                              <span className="ws-code">{question.question_code}</span>
                              <span className="ws-clip-1" title={question.content}>{question.content}</span>
                              <span className="rv-row-flags">
                                {isResubmission(question) && <span className="ws-pill ws-pill--info">Gửi lại</span>}
                                {question.secondary_review?.status === 'AWAITING_SECONDARY' && <span className="ws-pill ws-pill--info">Vòng 2</span>}
                                {(!question.sources || question.sources.length === 0) && <span className="ws-pill ws-pill--warn">Thiếu nguồn</span>}
                              </span>
                            </td>
                            <td>
                              {subjectShort(question, lookups.subjectsById)}
                              {chapter && <small>{chapter}</small>}
                            </td>
                            <td>
                              {questionTypeLabel(questionTypeKey(question)) || '--'}
                              <small>Bloom {question.classification?.bloom?.level || '--'}</small>
                            </td>
                            <td>
                              <span className={`ws-pill ${quality.color ? `ws-pill--${QUALITY_TONE[quality.color]}` : ''} tabular`}>
                                {quality.score === null ? (EVALUATION_STATUS_LABEL[question.evaluation_status] || 'Chưa đánh giá') : `${formatScore(quality.score)} ${QUALITY_LABEL[quality.color] || ''}`}
                              </span>
                            </td>
                            <td>
                              {pendingTab
                                ? (formatWaiting(question.review_submission?.submitted_at || question.submitted_at) || '--')
                                : (
                                  <span className={`ws-pill ws-pill--${REVIEW_STATUS_TONE[question.review_status] || 'outline'}`}>
                                    {REVIEW_STATUS_LABEL[question.review_status] || question.review_status}
                                  </span>
                                )}
                            </td>
                            <td>
                              {pendingTab
                                ? (holder || <span className="ws-muted">Chưa ai nhận</span>)
                                : (question.review_status === 'APPROVED' ? PUBLICATION_STATUS_LABEL[question.publication_status] || '--' : '--')}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              <Pagination page={page} pageSize={PAGE_SIZE} total={total} loading={loading} onChange={setPage} />
            </div>
          </section>
        </div>
      </section>

      <BulkBar count={selected.size} onClear={() => setSelected(new Set())}>
        {pendingTab && (
          <button
            type="button"
            className="btn btn--primary btn--sm"
            disabled={Boolean(busy) || approvable.length === 0}
            title={approvable.length === 0 ? 'Chỉ duyệt nhanh được câu đang chờ mà AI đề xuất đạt' : `Tối đa ${BULK_APPROVE_LIMIT} câu mỗi lần`}
            onClick={bulkApprove}
          >
            Duyệt các câu AI đề xuất đạt ({approvable.length})
          </button>
        )}
        {pendingTab && (
          <button
            type="button"
            className="btn btn--outline btn--sm"
            disabled={Boolean(busy) || claimable.length === 0}
            title={claimable.length === 0 ? 'Không có câu nào nhận được trong các câu đã chọn' : undefined}
            onClick={bulkClaim}
          >
            Nhận ({claimable.length})
          </button>
        )}
        {pendingTab && isAdminUser && (
          <button
            type="button"
            className="btn btn--outline btn--sm"
            disabled={Boolean(busy)}
            onClick={() => setAssignDrawer({ items: selectedRows.filter(isPending), reviewerId: '', note: '' })}
          >
            Giao cho...
          </button>
        )}
        {tab === 'moodle' && (
          <button
            type="button"
            className="btn btn--primary btn--sm"
            disabled={Boolean(busy) || publishable.length === 0}
            onClick={bulkPublish}
          >
            Xuất bản Moodle ({publishable.length})
          </button>
        )}
      </BulkBar>

      <Drawer
        open={Boolean(assignDrawer)}
        title="Giao câu cho người duyệt"
        subtitle={assignDrawer ? `${assignDrawer.items.length} câu đang chờ duyệt` : ''}
        onClose={() => setAssignDrawer(null)}
        as="form"
        onSubmit={submitAssign}
        footer={(
          <>
            <button type="button" className="btn btn--outline" onClick={() => setAssignDrawer(null)}>Huỷ</button>
            <button type="submit" className="btn btn--primary">Lưu phân công</button>
          </>
        )}
      >
        {assignDrawer && (
          <>
            <label className="ws-field">
              <span>Người duyệt</span>
              <select className="ws-select" value={assignDrawer.reviewerId} onChange={(event) => setAssignDrawer({ ...assignDrawer, reviewerId: event.target.value })}>
                <option value="">Bỏ giao, trả về hàng chờ chung</option>
                {lookups.reviewers.map((reviewer) => <option key={refId(reviewer)} value={refId(reviewer)}>{userName(reviewer)}</option>)}
              </select>
              <small>Người được giao nhận thông báo và giữ câu trong 30 phút kể từ lúc giao.</small>
            </label>
            <label className="ws-field">
              <span>Ghi chú</span>
              <textarea className="ws-textarea" maxLength={500} value={assignDrawer.note} onChange={(event) => setAssignDrawer({ ...assignDrawer, note: event.target.value })} />
            </label>
          </>
        )}
      </Drawer>

      <Dialog
        open={Boolean(evalDialog)}
        title="Đánh giá lại bằng AI"
        description="AI chỉ đưa ra gợi ý; người duyệt vẫn là người quyết định."
        onClose={() => setEvalDialog(null)}
        as="form"
        onSubmit={submitEvaluate}
        footer={(
          <>
            <button type="button" className="btn btn--outline" onClick={() => setEvalDialog(null)}>Huỷ</button>
            <button type="submit" className="btn btn--primary">Gửi đánh giá</button>
          </>
        )}
      >
        {evalDialog && (
          <>
            <label className="ws-field">
              <span>Phạm vi</span>
              <select className="ws-select" value={evalDialog.scope} onChange={(event) => setEvalDialog({ ...evalDialog, scope: event.target.value })}>
                <option value="filtered">Các câu đang hiển thị cần đánh giá (tối đa 10)</option>
                <option value="failed">Mọi câu chờ duyệt có kết quả AI lỗi, cũ hoặc thiếu minh chứng</option>
              </select>
            </label>
            <label className="ws-field">
              <span>Mô hình đánh giá</span>
              <select className="ws-select" value={evalDialog.modelCode} onChange={(event) => setEvalDialog({ ...evalDialog, modelCode: event.target.value })}>
                {evalModels.length === 0 && <option value="">Mô hình mặc định của hệ thống</option>}
                {evalModels.map((model) => <option key={model.code} value={model.code}>{model.name || model.code}</option>)}
              </select>
            </label>
          </>
        )}
      </Dialog>
      {confirmDialog}
    </main>
  );
}

export default ReviewInboxPage;
