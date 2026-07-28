import React, { useEffect, useMemo, useState } from 'react';
import { createUser, deleteUser, importUsers, inviteUser, listUsers, resetUserPassword, updateUser } from '../api/users';
import { ROLE_DEFAULT_PERMISSIONS } from '../auth/permissions';
import '../css/UsersAdminPage.css';

const ROLE_LABEL = {
  Admin: 'Quản trị viên',
  Teacher: 'Giảng viên',
  Reviewer: 'Người duyệt',
};

const PERMISSION_OPTIONS = [
  { value: 'questions.generate', label: 'Sinh câu hỏi' },
  { value: 'questions.manage_own', label: 'Quản lý câu hỏi cá nhân' },
  { value: 'questions.share_bank', label: 'Chia sẻ ngân hàng câu hỏi' },
  { value: 'questions.use_shared_bank', label: 'Dùng ngân hàng được chia sẻ' },
  { value: 'reviews.manage', label: 'Kiểm duyệt câu hỏi' },
  { value: 'documents.manage_own', label: 'Quản lý tài liệu cá nhân' },
  { value: 'documents.manage_all', label: 'Quản lý mọi tài liệu' },
  { value: 'exams.manage_own', label: 'Làm đề thi' },
  { value: 'admin.overview', label: 'Tổng quan Admin' },
  { value: 'admin.users', label: 'Quản lý người dùng' },
  { value: 'admin.catalog', label: 'Quản lý danh mục' },
  { value: 'admin.audit', label: 'Xem audit log' },
  { value: 'admin.jobs', label: 'Quản lý job' },
  { value: 'admin.moodle', label: 'Quản lý Moodle' },
];

const emptyCreateForm = {
  email: '',
  password: '',
  display_name: '',
  role: 'Teacher',
  permissions: [...ROLE_DEFAULT_PERMISSIONS.Teacher],
};

function permissionsForRole(role) {
  return [...(ROLE_DEFAULT_PERMISSIONS[role] || [])];
}

function togglePermission(list, permission) {
  const current = new Set(list || []);
  if (current.has(permission)) {
    current.delete(permission);
  } else {
    current.add(permission);
  }
  return Array.from(current);
}

function UsersAdminPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [roleFilter, setRoleFilter] = useState('all');
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  const [showCreate, setShowCreate] = useState(false);
  const [createMode, setCreateMode] = useState('direct');
  const [createForm, setCreateForm] = useState(emptyCreateForm);
  const [creating, setCreating] = useState(false);
  const [inviteResult, setInviteResult] = useState(null);
  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState('');
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);

  const [editing, setEditing] = useState(null);
  const [editDisplayName, setEditDisplayName] = useState('');
  const [editRole, setEditRole] = useState('Teacher');
  const [editActive, setEditActive] = useState(true);
  const [editPermissions, setEditPermissions] = useState([]);
  const [saving, setSaving] = useState(false);

  const [deletingId, setDeletingId] = useState(null);
  const [resettingId, setResettingId] = useState(null);
  const [resetResult, setResetResult] = useState(null);

  useEffect(() => {
    const handle = setTimeout(() => setSearchTerm(searchInput.trim()), 400);
    return () => clearTimeout(handle);
  }, [searchInput]);

  const fetchUsers = async (search) => {
    setLoading(true);
    setError('');
    try {
      const result = await listUsers({ page: 1, pageSize: 100, search: search || undefined });
      setUsers(result.items || []);
    } catch (err) {
      setError(err.message || 'Không tải được danh sách người dùng');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers(searchTerm);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchTerm]);

  const filtered = useMemo(
    () => users.filter((u) => roleFilter === 'all' || u.role === roleFilter),
    [users, roleFilter],
  );

  const counts = useMemo(
    () => ({
      all: users.length,
      Admin: users.filter((u) => u.role === 'Admin').length,
      Teacher: users.filter((u) => u.role === 'Teacher').length,
      Reviewer: users.filter((u) => u.role === 'Reviewer').length,
    }),
    [users],
  );

  const openCreate = (mode = 'direct') => {
    setCreateMode(mode);
    setInviteResult(null);
    setCreateForm({
      ...emptyCreateForm,
      password: '',
      permissions: permissionsForRole('Teacher'),
    });
    setShowCreate(true);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!createForm.email.trim() || !createForm.display_name.trim() || (createMode === 'direct' && !createForm.password)) {
      alert('Vui lòng nhập đầy đủ email, mật khẩu và họ tên.');
      return;
    }
    setCreating(true);
    try {
      const payload = {
        ...createForm,
        permissions: createForm.permissions || [],
      };
      if (createMode === 'invite') {
        const result = await inviteUser({
          email: payload.email,
          display_name: payload.display_name,
          role: payload.role,
          permissions: payload.permissions,
        });
        setInviteResult(result);
      } else {
        await createUser(payload);
        setShowCreate(false);
      }
      await fetchUsers(searchTerm);
    } catch (err) {
      alert('Tạo tài khoản thất bại: ' + err.message);
    } finally {
      setCreating(false);
    }
  };

  const openEdit = (user) => {
    setEditing(user);
    setEditDisplayName(user.display_name || '');
    setEditRole(user.role);
    setEditActive(user.is_active);
    setEditPermissions(user.permissions || permissionsForRole(user.role));
  };

  const closeEdit = () => {
    if (saving) return;
    setEditing(null);
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editing) return;
    setSaving(true);
    try {
      await updateUser(editing.id, {
        display_name: editDisplayName,
        role: editRole,
        is_active: editActive,
        permissions: editPermissions,
      });
      setEditing(null);
      await fetchUsers(searchTerm);
    } catch (err) {
      alert('Cập nhật tài khoản thất bại: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleResetPassword = async (user) => {
    setResettingId(user.id);
    try {
      const result = await resetUserPassword(user.id);
      setResetResult(result);
    } catch (err) {
      alert('Tạo link reset mật khẩu thất bại: ' + err.message);
    } finally {
      setResettingId(null);
    }
  };

  const parseImportRows = () => importText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [email, displayName, role = 'Teacher', permissions = ''] = line.split(',').map((part) => part.trim());
      return {
        email,
        display_name: displayName || email,
        role: ROLE_LABEL[role] ? role : 'Teacher',
        permissions: permissions
          ? permissions.split('|').map((item) => item.trim()).filter(Boolean)
          : permissionsForRole(ROLE_LABEL[role] ? role : 'Teacher'),
      };
    });

  const handleImportUsers = async (event) => {
    event.preventDefault();
    const rows = parseImportRows();
    if (rows.length === 0) {
      alert('Vui lòng nhập ít nhất một dòng CSV.');
      return;
    }
    setImporting(true);
    setImportResult(null);
    try {
      const result = await importUsers({ users: rows });
      setImportResult(result);
      await fetchUsers(searchTerm);
    } catch (err) {
      alert('Import tài khoản thất bại: ' + err.message);
    } finally {
      setImporting(false);
    }
  };

  const handleDelete = async (user) => {
    if (!window.confirm(`Vô hiệu hoá tài khoản "${user.display_name}" (${user.email})?`)) {
      return;
    }
    setDeletingId(user.id);
    try {
      await deleteUser(user.id);
      await fetchUsers(searchTerm);
    } catch (err) {
      alert('Vô hiệu hoá tài khoản thất bại: ' + err.message);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <main className="users-page">
      <section className="page-hero">
        <div className="container users-hero-row">
          <div>
            <div className="page-hero-badge">Khu vực quản trị</div>
            <h1 className="page-hero-title">Quản lý người dùng</h1>
            <p className="page-hero-desc">
              Quản lý tài khoản giảng viên, người duyệt và quản trị viên trong hệ thống ngân hàng câu hỏi.
            </p>
          </div>
          <div className="users-hero-actions">
            <button type="button" className="btn btn--outline" onClick={() => setShowImport(true)}>
              Import CSV
            </button>
            <button type="button" className="btn btn--outline" onClick={() => openCreate('invite')}>
              Mời qua email
            </button>
            <button type="button" className="btn btn--primary" onClick={() => openCreate('direct')}>
              + Tạo bằng mật khẩu
            </button>
          </div>
        </div>
      </section>

      <section className="users-body">
        <div className="container">
          <div className="stats-row">
            <button type="button" className={`stat-card ${roleFilter === 'all' ? 'stat-card--active' : ''}`} onClick={() => setRoleFilter('all')}>
              <b>{counts.all}</b>
              <span>Tổng tài khoản</span>
            </button>
            <button type="button" className={`stat-card ${roleFilter === 'Admin' ? 'stat-card--active' : ''}`} onClick={() => setRoleFilter('Admin')}>
              <b>{counts.Admin}</b>
              <span>Quản trị viên</span>
            </button>
            <button type="button" className={`stat-card ${roleFilter === 'Teacher' ? 'stat-card--active' : ''}`} onClick={() => setRoleFilter('Teacher')}>
              <b>{counts.Teacher}</b>
              <span>Giảng viên</span>
            </button>
            <button type="button" className={`stat-card ${roleFilter === 'Reviewer' ? 'stat-card--active' : ''}`} onClick={() => setRoleFilter('Reviewer')}>
              <b>{counts.Reviewer}</b>
              <span>Người duyệt</span>
            </button>
          </div>

          <div className="card list-card">
            <div className="list-card-header">
              <h3>Danh sách người dùng</h3>
              <div className="list-toolbar">
                <input
                  className="field-input search-input"
                  placeholder="Tìm theo tên hoặc email..."
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                />
              </div>
            </div>

            {error && <p className="users-error">{error}</p>}

            {loading ? (
              <p className="empty-note">Đang tải danh sách người dùng...</p>
            ) : (
              <div className="user-list">
                {filtered.map((u) => (
                  <article key={u.id} className="user-item">
                    <img
                      className="user-avatar-sm"
                      src={u.profile?.avatar || `https://ui-avatars.com/api/?name=${encodeURIComponent(u.display_name)}&background=0c78d4&color=fff`}
                      alt=""
                      referrerPolicy="no-referrer"
                    />
                    <div className="user-main">
                      <div className="user-meta-row">
                        <span className="user-name">{u.display_name}</span>
                        <span className="role-tag">{ROLE_LABEL[u.role] || u.role}</span>
                        {!u.is_active && <span className="status-badge status--revise">Đã khoá</span>}
                      </div>
                      <p className="user-email">{u.email}</p>
                      <p className="user-email">{(u.permissions || []).length} quyền hiệu lực</p>
                    </div>
                    <div className="user-actions">
                      <button
                        type="button"
                        className="icon-btn"
                        title="Tạo link reset mật khẩu"
                        disabled={resettingId === u.id}
                        onClick={() => handleResetPassword(u)}
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 7a4 4 0 1 0-4 4" /><path d="M21 2l-9.6 9.6" /><path d="M15 2h6v6" /></svg>
                      </button>
                      <button type="button" className="icon-btn" title="Chỉnh sửa" onClick={() => openEdit(u)}>
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" /></svg>
                      </button>
                      <button
                        type="button"
                        className="icon-btn icon-btn--danger"
                        title="Vô hiệu hoá"
                        disabled={deletingId === u.id}
                        onClick={() => handleDelete(u)}
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6" /></svg>
                      </button>
                    </div>
                  </article>
                ))}
                {filtered.length === 0 && (
                  <p className="empty-note">Không có người dùng nào phù hợp.</p>
                )}
              </div>
            )}
          </div>
        </div>
      </section>

      {showCreate && (
        <div className="modal-overlay" onClick={() => !creating && setShowCreate(false)}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={handleCreate}>
            <h3 className="modal-title">{createMode === 'invite' ? 'Mời tài khoản mới' : 'Tạo tài khoản bằng mật khẩu'}</h3>

            <div className="field-group">
              <label className="field-label">Email</label>
              <input
                className="field-input"
                type="email"
                value={createForm.email}
                onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
              />
            </div>

            {createMode === 'direct' && (
              <div className="field-group">
                <label className="field-label">Mật khẩu</label>
                <input
                  className="field-input"
                  type="password"
                  value={createForm.password}
                  onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                />
              </div>
            )}

            <div className="field-group">
              <label className="field-label">Họ và tên</label>
              <input
                className="field-input"
                value={createForm.display_name}
                onChange={(e) => setCreateForm({ ...createForm, display_name: e.target.value })}
              />
            </div>

            <div className="field-group">
              <label className="field-label">Vai trò</label>
              <select
                className="field-select"
                value={createForm.role}
                onChange={(e) => setCreateForm({
                  ...createForm,
                  role: e.target.value,
                  permissions: permissionsForRole(e.target.value),
                })}
              >
                <option value="Teacher">Giảng viên</option>
                <option value="Reviewer">Người duyệt</option>
                <option value="Admin">Quản trị viên</option>
              </select>
            </div>

            <div className="field-group">
              <label className="field-label">Quyền chi tiết</label>
              <div className="permission-grid">
                {PERMISSION_OPTIONS.map((permission) => (
                  <label className="field-checkbox" key={permission.value}>
                    <input
                      type="checkbox"
                      checked={(createForm.permissions || []).includes(permission.value)}
                      onChange={() => setCreateForm({
                        ...createForm,
                        permissions: togglePermission(createForm.permissions, permission.value),
                      })}
                    />
                    {permission.label}
                  </label>
                ))}
              </div>
            </div>

            {inviteResult?.reset_link && (
              <div className="users-result-box">
                <b>Link đặt mật khẩu</b>
                <textarea className="field-input" readOnly value={inviteResult.reset_link} rows={3} />
              </div>
            )}

            <div className="modal-actions">
              <button type="button" className="btn btn--outline" onClick={() => setShowCreate(false)} disabled={creating}>
                Huỷ
              </button>
              <button type="submit" className="btn btn--primary" disabled={creating}>
                {creating ? 'Đang lưu...' : (createMode === 'invite' ? 'Tạo link mời' : 'Tạo tài khoản')}
              </button>
            </div>
          </form>
        </div>
      )}

      {showImport && (
        <div className="modal-overlay" onClick={() => !importing && setShowImport(false)}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={handleImportUsers}>
            <h3 className="modal-title">Import người dùng</h3>
            <div className="field-group">
              <label className="field-label">CSV</label>
              <textarea
                className="field-input"
                rows={8}
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
                placeholder="email@ctu.edu.vn,Nguyễn Văn A,Teacher,questions.generate|questions.manage_own"
              />
            </div>
            {importResult && (
              <div className="users-result-box">
                <b>{importResult.created} tạo thành công, {importResult.failed} lỗi</b>
                {(importResult.items || []).slice(0, 8).map((item) => (
                  <p key={item.email}>{item.email}: {item.ok ? 'OK' : item.error}</p>
                ))}
              </div>
            )}
            <div className="modal-actions">
              <button type="button" className="btn btn--outline" onClick={() => setShowImport(false)} disabled={importing}>
                Đóng
              </button>
              <button type="submit" className="btn btn--primary" disabled={importing}>
                {importing ? 'Đang import...' : 'Import'}
              </button>
            </div>
          </form>
        </div>
      )}

      {resetResult && (
        <div className="modal-overlay" onClick={() => setResetResult(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <h3 className="modal-title">Link reset mật khẩu</h3>
            <p className="user-email">{resetResult.email}</p>
            <textarea className="field-input" readOnly rows={4} value={resetResult.reset_link} />
            <div className="modal-actions">
              <button type="button" className="btn btn--primary" onClick={() => setResetResult(null)}>
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}

      {editing && (
        <div className="modal-overlay" onClick={closeEdit}>
          <form className="modal-card" onClick={(e) => e.stopPropagation()} onSubmit={handleSaveEdit}>
            <h3 className="modal-title">Chỉnh sửa tài khoản</h3>

            <div className="field-group">
              <label className="field-label">Email</label>
              <input className="field-input" value={editing.email} disabled />
            </div>

            <div className="field-group">
              <label className="field-label">Họ và tên</label>
              <input
                className="field-input"
                value={editDisplayName}
                onChange={(e) => setEditDisplayName(e.target.value)}
              />
            </div>

            <div className="field-group">
              <label className="field-label">Vai trò</label>
              <select
                className="field-select"
                value={editRole}
                onChange={(e) => {
                  setEditRole(e.target.value);
                  setEditPermissions(permissionsForRole(e.target.value));
                }}
              >
                <option value="Teacher">Giảng viên</option>
                <option value="Reviewer">Người duyệt</option>
                <option value="Admin">Quản trị viên</option>
              </select>
            </div>

            <div className="field-group">
              <label className="field-label">Quyền chi tiết</label>
              <div className="permission-grid">
                {PERMISSION_OPTIONS.map((permission) => (
                  <label className="field-checkbox" key={permission.value}>
                    <input
                      type="checkbox"
                      checked={(editPermissions || []).includes(permission.value)}
                      onChange={() => setEditPermissions((current) => togglePermission(current, permission.value))}
                    />
                    {permission.label}
                  </label>
                ))}
              </div>
            </div>

            <div className="field-group field-group--checkbox">
              <label className="field-checkbox">
                <input
                  type="checkbox"
                  checked={editActive}
                  onChange={(e) => setEditActive(e.target.checked)}
                />
                Tài khoản đang hoạt động
              </label>
            </div>

            <div className="modal-actions">
              <button type="button" className="btn btn--outline" onClick={closeEdit} disabled={saving}>
                Huỷ
              </button>
              <button type="submit" className="btn btn--primary" disabled={saving}>
                {saving ? 'Đang lưu...' : 'Lưu thay đổi'}
              </button>
            </div>
          </form>
        </div>
      )}
    </main>
  );
}

export default UsersAdminPage;
