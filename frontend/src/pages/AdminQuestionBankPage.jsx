import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faChevronLeft, faChevronRight, faDownload, faPlus, faRotateRight } from '@fortawesome/free-solid-svg-icons';
import {
  createQuestion,
  deleteQuestion,
  getQuestion,
  listQuestionReviews,
  listQuestionVersions,
  listQuestions,
  updateQuestion,
  updateQuestionSharing,
} from '../api/questions';
import { listSubjects } from '../api/catalog';
import { listUsers } from '../api/users';
import QuestionContent from '../components/QuestionContent';
import QuestionEditorDialog from '../components/questionBank/QuestionEditorDialog';
import { BLOOM_LEVELS, DIFFICULTIES, QUESTION_TYPES, difficultyLabel, questionTypeLabel } from '../constants/generationEnums';
import { downloadCsv, downloadXlsx, rowsToCsv, timestampedCsvFilename, timestampedXlsxFilename } from '../utils/csvExport';
import {
  QUESTION_BANK_EXPORT_COLUMNS,
  downloadTextFile,
  questionsToGift,
  questionsToMoodleXml,
  timestampedQuestionBankFilename,
} from '../utils/questionBankExchange';
import {
  PUBLICATION_STATUS,
  QUALITY_COLORS,
  REVIEW_STATUS,
  REVIEW_STATUS_ORDER,
  aiSummaryOf,
  authorOf,
  originLabel,
  publicationStatusOf,
  questionTypeOf,
  reviewStatusOf,
  statusTotal,
  subjectOf,
} from '../utils/questionBankView';
import { correctAnswerValues, optionEntriesForQuestion } from '../utils/questionOptions';
import '../css/AdminJobsPage.css';
import '../css/AdminQuestionBankPage.css';

const PAGE_SIZE = 20;
const EMPTY_FILTERS = {
  status: 'all',
  creatorUserId: '',
  subjectId: '',
  questionType: '',
  qualityColor: '',
  publicationStatus: '',
  bloomLevel: '',
  difficulty: '',
  createdFrom: '',
  createdTo: '',
  sortBy: 'updated',
};
const SORT_OPTIONS = [
  { value: 'updated', label: 'Mới cập nhật' },
  { value: 'newest', label: 'Mới tạo' },
  { value: 'oldest', label: 'Cũ nhất' },
  { value: 'ai_lowest', label: 'Điểm AI thấp trước' },
];
// Ghi chú mặc định do máy chủ tự điền bằng tiếng Anh.
const CHANGE_NOTE_LABEL = { 'Initial version': 'Phiên bản đầu tiên', 'Question edited': 'Cập nhật câu hỏi' };
const EXPORT_FORMATS = [
  { value: 'xlsx', label: 'Excel (XLSX)' },
  { value: 'csv', label: 'CSV' },
  { value: 'gift', label: 'GIFT' },
  { value: 'xml', label: 'XML Moodle' },
];

function refId(value) {
  if (!value) return '';
  return typeof value === 'string' ? value : value.id || value._id || '';
}

function formatDateTime(value) {
  if (!value) return '--';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '--' : date.toLocaleString('vi-VN');
}

function formatDate(value) {
  if (!value) return '--';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '--' : date.toLocaleDateString('vi-VN');
}

async function fetchAllUsers() {
  const first = await listUsers({ page: 1, pageSize: 100 });
  const items = [...(first.items || [])];
  for (let page = 2; items.length < (first.total || 0); page += 1) {
    const next = await listUsers({ page, pageSize: 100 });
    if (!next.items?.length) break;
    items.push(...next.items);
  }
  return items;
}

function AdminQuestionBankPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState(() => ({
    ...EMPTY_FILTERS,
    status: REVIEW_STATUS[searchParams.get('status')] ? searchParams.get('status') : 'all',
  }));
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [moreFilters, setMoreFilters] = useState(false);
  const [page, setPage] = useState(1);
  const [questions, setQuestions] = useState([]);
  const [total, setTotal] = useState(0);
  const [statusCounts, setStatusCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState(null);
  const [subjects, setSubjects] = useState([]);
  const [users, setUsers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [history, setHistory] = useState({ loading: false, versions: [], reviews: [] });
  const [editor, setEditor] = useState(null);
  const [editorError, setEditorError] = useState('');
  const [saving, setSaving] = useState(false);
  const [archiveConfirmation, setArchiveConfirmation] = useState(null);
  const [sharing, setSharing] = useState(null);
  const [sharingError, setSharingError] = useState('');
  const [exportFormat, setExportFormat] = useState('xlsx');
  const [exporting, setExporting] = useState(false);

  const userById = useMemo(() => new Map(users.map((user) => [user.id, user])), [users]);
  const subjectById = useMemo(() => new Map(subjects.map((subject) => [refId(subject), subject])), [subjects]);
  const authors = useMemo(
    () => users.filter((user) => ['Teacher', 'Admin'].includes(user.role))
      .sort((left, right) => String(left.display_name || left.email).localeCompare(String(right.display_name || right.email), 'vi')),
    [users],
  );

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 350);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    listSubjects().then(setSubjects).catch(() => setSubjects([]));
    fetchAllUsers().then(setUsers).catch(() => setUsers([]));
  }, []);

  const requestFor = useCallback((pageNumber, pageSize) => ({
    page: pageNumber,
    pageSize,
    search: search || undefined,
    reviewStatus: filters.status === 'all' ? undefined : filters.status,
    creatorUserId: filters.creatorUserId || undefined,
    subjectId: filters.subjectId || undefined,
    questionType: filters.questionType || undefined,
    qualityColor: filters.qualityColor || undefined,
    publicationStatus: filters.publicationStatus || undefined,
    bloomLevel: filters.bloomLevel || undefined,
    difficulty: filters.difficulty || undefined,
    createdFrom: filters.createdFrom || undefined,
    createdTo: filters.createdTo || undefined,
    sortBy: filters.sortBy,
  }), [filters, search]);

  const fetchQuestions = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await listQuestions({ ...requestFor(page, PAGE_SIZE), includeStatusCounts: true });
      setQuestions(result.items || []);
      setTotal(result.total || 0);
      setStatusCounts(result.status_counts || {});
      return result.items || [];
    } catch (err) {
      setError(err.message || 'Không tải được danh sách câu hỏi');
      return [];
    } finally {
      setLoading(false);
    }
  }, [requestFor, page]);

  useEffect(() => {
    fetchQuestions();
  }, [fetchQuestions]);

  useEffect(() => {
    if (!notice || notice.type === 'error') return undefined;
    const timer = setTimeout(() => setNotice(null), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  const openDetail = useCallback(async (question) => {
    setSelected(question);
    setHistory({ loading: true, versions: [], reviews: [] });
    try {
      const [versions, reviews] = await Promise.all([
        listQuestionVersions(question.id),
        listQuestionReviews(question.id),
      ]);
      setHistory({ loading: false, versions: versions || [], reviews: reviews.items || [] });
    } catch {
      setHistory({ loading: false, versions: [], reviews: [] });
    }
  }, []);

  const closeDetail = useCallback(() => {
    setSelected(null);
    if (searchParams.get('questionId')) {
      const next = new URLSearchParams(searchParams);
      next.delete('questionId');
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  // Liên kết từ trang khác (?questionId=...) mở thẳng ngăn chi tiết.
  const linkedQuestionId = searchParams.get('questionId');
  useEffect(() => {
    if (!linkedQuestionId || selected?.id === linkedQuestionId) return;
    getQuestion(linkedQuestionId)
      .then(openDetail)
      .catch((err) => setNotice({ type: 'error', text: err.message || 'Không mở được câu hỏi' }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linkedQuestionId]);

  useEffect(() => {
    if (!selected || editor || archiveConfirmation || sharing) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') closeDetail();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [selected, editor, archiveConfirmation, sharing, closeDetail]);

  const updateFilter = (field, value) => {
    setFilters((current) => ({ ...current, [field]: value }));
    setPage(1);
  };
  const resetFilters = () => {
    setFilters(EMPTY_FILTERS);
    setSearchInput('');
    setPage(1);
  };
  const activeFilterCount = Object.entries(filters)
    .filter(([key, value]) => key !== 'sortBy' && value !== EMPTY_FILTERS[key]).length + (search ? 1 : 0);
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const allCount = statusTotal(statusCounts);

  const handleSaveEditor = async (payload) => {
    setSaving(true);
    setEditorError('');
    try {
      const saved = editor.question
        ? await updateQuestion(editor.question.id, payload)
        : await createQuestion(payload);
      setNotice({ type: 'success', text: editor.question ? `Đã lưu ${saved.question_code}.` : `Đã tạo ${saved.question_code} ở trạng thái Nháp.` });
      setEditor(null);
      await fetchQuestions();
      await openDetail(saved);
    } catch (err) {
      setEditorError(err.message || 'Lưu câu hỏi thất bại');
    } finally {
      setSaving(false);
    }
  };

  const handleArchive = async (question) => {
    setSaving(true);
    try {
      await deleteQuestion(question.id);
      setNotice({ type: 'success', text: `Đã lưu trữ ${question.question_code}.` });
      setArchiveConfirmation(null);
      closeDetail();
      await fetchQuestions();
    } catch (err) {
      setNotice({ type: 'error', text: err.message || 'Lưu trữ câu hỏi thất bại' });
    } finally {
      setSaving(false);
    }
  };

  const saveSharing = async (event) => {
    event.preventDefault();
    setSaving(true);
    setSharingError('');
    try {
      const updated = await updateQuestionSharing(sharing.id, {
        shared_scope: sharing.scope,
        shared_with_user_ids: sharing.userIds,
      });
      setSelected(updated);
      setSharing(null);
      setNotice({ type: 'success', text: 'Đã lưu chia sẻ câu hỏi.' });
      await fetchQuestions();
    } catch (err) {
      setSharingError(err.message || 'Không lưu được chia sẻ');
    } finally {
      setSaving(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const first = await listQuestions(requestFor(1, 100));
      const rows = [...(first.items || [])];
      for (let nextPage = 2; rows.length < (first.total || 0); nextPage += 1) {
        const next = await listQuestions(requestFor(nextPage, 100));
        if (!next.items?.length) break;
        rows.push(...next.items);
      }
      const prefix = 'ngan-hang-cau-hoi';
      if (exportFormat === 'csv') downloadCsv(timestampedCsvFilename(prefix), rowsToCsv(QUESTION_BANK_EXPORT_COLUMNS, rows));
      else if (exportFormat === 'xlsx') downloadXlsx(timestampedXlsxFilename(prefix), QUESTION_BANK_EXPORT_COLUMNS, rows, 'Ngân hàng câu hỏi');
      else if (exportFormat === 'gift') downloadTextFile(timestampedQuestionBankFilename(prefix, 'gift'), questionsToGift(rows), 'text/plain;charset=utf-8');
      else downloadTextFile(timestampedQuestionBankFilename(prefix, 'xml'), questionsToMoodleXml(rows), 'application/xml;charset=utf-8');
      setNotice({ type: 'success', text: `Đã xuất ${rows.length} câu hỏi theo bộ lọc hiện tại.` });
    } catch (err) {
      setNotice({ type: 'error', text: err.message || 'Xuất câu hỏi thất bại' });
    } finally {
      setExporting(false);
    }
  };

  const detail = selected ? questions.find((item) => item.id === selected.id) || selected : null;
  const detailType = questionTypeOf(detail);
  const detailOptions = detail
    ? optionEntriesForQuestion({ questionType: detailType, rawOptions: detail.question_data?.options })
    : [];
  const detailAnswers = correctAnswerValues(detail?.question_data?.correct_answer);
  const detailSource = detail?.sources?.find((source) => source.is_primary) || detail?.sources?.[0];
  const currentVersion = history.versions.find((version) => version.version === detail?.current_version);

  return (
    <main className="admin-jobs-page question-bank-page">
      <section className="jobs-header">
        <div>
          <span>Ngân hàng</span>
          <h1>Ngân hàng câu hỏi</h1>
          <p>Toàn bộ câu hỏi của các giảng viên: tra cứu, chỉnh sửa, lưu trữ và xuất file.</p>
        </div>
        <div className="jobs-header-actions">
          <button type="button" className="jobs-secondary-button" onClick={fetchQuestions} disabled={loading}>
            <FontAwesomeIcon icon={faRotateRight} />
            <span>{loading ? 'Đang tải' : 'Làm mới'}</span>
          </button>
          <select className="qbank-export-select" aria-label="Định dạng xuất" value={exportFormat} onChange={(event) => setExportFormat(event.target.value)}>
            {EXPORT_FORMATS.map((format) => <option key={format.value} value={format.value}>{format.label}</option>)}
          </select>
          <button type="button" className="jobs-secondary-button" onClick={handleExport} disabled={exporting || total === 0}>
            <FontAwesomeIcon icon={faDownload} />
            <span>{exporting ? 'Đang xuất' : `Xuất ${total} câu`}</span>
          </button>
          <button type="button" className="jobs-primary-button" onClick={() => { setEditorError(''); setEditor({ question: null }); }}>
            <FontAwesomeIcon icon={faPlus} />
            <span>Thêm câu hỏi</span>
          </button>
        </div>
      </section>

      <section className="jobs-summary qbank-summary" aria-label="Số câu hỏi theo trạng thái duyệt">
        <button type="button" className={`summary-tile ${filters.status === 'all' ? 'summary-tile--active' : ''}`} onClick={() => updateFilter('status', 'all')}>
          <b>{allCount}</b>
          <span>Tất cả</span>
        </button>
        {REVIEW_STATUS_ORDER.map((status) => (
          <button
            type="button"
            key={status}
            className={`summary-tile ${filters.status === status ? 'summary-tile--active' : ''}`}
            onClick={() => updateFilter('status', status)}
          >
            <b>{statusCounts[status] || 0}</b>
            <span>{REVIEW_STATUS[status].label}</span>
          </button>
        ))}
      </section>

      <section className="jobs-toolbar qbank-toolbar" aria-label="Bộ lọc câu hỏi">
        <div className="toolbar-field">
          <label htmlFor="qbank-search">Tìm kiếm</label>
          <input id="qbank-search" type="search" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Mã hoặc nội dung câu hỏi" />
        </div>
        <div className="toolbar-field">
          <label htmlFor="qbank-author">Người soạn</label>
          <select id="qbank-author" value={filters.creatorUserId} onChange={(event) => updateFilter('creatorUserId', event.target.value)}>
            <option value="">Tất cả</option>
            {authors.map((user) => <option key={user.id} value={user.id}>{user.display_name || user.email}</option>)}
          </select>
        </div>
        <div className="toolbar-field">
          <label htmlFor="qbank-subject">Học phần</label>
          <select id="qbank-subject" value={filters.subjectId} onChange={(event) => updateFilter('subjectId', event.target.value)}>
            <option value="">Tất cả</option>
            {subjects.map((subject) => <option key={refId(subject)} value={refId(subject)}>{subject.subject_code} — {subject.subject_name}</option>)}
          </select>
        </div>
        <div className="toolbar-field">
          <label htmlFor="qbank-quality">Kết quả AI</label>
          <select id="qbank-quality" value={filters.qualityColor} onChange={(event) => updateFilter('qualityColor', event.target.value)}>
            <option value="">Tất cả</option>
            {QUALITY_COLORS.map((color) => <option key={color.value} value={color.value}>{color.label}</option>)}
          </select>
        </div>
        <div className="toolbar-field">
          <label htmlFor="qbank-sort">Sắp xếp</label>
          <select id="qbank-sort" value={filters.sortBy} onChange={(event) => updateFilter('sortBy', event.target.value)}>
            {SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </div>
        <div className="qbank-toolbar-actions">
          <button type="button" className="jobs-secondary-button" aria-expanded={moreFilters} onClick={() => setMoreFilters((value) => !value)}>
            {moreFilters ? 'Ẩn bớt' : 'Thêm bộ lọc'}
          </button>
          {activeFilterCount > 0 && (
            <button type="button" className="qbank-link-button" onClick={resetFilters}>Xóa {activeFilterCount} bộ lọc</button>
          )}
        </div>
        {moreFilters && (
          <div className="qbank-more-filters">
            <div className="toolbar-field">
              <label htmlFor="qbank-type">Loại câu hỏi</label>
              <select id="qbank-type" value={filters.questionType} onChange={(event) => updateFilter('questionType', event.target.value)}>
                <option value="">Tất cả</option>
                {QUESTION_TYPES.map((type) => <option key={type.backend} value={type.backend}>{type.label}</option>)}
              </select>
            </div>
            <div className="toolbar-field">
              <label htmlFor="qbank-bloom">Mức Bloom</label>
              <select id="qbank-bloom" value={filters.bloomLevel} onChange={(event) => updateFilter('bloomLevel', event.target.value)}>
                <option value="">Tất cả</option>
                {BLOOM_LEVELS.map((bloom) => <option key={bloom.level} value={String(bloom.level)}>{bloom.label}</option>)}
              </select>
            </div>
            <div className="toolbar-field">
              <label htmlFor="qbank-difficulty">Độ khó</label>
              <select id="qbank-difficulty" value={filters.difficulty} onChange={(event) => updateFilter('difficulty', event.target.value)}>
                <option value="">Tất cả</option>
                {DIFFICULTIES.map((difficulty) => <option key={difficulty.backend} value={difficulty.backend}>{difficulty.label}</option>)}
              </select>
            </div>
            <div className="toolbar-field">
              <label htmlFor="qbank-moodle">Moodle</label>
              <select id="qbank-moodle" value={filters.publicationStatus} onChange={(event) => updateFilter('publicationStatus', event.target.value)}>
                <option value="">Tất cả</option>
                {Object.entries(PUBLICATION_STATUS).map(([value, item]) => <option key={value} value={value}>{item.label}</option>)}
              </select>
            </div>
            <div className="toolbar-field">
              <label htmlFor="qbank-from">Tạo từ ngày</label>
              <input id="qbank-from" type="date" value={filters.createdFrom} max={filters.createdTo || undefined} onChange={(event) => updateFilter('createdFrom', event.target.value)} />
            </div>
            <div className="toolbar-field">
              <label htmlFor="qbank-to">Đến ngày</label>
              <input id="qbank-to" type="date" value={filters.createdTo} min={filters.createdFrom || undefined} onChange={(event) => updateFilter('createdTo', event.target.value)} />
            </div>
          </div>
        )}
      </section>

      {error && <p className="jobs-error" role="alert">{error}</p>}

      <section className="jobs-layout jobs-layout--single">
        <div className="jobs-table-panel">
          <div className="jobs-table-header">
            <div>
              <h2>Danh sách câu hỏi</h2>
              <span>{total} câu{activeFilterCount > 0 ? ' phù hợp với bộ lọc' : ''}</span>
            </div>
          </div>
          <div className="jobs-table-wrap">
            <table className="jobs-table qbank-table">
              <thead>
                <tr>
                  <th>Câu hỏi</th>
                  <th>Học phần</th>
                  <th>Người soạn</th>
                  <th>Kết quả AI</th>
                  <th>Duyệt</th>
                  <th>Moodle</th>
                  <th>Cập nhật</th>
                </tr>
              </thead>
              <tbody>
                {questions.map((question) => {
                  const author = authorOf(question, userById);
                  const ai = aiSummaryOf(question);
                  const review = reviewStatusOf(question);
                  const publication = publicationStatusOf(question);
                  return (
                    <tr
                      key={question.id}
                      className={detail?.id === question.id ? 'is-selected' : ''}
                      tabIndex={0}
                      onClick={() => openDetail(question)}
                      onKeyDown={(event) => { if (event.key === 'Enter') openDetail(question); }}
                    >
                      <td className="qbank-cell-question">
                        <strong>{question.content}</strong>
                        <small>
                          {question.question_code} · {questionTypeLabel(questionTypeOf(question))}
                          {question.classification?.bloom?.name ? ` · ${question.classification.bloom.name}` : ''}
                          {difficultyLabel(question.classification?.difficulty) ? ` · ${difficultyLabel(question.classification.difficulty)}` : ''}
                        </small>
                      </td>
                      <td title={subjectOf(question, subjectById).name}>{subjectOf(question, subjectById).code || subjectOf(question, subjectById).name || 'Chưa gắn'}</td>
                      <td>
                        <span>{author.name}</span>
                        {author.email && author.email !== author.name && <small>{author.email}</small>}
                      </td>
                      <td><span className={`status-pill status-pill--${ai.tone}`}>{ai.text}</span></td>
                      <td><span className={`status-pill status-pill--${review.tone}`}>{review.label}</span></td>
                      <td><span className={`status-pill status-pill--${publication.tone}`}>{publication.label}</span></td>
                      <td>{formatDate(question.updated_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {loading && <p className="jobs-empty">Đang tải danh sách câu hỏi...</p>}
            {!loading && questions.length === 0 && (
              <p className="jobs-empty">{activeFilterCount > 0 ? 'Không có câu hỏi phù hợp với bộ lọc.' : 'Ngân hàng chưa có câu hỏi nào.'}</p>
            )}
          </div>
          <div className="jobs-pagination">
            <button type="button" aria-label="Trang trước" disabled={page <= 1 || loading} onClick={() => setPage((current) => Math.max(1, current - 1))}>
              <FontAwesomeIcon icon={faChevronLeft} />
            </button>
            <span>Trang {page} / {pageCount}</span>
            <button type="button" aria-label="Trang sau" disabled={page >= pageCount || loading} onClick={() => setPage((current) => Math.min(pageCount, current + 1))}>
              <FontAwesomeIcon icon={faChevronRight} />
            </button>
          </div>
        </div>
      </section>

      {detail && (
        <div className="qbank-drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) closeDetail(); }}>
          <aside className="qbank-drawer" role="dialog" aria-modal="true" aria-label={`Chi tiết ${detail.question_code}`}>
            <div className="qbank-drawer-head">
              <div>
                <span>{detail.question_code} · phiên bản {detail.current_version}</span>
                <h2>{questionTypeLabel(detailType)}</h2>
              </div>
              <button type="button" className="qbank-icon-button" onClick={closeDetail} aria-label="Đóng">×</button>
            </div>

            <div className="qbank-drawer-pills">
              <span className={`status-pill status-pill--${reviewStatusOf(detail).tone}`}>{reviewStatusOf(detail).label}</span>
              <span className={`status-pill status-pill--${aiSummaryOf(detail).tone}`}>AI: {aiSummaryOf(detail).text}</span>
              <span className={`status-pill status-pill--${publicationStatusOf(detail).tone}`}>Moodle: {publicationStatusOf(detail).label}</span>
            </div>

            <div className="qbank-drawer-actions">
              <button type="button" className="jobs-primary-button" onClick={() => { setEditorError(''); setEditor({ question: detail }); }} disabled={saving}>Sửa</button>
              <Link className="jobs-secondary-button" to={`/kiem-duyet?questionId=${detail.id}`}>Mở kiểm duyệt</Link>
              <Link className="jobs-secondary-button" to={`/duyet-ai?questionId=${detail.id}`}>Xem thẩm định AI</Link>
              <button type="button" className="jobs-secondary-button" disabled={saving} onClick={() => { setSharingError(''); setSharing({ id: detail.id, scope: detail.shared_scope || 'PRIVATE', userIds: detail.shared_with_user_ids || [] }); }}>Chia sẻ</button>
              <button type="button" className="jobs-secondary-button qbank-danger" onClick={() => { setNotice(null); setArchiveConfirmation(detail); }} disabled={saving}>Lưu trữ</button>
            </div>

            <section className="qbank-section">
              <h3>Nội dung</h3>
              <QuestionContent text={detail.content} />
              {detailOptions.length > 0 && (
                <ul className="qbank-options">
                  {detailOptions.map((option) => {
                    const correct = detailAnswers.includes(option.key);
                    return (
                      <li key={option.key} className={correct ? 'is-correct' : ''}>
                        <b>{option.key}</b>
                        <span>{option.value}</span>
                        {correct && <em>Đáp án đúng</em>}
                      </li>
                    );
                  })}
                </ul>
              )}
              {(detailOptions.length === 0 || !detailOptions.some((option) => detailAnswers.includes(option.key))) && (
                <p className="qbank-answer"><b>Đáp án đúng:</b> {detail.question_data?.correct_answer || '--'}</p>
              )}
              {detail.question_data?.explanation && (
                <p className="qbank-explanation"><b>Giải thích:</b> {detail.question_data.explanation}</p>
              )}
            </section>

            <section className="qbank-section">
              <h3>Thông tin</h3>
              <dl className="qbank-facts">
                <div><dt>Người soạn</dt><dd>{authorOf(detail, userById).name}{authorOf(detail, userById).email ? ` · ${authorOf(detail, userById).email}` : ''}</dd></div>
                <div><dt>Học phần</dt><dd>{subjectOf(detail, subjectById).name || 'Chưa gắn'}</dd></div>
                <div><dt>Chương</dt><dd>{detail.classification?.chapter?.name || detail.classification?.chapter?.code || 'Chưa gắn'}</dd></div>
                <div><dt>Bloom</dt><dd>{detail.classification?.bloom?.name || '--'}</dd></div>
                <div><dt>Độ khó</dt><dd>{difficultyLabel(detail.classification?.difficulty) || 'Chưa ước lượng'}</dd></div>
                <div><dt>CLO</dt><dd>{(detail.clos || []).map((clo) => clo.code || clo.clo_code).filter(Boolean).join(', ') || 'Chưa gắn'}</dd></div>
                <div><dt>Nguồn gốc</dt><dd>{history.loading ? 'Đang tải...' : originLabel(currentVersion?.origin)}</dd></div>
                <div><dt>Tạo lúc</dt><dd>{formatDateTime(detail.created_at)}</dd></div>
                <div><dt>Cập nhật</dt><dd>{formatDateTime(detail.updated_at)}</dd></div>
                <div><dt>Gửi duyệt</dt><dd>{detail.submitted_at ? `${formatDateTime(detail.submitted_at)}${detail.review_submission?.submitted_by?.display_name ? ` · ${detail.review_submission.submitted_by.display_name}` : ''}` : 'Chưa gửi'}</dd></div>
              </dl>
            </section>

            <section className="qbank-section">
              <h3>Đoạn tài liệu nguồn</h3>
              {detailSource?.context_excerpt
                ? <p className="qbank-source">{detailSource.context_excerpt}</p>
                : <p className="qbank-muted">Câu hỏi này không gắn với đoạn tài liệu nào.</p>}
            </section>

            <section className="qbank-section">
              <h3>Nhận xét của AI</h3>
              {detail.quality_summary?.feedback?.summary
                ? <p>{detail.quality_summary.feedback.summary}</p>
                : (
                  <p className="qbank-muted">
                    {!detail.quality_summary?.error?.message && 'Chưa có nhận xét.'}
                    {detail.quality_summary?.error?.message?.startsWith('Cancelled by admin') && 'Lượt chấm gần nhất đã bị quản trị viên dừng.'}
                    {detail.quality_summary?.error?.message && !detail.quality_summary.error.message.startsWith('Cancelled by admin')
                      && `Lượt chấm gần nhất không có kết quả: ${detail.quality_summary.error.message}`}
                  </p>
                )}
              {detail.quality_summary?.evaluator_model_code && (
                <p className="qbank-muted">Mô hình: {detail.quality_summary.evaluator_model_code}{detail.quality_summary.evaluated_at ? ` · ${formatDateTime(detail.quality_summary.evaluated_at)}` : ''}</p>
              )}
            </section>

            <section className="qbank-section">
              <h3>Lịch sử kiểm duyệt</h3>
              {history.loading && <p className="qbank-muted">Đang tải...</p>}
              {!history.loading && history.reviews.length === 0 && <p className="qbank-muted">Chưa có lượt kiểm duyệt.</p>}
              {history.reviews.map((review) => (
                <div className="qbank-history-item" key={review.id || review._id}>
                  <b>{REVIEW_STATUS[review.decision]?.label || review.decision}</b>
                  <span>
                    {userById.get(refId(review.reviewer_user_id))?.display_name || 'Người duyệt'}
                    {' · '}{formatDateTime(review.reviewed_at || review.created_at)}
                  </span>
                  {review.note && <p>{review.note}</p>}
                </div>
              ))}
            </section>

            <section className="qbank-section">
              <h3>Các phiên bản</h3>
              {history.loading && <p className="qbank-muted">Đang tải...</p>}
              {history.versions.map((version) => (
                <div className="qbank-history-item" key={version.id}>
                  <b>Phiên bản {version.version}{version.version === detail.current_version ? ' · hiện tại' : ''}</b>
                  <span>
                    {userById.get(refId(version.created_by_user_id))?.display_name || originLabel(version.origin)}
                    {' · '}{formatDateTime(version.created_at)}
                  </span>
                  {version.change_note && <p>{CHANGE_NOTE_LABEL[version.change_note] || version.change_note}</p>}
                </div>
              ))}
            </section>
          </aside>
        </div>
      )}

      {sharing && (
        <div className="modal-overlay">
          <form className="qbank-dialog qbank-dialog--narrow" role="dialog" aria-modal="true" aria-label="Chia sẻ câu hỏi" onSubmit={saveSharing}>
            <h2>Chia sẻ câu hỏi</h2>
            <label className="qbank-field"><span>Phạm vi</span><select value={sharing.scope} onChange={(event) => setSharing({ ...sharing, scope: event.target.value })}><option value="PRIVATE">Riêng tư</option><option value="SUBJECT">Chia sẻ theo môn</option></select></label>
            <div className="qbank-field"><span>Chia sẻ riêng cho giảng viên</span>{users.filter((user) => user.role === 'Teacher' && (user.is_active !== false || sharing.userIds.includes(user.id))).map((user) => <label className="qbank-check" key={user.id}><input type="checkbox" checked={sharing.userIds.includes(user.id)} onChange={() => setSharing({ ...sharing, userIds: sharing.userIds.includes(user.id) ? sharing.userIds.filter((id) => id !== user.id) : [...sharing.userIds, user.id] })} />{user.display_name || user.email}</label>)}</div>
            {sharingError && <p className="qbank-note qbank-note--error" role="alert">{sharingError}</p>}
            <div className="qbank-dialog-actions"><button type="button" className="jobs-secondary-button" disabled={saving} onClick={() => setSharing(null)}>Hủy</button><button type="submit" className="jobs-primary-button" disabled={saving}>{saving ? 'Đang lưu...' : 'Lưu chia sẻ'}</button></div>
          </form>
        </div>
      )}

      {archiveConfirmation && (
        <div className="modal-overlay">
          <div className="qbank-dialog qbank-dialog--narrow" role="dialog" aria-modal="true" aria-label="Xác nhận lưu trữ câu hỏi">
            <h2>Lưu trữ {archiveConfirmation.question_code}?</h2>
            <p>Câu hỏi sẽ bị ẩn khỏi ngân hàng và không dùng được cho đề thi mới.</p>
            {notice?.type === 'error' && <p className="qbank-note qbank-note--error" role="alert">{notice.text}</p>}
            <div className="qbank-dialog-actions"><button type="button" className="jobs-secondary-button" disabled={saving} onClick={() => setArchiveConfirmation(null)}>Hủy</button><button type="button" className="jobs-primary-button" disabled={saving} onClick={() => handleArchive(archiveConfirmation)}>Xác nhận lưu trữ</button></div>
          </div>
        </div>
      )}

      {editor && (
        <QuestionEditorDialog
          question={editor.question}
          subjects={subjects}
          saving={saving}
          error={editorError}
          onSubmit={handleSaveEditor}
          onClose={() => { if (!saving) setEditor(null); }}
        />
      )}

      {notice && (
        <div className={`qbank-toast qbank-toast--${notice.type}`} role={notice.type === 'error' ? 'alert' : 'status'}>
          <span>{notice.text}</span>
          <button type="button" onClick={() => setNotice(null)} aria-label="Đóng thông báo">×</button>
        </div>
      )}
    </main>
  );
}

export default AdminQuestionBankPage;
