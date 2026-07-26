import React, { useContext } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faRightToBracket } from '@fortawesome/free-solid-svg-icons';
import { AuthContext } from '../context/AuthContext';
import UserProfileMenu from './UserProfileMenu'; 
import './Header.css';

const Header = () => {
  const location = useLocation();
  
  // Lấy trạng thái user từ AuthContext thay vì tự check localStorage
  const { user, loading } = useContext(AuthContext);
  const role = user?.role;
  const signedIn = Boolean(user);

  const navGroups = [
    {
      id: 'public',
      label: 'Chung',
      items: [
        { path: '/gioi-thieu', label: 'Giới thiệu' },
        { path: '/trang-chu', label: 'Trang chủ' },
        { path: '/huong-dan', label: 'Hướng dẫn' },
        { path: '/lien-he', label: 'Liên hệ' },
      ],
    },
    {
      id: 'teacher',
      label: 'Giảng viên',
      roles: ['Teacher'],
      items: [
        { path: '/sinh-cau-hoi', label: 'Sinh câu hỏi' },
        { path: '/quan-ly', label: 'Quản lý câu hỏi' },
        { path: '/lam-de-thi', label: 'Làm đề thi' },
      ],
    },
    {
      id: 'reviewer',
      label: 'Người duyệt',
      roles: ['Reviewer'],
      items: [
        { path: '/kiem-duyet', label: 'Hàng kiểm duyệt' },
      ],
    },
    {
      id: 'admin',
      label: 'Quản trị',
      roles: ['Admin'],
      items: [
        { path: '/danh-muc', label: 'Danh mục' },
        { path: '/quan-ly-nguoi-dung', label: 'Người dùng' },
      ],
    },
  ];
  const visibleNavGroups = navGroups.filter((group) => {
    if (!group.roles) return true;
    if (!signedIn) return false;
    return group.roles.includes(role);
  });
  const showSectionLabels = signedIn && visibleNavGroups.length > 1;

  return (
    <header className="navbar" id="navbar">
      <div className="nav-container">
        <div className="nav-brand">
          <Link to="/" className="nav-brand-link">
            <img 
              src="https://www.ctu.edu.vn/images/upload/logo.png" 
              alt="Logo Đại học Cần Thơ" 
              className="nav-logo" 
            />
          </Link>
          <div className="nav-title-group">
            <span className="nav-title">QBankCTU</span>
            <span className="nav-subtitle">Đại Học Cần Thơ</span>
          </div>
        </div>

        <nav className="nav-menu" aria-label="Điều hướng chính">
          {visibleNavGroups.map((group) => (
            <div
              key={group.id}
              className={`nav-section nav-section--${group.id}`}
            >
              {showSectionLabels && <span className="nav-section-label">{group.label}</span>}
              <div className="nav-section-links">
                {group.items.map((link) => {
                  const isActive = location.pathname === link.path;
                  return (
                    <Link
                      key={link.path}
                      to={link.path}
                      className={`nav-link ${isActive ? 'nav-link--active' : ''}`}
                    >
                      {link.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="nav-actions">
          {/* Kiểm tra user từ Context để render nút Đăng nhập hoặc Menu User */}
          {user ? (
            <UserProfileMenu />
          ) : (
            <Link
              to="/dang-nhap"
              className={`btn btn--login ${loading ? 'btn--login-pending' : ''}`}
              aria-busy={loading}
            >
              <FontAwesomeIcon icon={faRightToBracket} className="btn-icon" />
              <span>Đăng nhập</span>
            </Link>
          )}
        </div>
      </div>
    </header>
  );
};

export default Header;
