import { useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faCopy,
  faEnvelope,
  faFileImport,
  faKey,
  faLock,
  faLockOpen,
  faMagnifyingGlass,
  faPen,
  faPlus,
  faUsers,
} from '@fortawesome/free-solid-svg-icons';
import { createUser, deleteUser, importUsers, inviteUser, listUsers, resetUserPassword, updateUser } from '../api/users';
import { ROLE_DEFAULT_PERMISSIONS } from '../auth/permissions';
import { AuthContext } from '../context/AuthContext';
import { normalizeAvatarUrl } from '../utils/avatarUrl';
import WorkspaceHero from '../components/workspace/WorkspaceHero';
import Drawer from '../components/workspace/Drawer';
import MoreMenu from '../components/workspace/MoreMenu';
import { EmptyState, ErrorState, Notice, SkeletonRows } from '../components/workspace/Feedback';
import { useConfirm, useFlash } from '../components/workspace/Dialog';
import { Pagination, Segmented } from '../components/workspace/Navigation';
import '../css/workspace.css';
import '../css/AdminPages.css';

const PAGE_SIZE = 20;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const ROLE_OPTIONS = [
  { value: 'Teacher', label: 'Giảng viên' },
  { value: 'Reviewer', label: 'Người duyệt' },
  { value: 'Admin', label: 'Quản trị viên' },
];

const ROLE_LABEL = Object.fromEntries(ROLE_OPTIONS.map((role) => [role.value, role.label]));

const ROLE_TONE = {
  Admin: 'danger',
  Teacher: 'info',
  Reviewer: 'success',
};

// Nhóm quyền theo khu vực nghiệp vụ để dễ đọc hơn danh sách phẳng.
const PERMISSION_GROUPS = [
  {
    label: 'Giảng viên',
    items: [
      { value: 'questions.generate', label: 'Sinh câu hỏi bằng AI' },
      { value: 'questions.manage_own', label: 'Quản lý câu hỏi của mình' },
      { value: 'questions.share_bank', label: 'Chia sẻ ngân hàng câu hỏi' },
      { value: 'questions.use_shared_bank', label: 'Dùng ngân hàng được chia sẻ' },
      { value: 'documents.manage_own', label: 'Quản lý tài liệu của mình' },
      { value: 'exams.manage_own', label: 'Làm đề thi' },
      { value: 'catalog.subjects.manage_own', label: 'Quản lý học phần của mình' },
    ],
  },
  {
    label: 'Kiểm duyệt',
    items: [
      { value: 'reviews.manage', label: 'Kiểm duyệt câu hỏi' },
      { value: 'questions.read_review_queue', label: 'Xem hàng kiểm duyệt' },
      { value: 'questions.comment', label: 'Trao đổi trên câu hỏi' },
      { value: 'questions.export_moodle', label: 'Xuất và ghi Moodle' },
    ],
  },
  {
    label: 'Quản trị',
    items: [
      { value: 'questions.manage_all', label: 'Quản lý mọi câu hỏi' },
      { value: 'documents.manage_all', label: 'Quản lý mọi tài liệu' },
      { value: 'admin.overview', label: 'Xem tổng quan' },
      { value: 'admin.users', label: 'Quản lý người dùng' },
      { value: 'admin.catalog', label: 'Quản lý danh mục' },
      { value: 'admin.jobs', label: 'Quản lý hàng đợi' },
      { value: 'admin.moodle', label: 'Quản lý Moodle' },
      { value: 'admin.audit', label: 'Xem nhật ký' },
    ],
  },
];

function permissionsForRole(role) {
  return [...(ROLE_DEFAULT_PERMISSIONS[role] || [])];
}

function togglePermission(list, permission) {
  const current = new Set(list || []);
  if (current.has(permission)) current.delete(permission);
  else current.add(permission);
  return Array.from(current);
}

function initials(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  return `${parts[0][0] || ''}${parts.length > 1 ? parts[parts.length - 1][0] : ''}`.toUpperCase();
}

function formatDate(value) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--';
  return new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(date);
}

function parseImportRows(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [email = '', displayName, role = 'Teacher', permissions = ''] = line.split(',').map((part) => part.trim());
      const normalizedRole = ROLE_LABEL[role] ? role : 'Teacher';
      return {
        email,
        display_name: displayName || email,
        role: normalizedRole,
        permissions: permissions
          ? permissions.split('|').map((item) => item.trim()).filter(Boolean)
          : permissionsForRole(normalizedRole),
      };
    });
}

