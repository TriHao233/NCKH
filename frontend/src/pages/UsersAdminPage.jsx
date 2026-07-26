import React, { useEffect, useMemo, useState } from 'react';
import { createUser, deleteUser, listUsers, updateUser } from '../api/users';
import '../css/UsersAdminPage.css';

const ROLE_LABEL = { Admin: 'Quản trị viên', Teacher: 'Giảng viên' };

const emptyCreateForm = {
  email: '',
  password: '',
  display_name: '',
  role: 'Teacher',
};

function UsersAdminPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [roleFilter, setRoleFilter] = useState('all');
  const [searchInput, setSearchInput] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState(emptyCreateForm);
  const [creating, setCreating] = useState(false);

  const [editing, setEditing] = useState(null);
  const [editDisplayName, setEditDisplayName] = useState('');
  const [editRole, setEditRole] = useState('Teacher');
  const [editActive, setEditActive] = useState(true);
  const [saving, setSaving] = useState(false);

  const [deletingId, setDeletingId] = useState(null);

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
    }),
    [users],
  );

  const openCreate = () => {
    setCreateForm(emptyCreateForm);
    setShowCreate(true);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!createForm.email.trim() || !createForm.password || !createForm.display_name.trim()) {
      alert('Vui lòng nhập đầy đủ email, mật khẩu và họ tên.');
      return;
    }
    setCreating(true);
    try {
      await createUser(createForm);
      setShowCreate(false);
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
      });
      setEditing(null);
      await fetchUsers(searchTerm);
    } catch (err) {
      alert('Cập nhật tài khoản thất bại: ' + err.message);
    } finally {
      setSaving(false);
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
            <div className="page-hero-badge">Admin Dashboard</div>
            <h1 className="page-hero-title">Quản lý người dùng</h1>
            <p className="page-hero-desc">
              Quản lý tài khoản giảng viên và quản trị viên trong hệ thống ngân hàng câu hỏi.
            </p>
          </div>
          <div className="users-hero-actions">
            <button type="button" className="btn btn--primary" onClick={openCreate}>
              + Tạo tài khoản mới
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
                    </div>
                    <div className="user-actions">
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
            <h3 className="modal-title">Tạo tài khoản mới</h3>

            <div className="field-group">
              <label className="field-label">Email</label>
              <input
                className="field-input"
                type="email"
                value={createForm.email}
                onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
              />
            </div>

            <div className="field-group">
              <label className="field-label">Mật khẩu</label>
              <input
                className="field-input"
                type="password"
                value={createForm.password}
                onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
              />
            </div>

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
                onChange={(e) => setCreateForm({ ...createForm, role: e.target.value })}
              >
                <option value="Teacher">Giảng viên</option>
                <option value="Admin">Quản trị viên</option>
              </select>
            </div>

            <div className="modal-actions">
              <button type="button" className="btn btn--outline" onClick={() => setShowCreate(false)} disabled={creating}>
                Huỷ
              </button>
              <button type="submit" className="btn btn--primary" disabled={creating}>
                {creating ? 'Đang tạo...' : 'Tạo tài khoản'}
              </button>
            </div>
          </form>
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
              <select className="field-select" value={editRole} onChange={(e) => setEditRole(e.target.value)}>
                <option value="Teacher">Giảng viên</option>
                <option value="Admin">Quản trị viên</option>
              </select>
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
