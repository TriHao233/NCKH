import React, { useContext, useEffect, useMemo, useState } from 'react';
import {
  EmailAuthProvider,
  reauthenticateWithCredential,
  updatePassword,
} from 'firebase/auth';
import { AuthContext } from '../context/AuthContext';
import { auth } from '../../firebase';
import { getMe, getMyStats, updateMe } from '../api/users';
import '../css/UserProfile.css';

const MAX_SCHOOL_LENGTH = 200;
const MAX_ADDRESS_LENGTH = 300;
const URL_PATTERN = /^https?:\/\/[^\s]+$/i;

function buildFallbackAvatar(name) {
  return `https://ui-avatars.com/api/?name=${encodeURIComponent(name || 'U')}&background=0c78d4&color=fff`;
}

function toFormState(user) {
  return {
    displayName: user?.display_name || '',
    school: user?.profile?.school || '',
    address: user?.profile?.address || '',
    avatar: user?.profile?.avatar || '',
  };
}

function validateForm(form) {
  const errors = {};
  if (!form.displayName.trim()) {
    errors.displayName = 'Họ và tên không được để trống.';
  }
  if (form.school.trim().length > MAX_SCHOOL_LENGTH) {
    errors.school = `Đơn vị công tác không vượt quá ${MAX_SCHOOL_LENGTH} ký tự.`;
  }
  if (form.address.trim().length > MAX_ADDRESS_LENGTH) {
    errors.address = `Địa chỉ không vượt quá ${MAX_ADDRESS_LENGTH} ký tự.`;
  }
  if (form.avatar.trim() && !URL_PATTERN.test(form.avatar.trim())) {
    errors.avatar = 'Ảnh đại diện phải là một URL hợp lệ (bắt đầu bằng http:// hoặc https://) hoặc để trống.';
  }
  return errors;
}

function mapFirebaseAuthError(error) {
  const code = error?.code || '';
  if (code === 'auth/wrong-password' || code === 'auth/invalid-credential') {
    return 'Mật khẩu hiện tại không đúng.';
  }
  if (code === 'auth/weak-password') {
    return 'Mật khẩu mới quá yếu, cần tối thiểu 6 ký tự.';
  }
  if (code === 'auth/too-many-requests') {
    return 'Bạn đã thử quá nhiều lần. Vui lòng thử lại sau.';
  }
  if (code === 'auth/requires-recent-login') {
    return 'Phiên đăng nhập đã cũ. Vui lòng đăng xuất rồi đăng nhập lại trước khi đổi mật khẩu.';
  }
  return error?.message || 'Đổi mật khẩu thất bại.';
}