function PermissionPicker({ value, onChange }) {
  return (
    <div className="ws-field">
      <span className="ws-label">Quyền chi tiết</span>
      <small>Chọn vai trò sẽ điền sẵn quyền mặc định; chỉnh thêm khi cần ngoại lệ.</small>
      {PERMISSION_GROUPS.map((group) => (
        <fieldset key={group.label} style={{ border: 0, padding: 0, margin: '6px 0 0' }}>
          <legend className="ws-hint" style={{ fontWeight: 700, marginBottom: 6 }}>{group.label}</legend>
          <div className="ad-permission-grid">
            {group.items.map((permission) => (
              <label className="ws-check" key={permission.value}>
                <input
                  type="checkbox"
                  checked={(value || []).includes(permission.value)}
                  onChange={() => onChange(togglePermission(value, permission.value))}
                />
                {permission.label}
              </label>
            ))}
          </div>
        </fieldset>
      ))}
    </div>
  );
}

function SecretLink({ label, value, copied, onCopy }) {
  return (
    <div className="ws-field">
      <span>{label}</span>
      <div className="ad-secret">
        <input className="ws-input" readOnly value={value} onFocus={(event) => event.target.select()} />
        <button type="button" className="btn btn--outline" onClick={onCopy}>
          <FontAwesomeIcon icon={faCopy} />
          {copied ? 'Đã chép' : 'Sao chép'}
        </button>
      </div>
      <small>Gửi link này cho người dùng qua kênh an toàn. Link chỉ dùng được một lần.</small>
    </div>
  );
}

