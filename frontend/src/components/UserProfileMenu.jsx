import React, { useState, useRef, useEffect, useContext } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faUser,
  faCalendarCheck,
  faCog,
  faSignOutAlt,
  faChevronDown
} from '@fortawesome/free-solid-svg-icons';
import { AuthContext } from '../context/AuthContext';
import './UserProfileMenu.css';

const UserProfileMenu = () => {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef(null);
  const navigate = useNavigate();
  
  // Lấy dữ liệu user và hàm logout từ AuthContext
  const { user, logout } = useContext(AuthContext);

  // Xử lý đóng menu khi click ra ngoài
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogout = async () => {
    await logout();
    navigate('/dang-nhap'); // Chuyển hướng về đăng nhập
  };

  // Tránh lỗi render nếu trạng thái user chưa sẵn sàng
  if (!user) return null;

  // Trích xuất thông tin hiển thị (Dựa trên cấu trúc UserInfo trả về từ MongoDB)
  const roleLabel = {
    Admin: 'Quản trị viên',
    Teacher: 'Giảng viên',
    Reviewer: 'Người duyệt',
  };
  const displayName = user.display_name || 'Người dùng';
  const displayRole = roleLabel[user.role] || user.role || 'Người dùng';
  const canOpenSettings = user.role === 'Admin';
  
  // Tự động generate avatar dựa trên tên người dùng
  const avatarUrl = user.profile?.avatar || `https://ui-avatars.com/api/?name=${encodeURIComponent(displayName)}&background=0c78d4&color=fff`;

  return (
    <div className="user-menu-container" ref={menuRef}>
      <button 
        className={`user-menu-trigger ${isOpen ? 'active' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
      >
        <img src={avatarUrl} alt="Avatar" className="user-avatar" referrerPolicy="no-referrer" />
        <span className="user-name">{displayName}</span>
        <FontAwesomeIcon icon={faChevronDown} className="user-chevron" />
      </button>

      {isOpen && (
        <div className="user-dropdown">
          <div className="dropdown-header">
            <p className="dropdown-name">{displayName}</p>
            <p className="dropdown-role">{displayRole}</p>
          </div>
          
          <div className="dropdown-divider"></div>
          
          <Link to="/ho-so" className="dropdown-item" onClick={() => setIsOpen(false)}>
            <FontAwesomeIcon icon={faUser} className="dropdown-icon" />
            Hồ sơ cá nhân
          </Link>

          {['Admin', 'Teacher', 'Reviewer'].includes(user.role) && (
            <Link to="/lich-cong-viec" className="dropdown-item" onClick={() => setIsOpen(false)}>
              <FontAwesomeIcon icon={faCalendarCheck} className="dropdown-icon" />
              Lịch công việc
            </Link>
          )}

          {canOpenSettings && (
            <Link to="/quan-ly-nguoi-dung" className="dropdown-item" onClick={() => setIsOpen(false)}>
              <FontAwesomeIcon icon={faCog} className="dropdown-icon" />
              Quản lý người dùng
            </Link>
          )}
          
          <div className="dropdown-divider"></div>
          
          <button className="dropdown-item text-danger" onClick={handleLogout}>
            <FontAwesomeIcon icon={faSignOutAlt} className="dropdown-icon" />
            Đăng xuất
          </button>
        </div>
      )}
    </div>
  );
};

export default UserProfileMenu;