function InfoTab({ user, onProfileUpdated }) {
  const [initialForm, setInitialForm] = useState(() => toFormState(user));
  const [form, setForm] = useState(() => toFormState(user));
  const [fieldErrors, setFieldErrors] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [banner, setBanner] = useState(null); // { type: 'success' | 'error', message }

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    getMe()
      .then((freshUser) => {
        if (!active) return;
        const next = toFormState(freshUser);
        setInitialForm(next);
        setForm(next);
        onProfileUpdated(freshUser);
      })
      .catch(() => {
        // Nếu không tải được bản mới nhất, vẫn dùng dữ liệu sẵn có từ AuthContext.
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isDirty = useMemo(
    () =>
      form.displayName !== initialForm.displayName ||
      form.school !== initialForm.school ||
      form.address !== initialForm.address ||
      form.avatar !== initialForm.avatar,
    [form, initialForm],
  );

  const handleChange = (field) => (e) => {
    setForm((prev) => ({ ...prev, [field]: e.target.value }));
  };

  const handleUseDefaultAvatar = () => {
    setForm((prev) => ({ ...prev, avatar: '' }));
  };

  const handleReset = () => {
    setForm(initialForm);
    setFieldErrors({});
    setBanner(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errors = validateForm(form);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      return;
    }

    setIsSaving(true);
    setBanner(null);
    try {
      const updated = await updateMe({
        display_name: form.displayName.trim(),
        profile: {
          school: form.school.trim(),
          address: form.address.trim(),
          avatar: form.avatar.trim(),
        },
      });
      onProfileUpdated(updated);
      const next = toFormState(updated);
      setInitialForm(next);
      setForm(next);
      setBanner({ type: 'success', message: 'Đã lưu thay đổi hồ sơ.' });
    } catch (error) {
      setBanner({ type: 'error', message: error.message || 'Cập nhật hồ sơ thất bại.' });
    } finally {
      setIsSaving(false);
    }
  };

  const avatarPreview = form.avatar.trim() || buildFallbackAvatar(form.displayName);

  return (
    <form className="card profile-card" onSubmit={handleSubmit}>
      <h3 className="profile-card-title">Thông tin cá nhân</h3>

      {banner && (
        <div className={`profile-banner profile-banner--${banner.type}`}>{banner.message}</div>
      )}

      <div className="field-group">
        <label className="field-label">Ảnh đại diện</label>
        <div className="avatar-edit-row">
          <img src={avatarPreview} alt="Xem trước ảnh đại diện" className="avatar-preview" referrerPolicy="no-referrer" />
          <div className="avatar-edit-controls">
            <input
              className="field-input"
              placeholder="Dán URL ảnh (https://...)"
              value={form.avatar}
              onChange={handleChange('avatar')}
              disabled={isLoading}
            />
            <button
              type="button"
              className="btn btn--outline btn--small"
              onClick={handleUseDefaultAvatar}
              disabled={isLoading}
            >
              Dùng avatar mặc định
            </button>
          </div>
        </div>
        {fieldErrors.avatar && <span className="field-error">{fieldErrors.avatar}</span>}
      </div>

      <div className="field-group">
        <label className="field-label">Họ và tên</label>
        <input
          className="field-input"
          value={form.displayName}
          onChange={handleChange('displayName')}
          disabled={isLoading}
        />
        {fieldErrors.displayName && <span className="field-error">{fieldErrors.displayName}</span>}
      </div>

      <div className="field-row-2">
        <div className="field-group">
          <label className="field-label">Email</label>
          <input className="field-input" value={user?.email || ''} disabled />
          <span className="field-hint">Không thể thay đổi email tại đây.</span>
        </div>
        <div className="field-group">
          <label className="field-label">Vai trò</label>
          <input className="field-input" value={user?.role || ''} disabled />
          <span className="field-hint">Chỉ quản trị viên mới thay đổi được vai trò.</span>
        </div>
      </div>

      <div className="field-group">
        <label className="field-label">Đơn vị công tác</label>
        <input
          className="field-input"
          value={form.school}
          onChange={handleChange('school')}
          maxLength={MAX_SCHOOL_LENGTH}
          disabled={isLoading}
        />
        {fieldErrors.school && <span className="field-error">{fieldErrors.school}</span>}
      </div>

      <div className="field-group">
        <label className="field-label">Địa chỉ</label>
        <input
          className="field-input"
          placeholder="Chưa cập nhật"
          value={form.address}
          onChange={handleChange('address')}
          maxLength={MAX_ADDRESS_LENGTH}
          disabled={isLoading}
        />
        {fieldErrors.address && <span className="field-error">{fieldErrors.address}</span>}
      </div>

      <div className="field-row-2">
        <div className="field-group">
          <label className="field-label">Trạng thái tài khoản</label>
          <input className="field-input" value={user?.is_active ? 'Đang hoạt động' : 'Ngừng hoạt động'} disabled />
        </div>
        <div className="field-group">
          <label className="field-label">Ngày tham gia</label>
          <input
            className="field-input"
            value={user?.created_at ? new Date(user.created_at).toLocaleDateString('vi-VN') : '—'}
            disabled
          />
        </div>
      </div>

      <div className="profile-actions">
        <button className="btn btn--primary" type="submit" disabled={isSaving || isLoading || !isDirty}>
          {isSaving ? 'Đang lưu...' : 'Lưu thay đổi'}
        </button>
        <button
          className="btn btn--outline"
          type="button"
          onClick={handleReset}
          disabled={isSaving || isLoading || !isDirty}
        >
          Khôi phục
        </button>
      </div>
    </form>
  );
}

function SecurityTab() {
  const isPasswordAccount = (auth.currentUser?.providerData || []).some(
    (provider) => provider.providerId === 'password',
  );

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [banner, setBanner] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errors = {};
    if (!currentPassword) errors.currentPassword = 'Vui lòng nhập mật khẩu hiện tại.';
    if (!newPassword || newPassword.length < 6) errors.newPassword = 'Mật khẩu mới cần tối thiểu 6 ký tự.';
    if (newPassword !== confirmPassword) errors.confirmPassword = 'Xác nhận mật khẩu không khớp.';
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setIsSubmitting(true);
    setBanner(null);
    try {
      const credential = EmailAuthProvider.credential(auth.currentUser.email, currentPassword);
      await reauthenticateWithCredential(auth.currentUser, credential);
      await updatePassword(auth.currentUser, newPassword);
      setBanner({ type: 'success', message: 'Đổi mật khẩu thành công.' });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (error) {
      setBanner({ type: 'error', message: mapFirebaseAuthError(error) });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="card profile-card">
      <h3 className="profile-card-title">Bảo mật</h3>

      <div className="field-group">
        <label className="field-label">Phương thức đăng nhập hiện tại</label>
        <input className="field-input" value={isPasswordAccount ? 'Email/Mật khẩu' : 'Google'} disabled />
      </div>

      {!isPasswordAccount ? (
        <p className="field-hint">
          Tài khoản này đăng nhập bằng Google nên mật khẩu được quản lý bởi Google.
          Vui lòng đổi mật khẩu tại{' '}
          <a href="https://myaccount.google.com/security" target="_blank" rel="noreferrer">
            myaccount.google.com/security
          </a>.
        </p>
      ) : (
        <form onSubmit={handleSubmit}>
          {banner && (
            <div className={`profile-banner profile-banner--${banner.type}`}>{banner.message}</div>
          )}

          <div className="field-group">
            <label className="field-label">Mật khẩu hiện tại</label>
            <input
              className="field-input"
              type="password"
              placeholder="••••••••"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
            />
            {fieldErrors.currentPassword && <span className="field-error">{fieldErrors.currentPassword}</span>}
          </div>

          <div className="field-row-2">
            <div className="field-group">
              <label className="field-label">Mật khẩu mới</label>
              <input
                className="field-input"
                type="password"
                placeholder="••••••••"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
              {fieldErrors.newPassword && <span className="field-error">{fieldErrors.newPassword}</span>}
            </div>
            <div className="field-group">
              <label className="field-label">Xác nhận mật khẩu mới</label>
              <input
                className="field-input"
                type="password"
                placeholder="••••••••"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
              {fieldErrors.confirmPassword && <span className="field-error">{fieldErrors.confirmPassword}</span>}
            </div>
          </div>

          <button className="btn btn--outline" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Đang xử lý...' : 'Đổi mật khẩu'}
          </button>
        </form>
      )}
    </div>
  );
}

function ProfileSidebar({ user }) {
  const [stats, setStats] = useState(null);
  const [statsError, setStatsError] = useState(null);

  useEffect(() => {
    let active = true;
    getMyStats()
      .then((data) => {
        if (active) setStats(data);
      })
      .catch((error) => {
        if (active) setStatsError(error.message || 'Không tải được thống kê.');
      });
    return () => {
      active = false;
    };
  }, []);

  const displayStatus = user?.is_active ? 'Đang hoạt động' : 'Ngừng hoạt động';
  const joinedAt = user?.created_at ? new Date(user.created_at).toLocaleDateString('vi-VN') : '—';

  return (
    <aside className="profile-side">
      <div className="card side-card">
        <h3>Trạng thái tài khoản</h3>
        <div className="status-row">
          <span className={`status-dot ${user?.is_active ? '' : 'status-dot--inactive'}`} />
          {displayStatus}
        </div>
        <ul className="info-list">
          <li>
            <span className="info-list-label">Vai trò</span>
            <span>{user?.role || '—'}</span>
          </li>
          <li>
            <span className="info-list-label">Ngày tham gia</span>
            <span>{joinedAt}</span>
          </li>
        </ul>
      </div>

      <div className="card side-card">
        <h3>Thống kê cá nhân</h3>
        {statsError && <p className="side-note">{statsError}</p>}
        {!statsError && !stats && <p className="side-note">Đang tải...</p>}
        {stats && (
          <ul className="info-list">
            <li>
              <span className="info-list-label">Tài liệu đã tải lên</span>
              <span>{stats.documents_count}</span>
            </li>
            <li>
              <span className="info-list-label">Câu hỏi đã tạo</span>
              <span>{stats.questions_count}</span>
            </li>
            <li>
              <span className="info-list-label">Câu hỏi chờ duyệt</span>
              <span>{stats.pending_questions_count}</span>
            </li>
          </ul>
        )}
      </div>
    </aside>
  );
}

function UserProfile() {
  const { user, updateUser } = useContext(AuthContext);
  const [activeTab, setActiveTab] = useState('info');

  const displayName = user?.display_name || 'Giảng viên';
  const displayEmail = user?.email || '';
  const displayRole = user?.role || 'Teacher';
  const avatarUrl = user?.profile?.avatar || buildFallbackAvatar(displayName);

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
          <div className="profile-main">
            <div className="profile-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'info'}
                className={`profile-tab ${activeTab === 'info' ? 'profile-tab--active' : ''}`}
                onClick={() => setActiveTab('info')}
              >
                Thông tin cá nhân
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'security'}
                className={`profile-tab ${activeTab === 'security' ? 'profile-tab--active' : ''}`}
                onClick={() => setActiveTab('security')}
              >
                Bảo mật
              </button>
            </div>

            {activeTab === 'info' ? (
              <InfoTab user={user} onProfileUpdated={updateUser} />
            ) : (
              <SecurityTab />
            )}
          </div>

          <ProfileSidebar user={user} />
        </div>
      </section>
    </main>
  );
}

export default UserProfile;
