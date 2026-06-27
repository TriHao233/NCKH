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
  const { user } = useContext(AuthContext);

  const navLinks = [
    { path: '/gioi-thieu', label: 'Giới thiệu' },
    { path: '/trang-chu', label: 'Trang Chủ' },
    { path: '/sinh-cau-hoi', label: 'Sinh Câu Hỏi' },
    { path: '/quan-ly', label: 'Quản Lý' },
    { path: '/huong-dan', label: 'Hướng Dẫn' },
    { path: '/lien-he', label: 'Liên Hệ' },
  ];

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
          {navLinks.map((link) => {
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
        </nav>

        <div className="nav-actions">
          {/* Kiểm tra user từ Context để render nút Đăng nhập hoặc Menu User */}
          {user ? (
            <UserProfileMenu />
          ) : (
            <Link to="/dang-nhap" className="btn btn--login">
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