function UsersAdminPage() {
  const { user: currentUser } = useContext(AuthContext);
  const { flash, show: showFlash, clear: clearFlash } = useFlash();
  const [confirm, confirmDialog] = useConfirm();
  const [users, setUsers] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [stats, setStats] = useState({ all: null, Admin: null, Teacher: null, Reviewer: null });
  const [roleFilter, setRoleFilter] = useState('all');
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  const [createState, setCreateState] = useState(null);
  const [importState, setImportState] = useState(null);
  const [editState, setEditState] = useState(null);
  const [resetResult, setResetResult] = useState(null);
  const [busyKey, setBusyKey] = useState('');
  const [copiedKey, setCopiedKey] = useState('');

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setPage(1);
      setSearchTerm(searchInput.trim());
    }, 350);
    return () => window.clearTimeout(handle);
  }, [searchInput]);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await listUsers({
        page,
        pageSize: PAGE_SIZE,
        role: roleFilter === 'all' ? undefined : roleFilter,
        search: searchTerm || undefined,
      });
      setUsers(result.items || []);
      setTotal(result.total || 0);
    } catch (err) {
      setError(err.message || 'Không tải được danh sách người dùng.');
      setUsers([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, roleFilter, searchTerm]);

  const fetchStats = useCallback(async () => {
    const results = await Promise.allSettled([
      listUsers({ page: 1, pageSize: 1 }),
      ...ROLE_OPTIONS.map((role) => listUsers({ page: 1, pageSize: 1, role: role.value })),
    ]);
    const value = (index) => (results[index].status === 'fulfilled' ? results[index].value.total || 0 : null);
    setStats({ all: value(0), Teacher: value(1), Reviewer: value(2), Admin: value(3) });
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const refreshAll = () => Promise.all([fetchUsers(), fetchStats()]);

  const selectRole = (role) => {
    setRoleFilter(role);
    setPage(1);
  };

  const copy = async (text, key) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      window.setTimeout(() => setCopiedKey(''), 1500);
    } catch {
      // Môi trường không cho phép clipboard: người dùng tự chọn và sao chép trong ô.
    }
  };

  const openCreate = (mode) => {
    setCreateState({
      mode,
      error: '',
      result: null,
      form: { email: '', password: '', display_name: '', role: 'Teacher', permissions: permissionsForRole('Teacher') },
    });
  };

  const updateCreate = (patch) => setCreateState((current) => ({ ...current, form: { ...current.form, ...patch }, error: '' }));

  const submitCreate = async () => {
    const { form, mode } = createState;
    const email = form.email.trim();
    const displayName = form.display_name.trim();
    let message = '';
    if (!email || !displayName) message = 'Nhập đầy đủ email và họ tên.';
    else if (!EMAIL_RE.test(email)) message = 'Email chưa đúng định dạng.';
    else if (mode === 'direct' && form.password.length < 6) message = 'Mật khẩu cần ít nhất 6 ký tự.';
    if (message) {
      setCreateState((current) => ({ ...current, error: message }));
      return;
    }
    setBusyKey('create');
    try {
      if (mode === 'invite') {
        const result = await inviteUser({ email, display_name: displayName, role: form.role, permissions: form.permissions });
        setCreateState((current) => ({ ...current, result }));
      } else {
        await createUser({ ...form, email, display_name: displayName });
        setCreateState(null);
        showFlash('success', `Đã tạo tài khoản ${email}.`);
      }
      setPage(1);
      await refreshAll();
    } catch (err) {
      setCreateState((current) => ({ ...current, error: err.message || 'Tạo tài khoản thất bại.' }));
    } finally {
      setBusyKey('');
    }
  };

  const importRows = useMemo(() => parseImportRows(importState?.text || ''), [importState?.text]);
  const importValid = importRows.filter((row) => EMAIL_RE.test(row.email)).length;

  const submitImport = async () => {
    if (importRows.length === 0) {
      setImportState((current) => ({ ...current, error: 'Nhập ít nhất một dòng.' }));
      return;
    }
    if (importValid !== importRows.length) {
      setImportState((current) => ({ ...current, error: `${importRows.length - importValid} dòng có email chưa hợp lệ. Sửa trước khi nhập.` }));
      return;
    }
    setBusyKey('import');
    try {
      const result = await importUsers({ users: importRows });
      setImportState((current) => ({ ...current, result, error: '' }));
      setPage(1);
      await refreshAll();
    } catch (err) {
      setImportState((current) => ({ ...current, error: err.message || 'Nhập danh sách thất bại.' }));
    } finally {
      setBusyKey('');
    }
  };

  const openEdit = (target) => {
    setEditState({
      user: target,
      error: '',
      form: {
        display_name: target.display_name || '',
        role: target.role,
        is_active: target.is_active,
        permissions: target.permissions?.length ? target.permissions : permissionsForRole(target.role),
      },
    });
  };

  const updateEdit = (patch) => setEditState((current) => ({ ...current, form: { ...current.form, ...patch }, error: '' }));

  const submitEdit = async () => {
    const { user: target, form } = editState;
    if (!form.display_name.trim()) {
      setEditState((current) => ({ ...current, error: 'Họ tên không được để trống.' }));
      return;
    }
    setBusyKey('edit');
    try {
      await updateUser(target.id, { ...form, display_name: form.display_name.trim() });
      setEditState(null);
      showFlash('success', `Đã cập nhật ${target.email}.`);
      await refreshAll();
    } catch (err) {
      setEditState((current) => ({ ...current, error: err.message || 'Cập nhật thất bại.' }));
    } finally {
      setBusyKey('');
    }
  };

  const handleResetPassword = async (target) => {
    setBusyKey(`reset:${target.id}`);
    clearFlash();
    try {
      setResetResult(await resetUserPassword(target.id));
    } catch (err) {
      showFlash('error', err.message || 'Không tạo được link đặt lại mật khẩu.');
    } finally {
      setBusyKey('');
    }
  };

  const handleToggleActive = async (target) => {
    const activate = !target.is_active;
    const accepted = await confirm({
      title: activate ? 'Mở khoá tài khoản' : 'Khoá tài khoản',
      description: activate
        ? `${target.display_name} (${target.email}) sẽ đăng nhập lại được.`
        : `${target.display_name} (${target.email}) sẽ không đăng nhập được. Dữ liệu của tài khoản vẫn được giữ.`,
      confirmLabel: activate ? 'Mở khoá' : 'Khoá tài khoản',
      tone: activate ? 'primary' : 'danger',
    });
    if (!accepted) return;
    setBusyKey(`toggle:${target.id}`);
    clearFlash();
    try {
      if (activate) await updateUser(target.id, { is_active: true });
      else await deleteUser(target.id);
      showFlash('success', activate ? 'Đã mở khoá tài khoản.' : 'Đã khoá tài khoản.');
      await refreshAll();
    } catch (err) {
      showFlash('error', err.message || 'Thao tác thất bại.');
    } finally {
      setBusyKey('');
    }
  };

  const isSelf = (target) => String(target.id) === String(currentUser?.id || '');

  return (
    <main className="ws-page users-admin-page">
      <WorkspaceHero
        badge="Quản trị viên"
        title="Người dùng"
        description="Cấp tài khoản cho giảng viên, người duyệt và quản trị viên; điều chỉnh quyền và khoá tài khoản khi cần."
        actions={(
          <>
            <MoreMenu
              items={[
                { key: 'import', label: 'Nhập danh sách từ CSV', icon: faFileImport, onClick: () => setImportState({ text: '', error: '', result: null }) },
              ]}
            />
            <button type="button" className="btn btn--primary" onClick={() => openCreate('direct')}>
              <FontAwesomeIcon icon={faPlus} />
              Thêm người dùng
            </button>
          </>
        )}
      />

      <section className="ws-body">
        <div className="container ws-main">
          {flash && <Notice tone={flash.tone} onDismiss={clearFlash}>{flash.message}</Notice>}

          <section className="ws-card">
            <div className="ws-card-head">
              <div className="ws-card-title">
                <h2>Tài khoản</h2>
                <span className="ws-list-count tabular">{loading ? 'Đang tải...' : `${users.length} / ${total} tài khoản đang hiển thị`}</span>
              </div>
            </div>
            <div className="ws-toolbar" style={{ marginBottom: 12 }}>
              <label className="ws-search">
                <span className="ws-sr-only">Tìm người dùng</span>
                <FontAwesomeIcon icon={faMagnifyingGlass} />
                <input className="ws-input" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Tìm theo tên hoặc email" />
              </label>
              <Segmented
                label="Lọc theo vai trò"
                value={roleFilter}
                onChange={selectRole}
                items={[
                  { value: 'all', label: 'Tất cả', count: stats.all ?? undefined },
                  { value: 'Admin', label: 'Quản trị', count: stats.Admin ?? undefined },
                  { value: 'Teacher', label: 'Giảng viên', count: stats.Teacher ?? undefined },
                  { value: 'Reviewer', label: 'Người duyệt', count: stats.Reviewer ?? undefined },
                ]}
              />
            </div>

            {loading && users.length === 0 ? (
              <SkeletonRows rows={5} lines={2} />
            ) : error ? (
              <ErrorState message={error} onRetry={refreshAll} />
            ) : users.length === 0 ? (
              <EmptyState
                icon={faUsers}
                title={searchTerm || roleFilter !== 'all' ? 'Không có tài khoản khớp bộ lọc' : 'Chưa có tài khoản'}
                description={searchTerm || roleFilter !== 'all' ? 'Thử đổi từ khoá hoặc vai trò.' : 'Thêm người dùng đầu tiên hoặc nhập danh sách từ CSV.'}
              />
            ) : (
              <div className="ws-table-wrap">
                <table className="ws-table">
                  <thead>
                    <tr>
                      <th>Người dùng</th>
                      <th>Vai trò</th>
                      <th>Trạng thái</th>
                      <th>Ngày tạo</th>
                      <th aria-label="Thao tác" />
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((item) => {
                      const avatar = normalizeAvatarUrl(item.profile?.avatar);
                      const self = isSelf(item);
                      return (
                        <tr key={item.id}>
                          <td>
                            <div className="ad-user">
                              {avatar ? (
                                <img className="ad-avatar" src={avatar} alt="" referrerPolicy="no-referrer" />
                              ) : (
                                <span className={`ad-avatar ad-avatar--${item.role}`} aria-hidden="true">{initials(item.display_name)}</span>
                              )}
                              <div style={{ minWidth: 0 }}>
                                <strong>{item.display_name}{self ? ' (bạn)' : ''}</strong>
                                <small>{item.email}</small>
                              </div>
                            </div>
                          </td>
                          <td><span className={`ws-pill ws-pill--${ROLE_TONE[item.role] || 'outline'}`}>{ROLE_LABEL[item.role] || item.role}</span></td>
                          <td>
                            <span className={`ws-pill ${item.is_active ? 'ws-pill--success' : 'ws-pill--outline'}`}>
                              {item.is_active ? 'Hoạt động' : 'Đã khoá'}
                            </span>
                          </td>
                          <td>{formatDate(item.created_at)}</td>
                          <td>
                            <MoreMenu
                              variant="icon"
                              label={`Thao tác với ${item.email}`}
                              items={[
                                { key: 'edit', label: 'Sửa', icon: faPen, onClick: () => openEdit(item) },
                                { key: 'reset', label: 'Tạo link đặt lại mật khẩu', icon: faKey, disabled: Boolean(busyKey), onClick: () => handleResetPassword(item) },
                                {
                                  key: 'toggle',
                                  label: item.is_active ? 'Khoá tài khoản' : 'Mở khoá',
                                  icon: item.is_active ? faLock : faLockOpen,
                                  danger: item.is_active,
                                  disabled: Boolean(busyKey) || self,
                                  title: self ? 'Không thể tự khoá tài khoản của mình' : undefined,
                                  onClick: () => handleToggleActive(item),
                                },
                              ]}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <Pagination page={page} pageSize={PAGE_SIZE} total={total} loading={loading} onChange={setPage} />
          </section>
        </div>
      </section>

      <Drawer
        open={Boolean(createState)}
        wide
        title="Thêm người dùng"
        onClose={() => setCreateState(null)}
        busy={busyKey === 'create'}
        as="form"
        onSubmit={submitCreate}
        footer={createState?.result ? (
          <button type="button" className="btn btn--primary" onClick={() => setCreateState(null)}>Xong</button>
        ) : (
          <>
            <button type="button" className="btn btn--outline" onClick={() => setCreateState(null)} disabled={busyKey === 'create'}>Huỷ</button>
            <button type="submit" className="btn btn--primary" disabled={busyKey === 'create'}>
              {busyKey === 'create' ? 'Đang lưu...' : (createState?.mode === 'invite' ? 'Tạo link mời' : 'Tạo tài khoản')}
            </button>
          </>
        )}
      >
        {createState && (createState.result?.reset_link ? (
          <>
            <Notice tone="success">Đã tạo tài khoản {createState.form.email}.</Notice>
            <SecretLink label="Link đặt mật khẩu" value={createState.result.reset_link} copied={copiedKey === 'invite'} onCopy={() => copy(createState.result.reset_link, 'invite')} />
          </>
        ) : (
          <>
            <Segmented
              label="Cách tạo tài khoản"
              value={createState.mode}
              onChange={(mode) => setCreateState((current) => ({ ...current, mode, error: '' }))}
              items={[
                { value: 'direct', label: 'Tạo trực tiếp' },
                { value: 'invite', label: 'Mời qua email' },
              ]}
            />
            <p className="ws-hint" style={{ margin: 0 }}>
              <FontAwesomeIcon icon={faEnvelope} style={{ marginRight: 6 }} />
              {createState.mode === 'invite'
                ? 'Hệ thống tạo tài khoản và một link để người dùng tự đặt mật khẩu.'
                : 'Bạn đặt mật khẩu ban đầu và gửi cho người dùng.'}
            </p>
            <div className="ws-form-grid">
              <label className="ws-field">
                <span>Email</span>
                <input className="ws-input" type="email" autoComplete="off" value={createState.form.email} onChange={(event) => updateCreate({ email: event.target.value })} placeholder="ten@ctu.edu.vn" />
              </label>
              <label className="ws-field">
                <span>Họ và tên</span>
                <input className="ws-input" value={createState.form.display_name} onChange={(event) => updateCreate({ display_name: event.target.value })} />
              </label>
              {createState.mode === 'direct' && (
                <label className="ws-field">
                  <span>Mật khẩu ban đầu</span>
                  <input className="ws-input" type="password" autoComplete="new-password" value={createState.form.password} onChange={(event) => updateCreate({ password: event.target.value })} />
                  <small>Tối thiểu 6 ký tự.</small>
                </label>
              )}
              <label className="ws-field">
                <span>Vai trò</span>
                <select className="ws-select" value={createState.form.role} onChange={(event) => updateCreate({ role: event.target.value, permissions: permissionsForRole(event.target.value) })}>
                  {ROLE_OPTIONS.map((role) => <option key={role.value} value={role.value}>{role.label}</option>)}
                </select>
              </label>
            </div>
            <PermissionPicker value={createState.form.permissions} onChange={(permissions) => updateCreate({ permissions })} />
            {createState.error && <Notice tone="error">{createState.error}</Notice>}
          </>
        ))}
      </Drawer>

      <Drawer
        open={Boolean(importState)}
        wide
        title="Nhập danh sách từ CSV"
        subtitle="Mỗi dòng: email, họ tên, vai trò (Teacher, Reviewer hoặc Admin), quyền cách nhau bằng dấu | (không bắt buộc)."
        onClose={() => setImportState(null)}
        busy={busyKey === 'import'}
        as="form"
        onSubmit={submitImport}
        footer={(
          <>
            <button type="button" className="btn btn--outline" onClick={() => setImportState(null)} disabled={busyKey === 'import'}>Đóng</button>
            <button type="submit" className="btn btn--primary" disabled={busyKey === 'import' || importRows.length === 0}>
              {busyKey === 'import' ? 'Đang nhập...' : (importRows.length ? `Nhập ${importRows.length} tài khoản` : 'Nhập tài khoản')}
            </button>
          </>
        )}
      >
        {importState && (
          <>
            <label className="ws-field">
              <span>Dữ liệu CSV</span>
              <textarea
                className="ws-textarea ad-code-editor"
                style={{ minHeight: 220 }}
                value={importState.text}
                onChange={(event) => setImportState((current) => ({ ...current, text: event.target.value, error: '', result: null }))}
                placeholder={'nguyenvana@ctu.edu.vn,Nguyễn Văn An,Teacher\ntranthib@ctu.edu.vn,Trần Thị Bích,Reviewer'}
              />
              {importRows.length > 0 && (
                <small className="tabular">
                  {importRows.length} dòng, {importValid} hợp lệ{importRows.length - importValid ? `, ${importRows.length - importValid} email chưa hợp lệ` : ''}
                </small>
              )}
            </label>
            {importState.error && <Notice tone="error">{importState.error}</Notice>}
            {importState.result && (
              <Notice tone={importState.result.failed ? 'warn' : 'success'}>
                {importState.result.created} tài khoản đã tạo, {importState.result.failed} lỗi.
                {(importState.result.items || []).filter((item) => !item.ok).slice(0, 5).map((item) => ` ${item.email}: ${item.error}.`).join('')}
              </Notice>
            )}
          </>
        )}
      </Drawer>

      <Drawer
        open={Boolean(editState)}
        wide
        title="Sửa tài khoản"
        subtitle={editState?.user?.email}
        onClose={() => setEditState(null)}
        busy={busyKey === 'edit'}
        as="form"
        onSubmit={submitEdit}
        footer={(
          <>
            <button type="button" className="btn btn--outline" onClick={() => setEditState(null)} disabled={busyKey === 'edit'}>Huỷ</button>
            <button type="submit" className="btn btn--primary" disabled={busyKey === 'edit'}>{busyKey === 'edit' ? 'Đang lưu...' : 'Lưu thay đổi'}</button>
          </>
        )}
      >
        {editState && (
          <>
            <div className="ws-form-grid">
              <label className="ws-field">
                <span>Họ và tên</span>
                <input className="ws-input" value={editState.form.display_name} onChange={(event) => updateEdit({ display_name: event.target.value })} />
              </label>
              <label className="ws-field">
                <span>Vai trò</span>
                <select
                  className="ws-select"
                  value={editState.form.role}
                  disabled={isSelf(editState.user)}
                  title={isSelf(editState.user) ? 'Không tự đổi vai trò của chính mình' : undefined}
                  onChange={(event) => updateEdit({ role: event.target.value, permissions: permissionsForRole(event.target.value) })}
                >
                  {ROLE_OPTIONS.map((role) => <option key={role.value} value={role.value}>{role.label}</option>)}
                </select>
              </label>
            </div>
            <PermissionPicker value={editState.form.permissions} onChange={(permissions) => updateEdit({ permissions })} />
            <label className="ws-check">
              <input type="checkbox" checked={editState.form.is_active} disabled={isSelf(editState.user)} onChange={(event) => updateEdit({ is_active: event.target.checked })} />
              Tài khoản đang hoạt động
            </label>
            {editState.error && <Notice tone="error">{editState.error}</Notice>}
          </>
        )}
      </Drawer>

      <Drawer
        open={Boolean(resetResult)}
        title="Link đặt lại mật khẩu"
        subtitle={resetResult?.email}
        onClose={() => setResetResult(null)}
        footer={<button type="button" className="btn btn--primary" onClick={() => setResetResult(null)}>Xong</button>}
      >
        {resetResult?.reset_link && (
          <SecretLink label="Link đặt lại" value={resetResult.reset_link} copied={copiedKey === 'reset'} onCopy={() => copy(resetResult.reset_link, 'reset')} />
        )}
      </Drawer>
      {confirmDialog}
    </main>
  );
}

export default UsersAdminPage;
