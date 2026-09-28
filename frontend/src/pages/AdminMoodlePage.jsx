import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faBan, faMagnifyingGlass, faPen, faPlug, faPlus, faRotateRight, faUpload } from '@fortawesome/free-solid-svg-icons';
import {
  checkMoodleTarget,
  deactivateMoodleTarget,
  listMoodlePublications,
  listMoodleTargets,
  retryMoodlePublication,
  saveMoodleTarget,
} from '../api/adminMoodle';
import WorkspaceHero from '../components/workspace/WorkspaceHero';
import Drawer from '../components/workspace/Drawer';
import MoreMenu from '../components/workspace/MoreMenu';
import { EmptyState, ErrorState, Notice, SkeletonRows } from '../components/workspace/Feedback';
import { useConfirm, useFlash } from '../components/workspace/Dialog';
import { Pagination, Segmented, Tabs } from '../components/workspace/Navigation';
import { formatDateTime } from '../features/review/reviewModel';
import '../css/workspace.css';
import '../css/AdminPages.css';

const PAGE_SIZE = 25;

const EMPTY_TARGET = {
  site_key: '',
  site_name: '',
  mode: 'MOCK',
  base_url: '',
  token_env_var: '',
  default_course_id: '',
  default_category_id: '',
  allowed_roles: ['Admin', 'Reviewer'],
  is_active: true,
};

const PUBLISH_ROLES = [
  { value: 'Admin', label: 'Quản trị viên' },
  { value: 'Reviewer', label: 'Người duyệt' },
];

const STATUS_LABEL = {
  PUBLISHED: 'Thành công',
  FAILED: 'Đồng bộ lỗi',
  QUEUED: 'Đang chờ',
  PROCESSING: 'Đang xử lý',
};

const STATUS_TONE = {
  PUBLISHED: 'success',
  FAILED: 'danger',
  QUEUED: 'info',
  PROCESSING: 'info',
};

function targetForm(target = {}) {
  return {
    ...EMPTY_TARGET,
    ...target,
    base_url: target.base_url || '',
    token_env_var: target.token_env_var || '',
    default_course_id: target.default_course_id ?? '',
    default_category_id: target.default_category_id ?? '',
    allowed_roles: target.allowed_roles?.length ? target.allowed_roles : EMPTY_TARGET.allowed_roles,
  };
}

function syncError(item) {
  if (item?.error_message) return item.error_message;
  if (typeof item?.error === 'string') return item.error;
  return item?.error?.message || '';
}

function AdminMoodlePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') === 'targets' ? 'targets' : 'syncs';
  const statusParam = searchParams.get('status');
  const status = STATUS_LABEL[statusParam] || statusParam === 'all' ? (statusParam || 'all') : 'all';
  const { flash, show: showFlash, clear: clearFlash } = useFlash();
  const [confirm, confirmDialog] = useConfirm();

  const [targets, setTargets] = useState([]);
  const [targetsLoading, setTargetsLoading] = useState(true);
  const [targetsError, setTargetsError] = useState('');
  const [syncs, setSyncs] = useState([]);
  const [summary, setSummary] = useState({});
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [siteFilter, setSiteFilter] = useState('all');
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [syncsLoading, setSyncsLoading] = useState(true);
  const [syncsError, setSyncsError] = useState('');
  const [busy, setBusy] = useState('');
  const [detail, setDetail] = useState(null);
  const [editor, setEditor] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setSearchTerm(searchInput.trim());
      setPage(1);
    }, 350);
    return () => window.clearTimeout(handle);
  }, [searchInput]);

  const loadTargets = useCallback(async () => {
    setTargetsLoading(true);
    setTargetsError('');
    try {
      const result = await listMoodleTargets();
      setTargets(result.items || []);
    } catch (err) {
      setTargetsError(err.message || 'Không tải được điểm đồng bộ.');
    } finally {
      setTargetsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTargets();
  }, [loadTargets, refreshKey]);

  useEffect(() => {
    let active = true;
    setSyncsLoading(true);
    setSyncsError('');
    listMoodlePublications({ page, pageSize: PAGE_SIZE, status, siteKey: siteFilter, search: searchTerm })
      .then((result) => {
        if (!active) return;
        setSyncs(result.items || []);
        setSummary(result.summary || {});
        setTotal(result.total || 0);
      })
      .catch((err) => {
        if (!active) return;
        setSyncs([]);
        setTotal(0);
        setSyncsError(err.message || 'Không tải được lịch sử đồng bộ.');
      })
      .finally(() => active && setSyncsLoading(false));
    return () => {
      active = false;
    };
  }, [page, status, siteFilter, searchTerm, refreshKey]);

  const refresh = () => setRefreshKey((key) => key + 1);

  const setParam = (patch) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(patch).forEach(([key, value]) => {
      if (!value || value === 'all' || value === 'syncs') next.delete(key);
      else next.set(key, value);
    });
    setSearchParams(next, { replace: true });
    setPage(1);
  };

  const retry = async (item) => {
    setBusy(`retry:${item.id}`);
    clearFlash();
    try {
      await retryMoodlePublication(item.id);
      showFlash('success', `Đã đồng bộ lại ${item.question_code || 'câu hỏi'}.`);
      setDetail(null);
      refresh();
    } catch (err) {
      showFlash('error', err.message || 'Đồng bộ lại thất bại.');
    } finally {
      setBusy('');
    }
  };

  const checkTarget = async (target) => {
    setBusy(`check:${target.site_key}`);
    clearFlash();
    try {
      const result = await checkMoodleTarget(target.site_key);
      const check = result?.check || {};
      showFlash(check.ok ? 'success' : 'warn', check.message || (check.ok ? 'Kết nối ổn định.' : 'Kết nối chưa sẵn sàng.'));
      await loadTargets();
    } catch (err) {
      showFlash('error', err.message || 'Không kiểm tra được kết nối.');
    } finally {
      setBusy('');
    }
  };

  const deactivate = async (target) => {
    const accepted = await confirm({
      title: 'Tắt điểm đồng bộ',
      description: `Không ai xuất bản được lên "${target.site_name}" cho tới khi bật lại.`,
      confirmLabel: 'Tắt',
      tone: 'danger',
    });
    if (!accepted) return;
    setBusy(`off:${target.site_key}`);
    clearFlash();
    try {
      await deactivateMoodleTarget(target.site_key);
      showFlash('success', `Đã tắt "${target.site_name}".`);
      await loadTargets();
    } catch (err) {
      showFlash('error', err.message || 'Không tắt được.');
    } finally {
      setBusy('');
    }
  };

  const updateEditor = (patch) => setEditor((current) => ({ ...current, error: '', form: { ...current.form, ...patch } }));

  const toggleRole = (role) => {
    const roles = new Set(editor.form.allowed_roles);
    if (roles.has(role)) {
      if (roles.size === 1) {
        setEditor((current) => ({ ...current, error: 'Phải có ít nhất một vai trò được xuất bản.' }));
        return;
      }
      roles.delete(role);
    } else {
      roles.add(role);
    }
    updateEditor({ allowed_roles: PUBLISH_ROLES.map((item) => item.value).filter((item) => roles.has(item)) });
  };

  const saveTarget = async () => {
    const { form, isNew } = editor;
    let error = '';
    if (!form.site_key.trim()) error = 'Nhập mã điểm đồng bộ.';
    else if (isNew && !/^[a-z0-9][a-z0-9_-]*$/i.test(form.site_key.trim())) error = 'Mã chỉ gồm chữ, số, gạch nối hoặc gạch dưới.';
    else if (!form.site_name.trim()) error = 'Nhập tên hiển thị.';
    else if (form.mode === 'REST_API' && !/^https?:\/\/\S+$/i.test(form.base_url.trim())) error = 'Chế độ REST API cần địa chỉ Moodle hợp lệ.';
    else if (form.mode === 'REST_API' && !form.token_env_var.trim()) error = 'Chế độ REST API cần tên biến môi trường chứa token.';
    else if (!form.allowed_roles.length) error = 'Phải có ít nhất một vai trò được xuất bản.';
    if (error) {
      setEditor((current) => ({ ...current, error }));
      return;
    }
    setBusy('save');
    try {
      await saveMoodleTarget({
        ...form,
        site_key: form.site_key.trim(),
        site_name: form.site_name.trim(),
        base_url: form.base_url.trim(),
        token_env_var: form.token_env_var.trim(),
        default_course_id: String(form.default_course_id).trim(),
        default_category_id: String(form.default_category_id).trim(),
      });
      setEditor(null);
      showFlash('success', 'Đã lưu điểm đồng bộ.');
      await loadTargets();
    } catch (err) {
      setEditor((current) => ({ ...current, error: err.message || 'Lưu thất bại.' }));
    } finally {
      setBusy('');
    }
  };

  const statusItems = [
    { value: 'all', label: 'Tất cả', count: summary.total },
    { value: 'PROCESSING', label: 'Đang xử lý', count: summary.pending },
    { value: 'PUBLISHED', label: 'Thành công', count: summary.published },
    { value: 'FAILED', label: 'Lỗi', count: summary.failed },
  ];

  return (
    <main className="ws-page moodle-workspace-page">
      <WorkspaceHero
        badge="Vận hành hệ thống"
        title="Moodle"
        description="Theo dõi các lần đồng bộ câu hỏi đã duyệt lên Moodle, xử lý đồng bộ lỗi và quản lý điểm đồng bộ."
        actions={(
          <button type="button" className="btn btn--outline" onClick={refresh} disabled={syncsLoading}>
            <FontAwesomeIcon icon={faRotateRight} />
            Làm mới
          </button>
        )}
      >
        <Tabs
          label="Khu vực Moodle"
          value={tab}
          onChange={(value) => setParam({ tab: value })}
          items={[
            { value: 'syncs', label: 'Đồng bộ', count: summary.total },
            { value: 'targets', label: 'Điểm đồng bộ', count: targets.length },
          ]}
        />
      </WorkspaceHero>

      <section className="ws-body">
        <div className="container ws-main">
          {flash && <Notice tone={flash.tone} onDismiss={clearFlash}>{flash.message}</Notice>}

          {tab === 'syncs' ? (
            <section className="ws-card">
              <div className="ws-card-head">
                <div className="ws-card-title">
                  <h2>Lần đồng bộ</h2>
                  <span className="ws-list-count tabular">{syncsLoading ? 'Đang tải...' : `${syncs.length} / ${total} lần đang hiển thị`}</span>
                </div>
                <Link className="ws-card-link" to="/kiem-duyet?tab=moodle">Câu chờ lên Moodle</Link>
              </div>
              <div className="ws-toolbar" style={{ marginBottom: 12 }}>
                <label className="ws-search">
                  <span className="ws-sr-only">Tìm lần đồng bộ</span>
                  <FontAwesomeIcon icon={faMagnifyingGlass} />
                  <input className="ws-input" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Mã câu hỏi hoặc mã tham chiếu Moodle" />
                </label>
                <select className="ws-select" aria-label="Điểm đồng bộ" value={siteFilter} onChange={(event) => { setSiteFilter(event.target.value); setPage(1); }}>
                  <option value="all">Mọi điểm đồng bộ</option>
                  {targets.map((target) => <option key={target.site_key} value={target.site_key}>{target.site_name}</option>)}
                </select>
              </div>
              <Segmented label="Lọc theo trạng thái" value={status} onChange={(value) => setParam({ status: value })} items={statusItems} />

              <div style={{ marginTop: 14 }}>
                {syncsLoading ? (
                  <SkeletonRows rows={5} lines={2} />
                ) : syncsError ? (
                  <ErrorState message={syncsError} onRetry={refresh} />
                ) : syncs.length === 0 ? (
                  <EmptyState
                    icon={faUpload}
                    title="Chưa có lần đồng bộ phù hợp"
                    description="Câu hỏi được xuất bản lên Moodle từ Bàn duyệt hoặc tab Chờ lên Moodle trong Hộp việc."
                  />
                ) : (
                  <div className="ws-table-wrap">
                    <table className="ws-table">
                      <thead><tr><th>Câu hỏi</th><th>Điểm đồng bộ</th><th>Trạng thái</th><th>Thời điểm</th><th aria-label="Thao tác" /></tr></thead>
                      <tbody>
                        {syncs.map((item) => (
                          <tr key={item.id} data-clickable="true" onClick={() => setDetail(item)}>
                            <td>
                              <span className="ws-code">{item.question_code || item.question_id}</span>
                              <small>Phiên bản {item.question_version}</small>
                            </td>
                            <td>
                              {item.target?.site_name || item.target?.moodle_site_id || '--'}
                              <small>{item.publication_mode === 'MOCK' || item.external_sync === false ? 'Mô phỏng' : 'REST API'}</small>
                            </td>
                            <td>
                              <span className={`ws-pill ws-pill--${STATUS_TONE[item.status] || 'outline'}`}>{STATUS_LABEL[item.status] || item.status}</span>
                              {syncError(item) && <small className="ws-clip-1" style={{ maxWidth: 240 }} title={syncError(item)}>{syncError(item)}</small>}
                            </td>
                            <td>{formatDateTime(item.created_at)}</td>
                            <td onClick={(event) => event.stopPropagation()}>
                              {item.status === 'FAILED' && (
                                <button type="button" className="btn btn--outline btn--sm" disabled={Boolean(busy)} onClick={() => retry(item)}>
                                  {busy === `retry:${item.id}` ? 'Đang gửi...' : 'Thử lại'}
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <Pagination page={page} pageSize={PAGE_SIZE} total={total} loading={syncsLoading} onChange={setPage} />
              </div>
            </section>
          ) : (
            <section className="ws-card">
              <div className="ws-card-head">
                <div className="ws-card-title">
                  <h2>Điểm đồng bộ Moodle</h2>
                  <span className="ws-list-count">Token thật không lưu trong hệ thống, chỉ khai báo tên biến môi trường</span>
                </div>
                <button type="button" className="btn btn--primary btn--sm" onClick={() => setEditor({ isNew: true, form: targetForm(), error: '' })}>
                  <FontAwesomeIcon icon={faPlus} />
                  Thêm điểm đồng bộ
                </button>
              </div>
              {targetsLoading ? (
                <SkeletonRows rows={3} lines={2} />
              ) : targetsError ? (
                <ErrorState message={targetsError} onRetry={loadTargets} />
              ) : targets.length === 0 ? (
                <EmptyState icon={faPlug} title="Chưa có điểm đồng bộ" description="Thêm điểm đồng bộ để người duyệt xuất bản câu hỏi đã duyệt lên Moodle." />
              ) : (
                <div className="ws-table-wrap">
                  <table className="ws-table">
                    <thead><tr><th>Điểm đồng bộ</th><th>Chế độ</th><th>Ai được xuất bản</th><th>Kết nối</th><th>Trạng thái</th><th aria-label="Thao tác" /></tr></thead>
                    <tbody>
                      {targets.map((target) => (
                        <tr key={target.site_key} style={{ opacity: target.is_active ? 1 : 0.65 }}>
                          <td><strong>{target.site_name}</strong><small className="ws-code">{target.site_key}</small></td>
                          <td>{target.mode === 'REST_API' ? 'REST API' : 'Mô phỏng'}<small>{target.default_course_id ? `Khoá ${target.default_course_id}` : ''}</small></td>
                          <td>{(target.allowed_roles?.length ? target.allowed_roles : EMPTY_TARGET.allowed_roles).map((role) => PUBLISH_ROLES.find((item) => item.value === role)?.label || role).join(', ')}</td>
                          <td>
                            <span className={`ws-pill ${target.last_check ? (target.last_check.ok ? 'ws-pill--success' : 'ws-pill--danger') : 'ws-pill--outline'}`}>
                              {target.last_check ? (target.last_check.ok ? 'Ổn định' : 'Lỗi') : 'Chưa kiểm tra'}
                            </span>
                            {target.last_check?.checked_at && <small>{formatDateTime(target.last_check.checked_at)}</small>}
                          </td>
                          <td><span className={`ws-pill ${target.is_active ? 'ws-pill--success' : 'ws-pill--outline'}`}>{target.is_active ? 'Đang bật' : 'Đã tắt'}</span></td>
                          <td>
                            <MoreMenu
                              variant="icon"
                              label={`Thao tác với ${target.site_name}`}
                              items={[
                                { key: 'check', label: busy === `check:${target.site_key}` ? 'Đang kiểm tra...' : 'Kiểm tra kết nối', icon: faPlug, disabled: Boolean(busy), onClick: () => checkTarget(target) },
                                { key: 'edit', label: 'Sửa', icon: faPen, onClick: () => setEditor({ isNew: false, form: targetForm(target), error: '' }) },
                                { key: 'off', label: 'Tắt', icon: faBan, danger: true, disabled: !target.is_active || Boolean(busy), title: target.is_active ? undefined : 'Điểm đồng bộ đã tắt', onClick: () => deactivate(target) },
                              ]}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
        </div>
      </section>

      <Drawer
        open={Boolean(detail)}
        title="Chi tiết lần đồng bộ"
        subtitle={detail?.question_code}
        onClose={() => setDetail(null)}
        footer={detail?.status === 'FAILED' ? (
          <button type="button" className="btn btn--primary" disabled={Boolean(busy)} onClick={() => retry(detail)}>
            {busy === `retry:${detail.id}` ? 'Đang gửi...' : 'Thử lại'}
          </button>
        ) : null}
      >
        {detail && (
          <>
            <span className={`ws-pill ws-pill--${STATUS_TONE[detail.status] || 'outline'}`} style={{ alignSelf: 'flex-start' }}>{STATUS_LABEL[detail.status] || detail.status}</span>
            <dl className="ws-kv">
              <div><dt>Câu hỏi</dt><dd><Link to={`/kiem-duyet/${detail.question_id}`} className="ws-code">{detail.question_code || detail.question_id}</Link></dd></div>
              <div><dt>Phiên bản</dt><dd>{detail.question_version}</dd></div>
              <div><dt>Điểm đồng bộ</dt><dd>{detail.target?.site_name || detail.target?.moodle_site_id || '--'}</dd></div>
              <div><dt>Chế độ</dt><dd>{detail.publication_mode === 'MOCK' || detail.external_sync === false ? 'Mô phỏng' : 'REST API'}</dd></div>
              <div><dt>Khoá học</dt><dd>{detail.target?.course_id || '--'}</dd></div>
              <div><dt>Danh mục</dt><dd>{detail.target?.category_id || '--'}</dd></div>
              <div><dt>Mã tham chiếu</dt><dd className="ws-code">{detail.moodle_question_ref_id || '--'}</dd></div>
              <div><dt>Thời điểm</dt><dd>{formatDateTime(detail.created_at)}</dd></div>
            </dl>
            {syncError(detail) && (
              <div>
                <h4 className="ws-subhead">Lỗi</h4>
                <div className="ad-error-box">{syncError(detail)}</div>
              </div>
            )}
          </>
        )}
      </Drawer>

      <Drawer
        open={Boolean(editor)}
        title={editor?.isNew ? 'Thêm điểm đồng bộ' : 'Sửa điểm đồng bộ'}
        subtitle={editor?.isNew ? undefined : editor?.form.site_key}
        onClose={() => setEditor(null)}
        busy={busy === 'save'}
        as="form"
        onSubmit={saveTarget}
        footer={(
          <>
            <button type="button" className="btn btn--outline" onClick={() => setEditor(null)} disabled={busy === 'save'}>Huỷ</button>
            <button type="submit" className="btn btn--primary" disabled={busy === 'save'}>{busy === 'save' ? 'Đang lưu...' : 'Lưu'}</button>
          </>
        )}
      >
        {editor && (
          <>
            <label className="ws-field">
              <span>Mã điểm đồng bộ</span>
              <input className="ws-input" value={editor.form.site_key} disabled={!editor.isNew} onChange={(event) => updateEditor({ site_key: event.target.value })} placeholder="ctu-elearning" />
              {!editor.isNew && <small>Mã dùng làm khoá, không đổi được sau khi tạo.</small>}
            </label>
            <label className="ws-field"><span>Tên hiển thị</span><input className="ws-input" value={editor.form.site_name} onChange={(event) => updateEditor({ site_name: event.target.value })} placeholder="E-learning CTU" /></label>
            <label className="ws-field">
              <span>Chế độ</span>
              <select className="ws-select" value={editor.form.mode} onChange={(event) => updateEditor({ mode: event.target.value })}>
                <option value="MOCK">Mô phỏng (lưu cục bộ)</option>
                <option value="REST_API">REST API Moodle</option>
              </select>
              <small>Hệ thống hiện chỉ ghi ở chế độ mô phỏng; REST API cần cấu hình phía máy chủ.</small>
            </label>
            <label className="ws-field"><span>Địa chỉ Moodle</span><input className="ws-input" value={editor.form.base_url} onChange={(event) => updateEditor({ base_url: event.target.value })} placeholder="https://elearning.ctu.edu.vn" /></label>
            <label className="ws-field"><span>Biến môi trường chứa token</span><input className="ws-input" value={editor.form.token_env_var} onChange={(event) => updateEditor({ token_env_var: event.target.value })} placeholder="MOODLE_API_TOKEN" /></label>
            <div className="ws-form-grid">
              <label className="ws-field"><span>Mã khoá học</span><input className="ws-input" value={editor.form.default_course_id} onChange={(event) => updateEditor({ default_course_id: event.target.value })} /></label>
              <label className="ws-field"><span>Mã danh mục</span><input className="ws-input" value={editor.form.default_category_id} onChange={(event) => updateEditor({ default_category_id: event.target.value })} /></label>
            </div>
            <div className="ws-field">
              <span className="ws-label">Ai được xuất bản</span>
              <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>
                {PUBLISH_ROLES.map((role) => (
                  <label className="ws-check" key={role.value}>
                    <input type="checkbox" checked={editor.form.allowed_roles.includes(role.value)} onChange={() => toggleRole(role.value)} />
                    {role.label}
                  </label>
                ))}
              </div>
            </div>
            <label className="ws-check"><input type="checkbox" checked={editor.form.is_active} onChange={(event) => updateEditor({ is_active: event.target.checked })} />Đang bật</label>
            {editor.error && <Notice tone="error">{editor.error}</Notice>}
          </>
        )}
      </Drawer>
      {confirmDialog}
    </main>
  );
}

export default AdminMoodlePage;
