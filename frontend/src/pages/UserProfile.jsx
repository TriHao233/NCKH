import React, { useContext, useEffect, useState } from 'react';
import { AuthContext } from '../context/AuthContext';
import { apiRequest } from '../services/apiClient';
import '../css/UserProfile.css';

function UserProfile() {
  const { user, updateUser } = useContext(AuthContext);

  const displayName = user?.display_name || 'Giảng viên';
  const displayEmail = user?.email || '';
  const displayRole = user?.role || 'Teacher';
  const displaySchool = user?.profile?.school || '';
  const displayAddress = user?.profile?.address || '';
  const displayStatus = user?.is_active ? 'Đang hoạt động' : 'Ngừng hoạt động';
  const joinedAt = user?.created_at
    ? new Date(user.created_at).toLocaleDateString('vi-VN')
    : '—';
  const avatarUrl = user?.profile?.avatar || `https://ui-avatars.com/api/?name=${encodeURIComponent(displayName)}&background=0c78d4&color=fff`;

  const [fullName, setFullName] = useState(displayName);
  const [school, setSchool] = useState(displaySchool);
  const [address, setAddress] = useState(displayAddress);
  const [isSaving, setIsSaving] = useState(false);

  // Đồng bộ lại form khi dữ liệu user từ AuthContext sẵn sàng/thay đổi
  useEffect(() => {
    setFullName(displayName);
    setSchool(displaySchool);
    setAddress(displayAddress);
  }, [user]);

  const handleSaveProfile = async (e) => {
    e.preventDefault();
    if (!fullName.trim()) {
      alert('Họ và tên không được để trống.');
      return;
    }

    setIsSaving(true);
    try {
      const data = await apiRequest('/auth/profile', {
        method: 'PUT',
        body: {
          full_name: fullName,
          school,
          address,
          avatar: user?.profile?.avatar || '',
        },
      });

      updateUser(data.user);
      alert('Cập nhật hồ sơ thành công!');
    } catch (error) {
      alert('Cập nhật hồ sơ thất bại: ' + error.message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <main className="profile-page">
      <section className="page-hero">
        <div className="container profile-hero-row">
          <img src={avatarUrl} alt="Ảnh đại diện" className="profile-avatar" referrerPolicy="no-referrer" />
          <div className="profile-hero-text">
            <span className="profile-role-badge">{displayRole}</span>
            <h1 className="page-hero-title">{displayName}</h1>
            <p className="page-hero-desc">{displayEmail}</p>
          </div>
        </div>
      </section>

      <section className="profile-body">
        <div className="container profile-grid">
          {/* Main column */}
          <div className="profile-main">
            <form className="card profile-card" onSubmit={handleSaveProfile}>
              <h3 className="profile-card-title">Thông tin cá nhân</h3>

              <div className="field-group">
                <label className="field-label">Họ và tên</label>
                <input
                  className="field-input"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>

              <div className="field-row-2">
                <div className="field-group">
                  <label className="field-label">Email</label>
                  <input className="field-input" value={displayEmail} disabled />
                  <span className="field-hint">Không thể thay đổi email</span>
                </div>
                <div className="field-group">
                  <label className="field-label">Vai trò</label>
                  <input className="field-input" value={displayRole} disabled />
                </div>
              </div>

              <div className="field-group">
                <label className="field-label">Đơn vị công tác</label>
                <input
                  className="field-input"
                  value={school}
                  onChange={(e) => setSchool(e.target.value)}
                />
              </div>

              <div className="field-group">
                <label className="field-label">Địa chỉ</label>
                <input
                  className="field-input"
                  placeholder="Chưa cập nhật"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                />
              </div>

              <button className="btn btn--primary" type="submit" disabled={isSaving}>
                {isSaving ? 'Đang lưu...' : 'Lưu thay đổi'}
              </button>
            </form>

            <form className="card profile-card" onSubmit={(e) => e.preventDefault()}>
              <h3 className="profile-card-title">Đổi mật khẩu</h3>

              <div className="field-group">
                <label className="field-label">Mật khẩu hiện tại</label>
                <input className="field-input" type="password" placeholder="••••••••" />
              </div>

              <div className="field-row-2">
                <div className="field-group">
                  <label className="field-label">Mật khẩu mới</label>
                  <input className="field-input" type="password" placeholder="••••••••" />
                </div>
                <div className="field-group">
                  <label className="field-label">Xác nhận mật khẩu mới</label>
                  <input className="field-input" type="password" placeholder="••••••••" />
                </div>
              </div>

              <button className="btn btn--outline" type="submit">Đổi mật khẩu</button>
            </form>
          </div>

          {/* Sidebar */}
          <aside className="profile-side">
            <div className="card side-card">
              <h3>Trạng thái tài khoản</h3>
              <div className="status-row">
                <span className="status-dot" />
                {displayStatus}
              </div>
              <ul className="info-list">
                <li>
                  <span className="info-list-label">Vai trò</span>
                  <span>{displayRole}</span>
                </li>
                <li>
                  <span className="info-list-label">Ngày tham gia</span>
                  <span>{joinedAt}</span>
                </li>
              </ul>
            </div>

            <div className="card side-card">
              <h3>Hoạt động gần đây</h3>
              <p className="side-note">Chưa có hoạt động nào được ghi nhận.</p>
            </div>
          </aside>
        </div>
      </section>
    </main>
  );
}

export default UserProfile;
