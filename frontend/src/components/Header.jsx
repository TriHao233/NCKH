import React, { useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faBars,
  faBell,
  faCheckDouble,
  faChevronRight,
  faClipboardCheck,
  faClockRotateLeft,
  faFileCircleQuestion,
  faGaugeHigh,
  faGraduationCap,
  faLayerGroup,
  faListCheck,
  faPlug,
  faRightToBracket,
  faRobot,
  faShieldHalved,
  faUsers,
  faXmark,
} from '@fortawesome/free-solid-svg-icons';
import { AuthContext } from '../context/AuthContext';
import { canAccessPath } from '../auth/permissions';
import {
  getUnreadNotificationCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '../api/notifications';
import UserProfileMenu from './UserProfileMenu';
import './Header.css';

const ADMIN_NAV_SECTIONS = [
  {
    id: 'command',
    label: 'Điều hành',
    items: [
      { path: '/tong-quan', label: 'Tổng quan', icon: faGaugeHigh },
      { path: '/kiem-duyet', label: 'Hàng kiểm duyệt', icon: faClipboardCheck },
      { path: '/duyet-ai', label: 'Đánh giá AI', icon: faRobot },
    ],
  },
  {
    id: 'content',
    label: 'Nội dung',
    items: [
      { path: '/quan-ly', label: 'Ngân hàng câu hỏi', icon: faFileCircleQuestion },
      { path: '/lam-de-thi', label: 'Đề thi', icon: faGraduationCap },
      { path: '/danh-muc', label: 'Danh mục', icon: faLayerGroup },
    ],
  },
  {
    id: 'system',
    label: 'Hệ thống',
    items: [
      { path: '/quan-ly-nguoi-dung', label: 'Người dùng', icon: faUsers },
      { path: '/quan-ly-job', label: 'Tác vụ', icon: faListCheck },
      { path: '/quan-ly-moodle', label: 'Moodle', icon: faPlug },
      { path: '/nhat-ky-he-thong', label: 'Nhật ký', icon: faClockRotateLeft },
    ],
  },
];

const PUBLIC_NAV_GROUPS = [
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
    items: [
      { path: '/sinh-cau-hoi', label: 'Sinh câu hỏi' },
      { path: '/quan-ly', label: 'Quản lý câu hỏi' },
      { path: '/lam-de-thi', label: 'Làm đề thi' },
    ],
  },
  {
    id: 'reviewer',
    label: 'Người duyệt',
    items: [
      { path: '/kiem-duyet', label: 'Hàng kiểm duyệt' },
    ],
  },
  {
    id: 'admin',
    label: 'Quản trị',
    items: ADMIN_NAV_SECTIONS.flatMap((section) => section.items),
  },
];

function isPathActive(pathname, path) {
  return pathname === path || pathname.startsWith(`${path}/`);
}

const Header = ({ adminShell = false }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const navMenuRef = useRef(null);
  const notificationRef = useRef(null);
  const { user, loading } = useContext(AuthContext);
  const role = user?.role;
  const signedIn = Boolean(user);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [notificationLoading, setNotificationLoading] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [adminMenuOpen, setAdminMenuOpen] = useState(false);

  const refreshUnreadCount = async () => {
    if (!signedIn) return;
    try {
      const result = await getUnreadNotificationCount();
      setUnreadCount(result.unread_count || 0);
    } catch {
      setUnreadCount(0);
    }
  };

  const loadNotifications = async () => {
    if (!signedIn) return;
    setNotificationLoading(true);
    try {
      const result = await listNotifications({ page: 1, pageSize: 8 });
      setNotifications(result.items || []);
    } catch {
      setNotifications([]);
    } finally {
      setNotificationLoading(false);
    }
  };

  useEffect(() => {
    if (!signedIn) {
      setUnreadCount(0);
      setNotifications([]);
      setNotificationOpen(false);
      return undefined;
    }
    refreshUnreadCount();
    const intervalId = window.setInterval(refreshUnreadCount, 60000);
    return () => window.clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signedIn, user?.id]);

  useEffect(() => {
    if (!notificationOpen) return undefined;
    const handleClick = (event) => {
      if (notificationRef.current && !notificationRef.current.contains(event.target)) {
        setNotificationOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [notificationOpen]);

  useEffect(() => {
    setAdminMenuOpen(false);
  }, [location.pathname]);

  const toggleNotifications = async () => {
    const nextOpen = !notificationOpen;
    setNotificationOpen(nextOpen);
    if (nextOpen) {
      await loadNotifications();
      await refreshUnreadCount();
    }
  };

  const openNotification = async (notification) => {
    if (!notification.is_read) {
      try {
        await markNotificationRead(notification.id);
        setUnreadCount((current) => Math.max(0, current - 1));
      } catch {
        // Deep-link navigation remains available if read-state synchronization fails.
      }
    }
    setNotificationOpen(false);
    if (notification.link) {
      navigate(notification.link);
    }
  };

  const markAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setUnreadCount(0);
      setNotifications((current) => current.map((item) => ({ ...item, is_read: true })));
    } catch {
      // Preserve the current state when the API cannot update it.
    }
  };

  const visibleAdminSections = useMemo(
    () => ADMIN_NAV_SECTIONS
      .map((section) => ({
        ...section,
        items: section.items.filter((item) => canAccessPath(user, item.path)),
      }))
      .filter((section) => section.items.length > 0),
    [user],
  );

  const visibleNavGroups = PUBLIC_NAV_GROUPS
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => !role || canAccessPath(user, item.path)),
    }))
    .filter((group) => {
      if (role === 'Admin' && group.id === 'public') return false;
      return group.id === 'public' || (signedIn && group.items.length > 0);
    });
  const showSectionLabels = signedIn && visibleNavGroups.length > 1;

  const activeAdminPage = useMemo(
    () => ADMIN_NAV_SECTIONS
      .flatMap((section) => section.items)
      .find((item) => isPathActive(location.pathname, item.path)),
    [location.pathname],
  );

  useEffect(() => {
    const activeLink = navMenuRef.current?.querySelector(
      '.nav-link--active, .admin-nav-link--active',
    );
    activeLink?.scrollIntoView({ block: 'nearest', inline: 'center' });
  }, [location.pathname, role, signedIn]);

  const notificationMenu = user ? (
    <div className="notification-menu" ref={notificationRef}>
      <button
        type="button"
        className={`notification-button ${unreadCount > 0 ? 'notification-button--unread' : ''}`}
        onClick={toggleNotifications}
        aria-label="Thông báo"
        aria-expanded={notificationOpen}
      >
        <FontAwesomeIcon icon={faBell} />
        {unreadCount > 0 && (
          <span className="notification-count">{unreadCount > 9 ? '9+' : unreadCount}</span>
        )}
      </button>
      {notificationOpen && (
        <div className="notification-panel">
          <div className="notification-panel__head">
            <b>Thông báo</b>
            <button type="button" onClick={markAllRead} disabled={unreadCount === 0}>
              <FontAwesomeIcon icon={faCheckDouble} />
              Đã đọc
            </button>
          </div>
          <div className="notification-list">
            {notificationLoading ? (
              <p>Đang tải thông báo...</p>
            ) : notifications.length > 0 ? (
              notifications.map((notification) => (
                <button
                  type="button"
                  className={`notification-item ${notification.is_read ? '' : 'notification-item--unread'}`}
                  key={notification.id}
                  onClick={() => openNotification(notification)}
                >
                  <span>{notification.title}</span>
                  <small>{notification.body || notification.entity?.question_code || 'Xem chi tiết'}</small>
                </button>
              ))
            ) : (
              <p>Chưa có thông báo.</p>
            )}
          </div>
        </div>
      )}
    </div>
  ) : null;

  if (adminShell) {
    return (
      <>
        {adminMenuOpen && (
          <button
            type="button"
            className="admin-shell-backdrop admin-shell-backdrop--visible"
            onClick={() => setAdminMenuOpen(false)}
            aria-label="Đóng điều hướng quản trị"
          />
        )}

        <aside
          id="admin-sidebar-navigation"
          className={`admin-sidebar ${adminMenuOpen ? 'admin-sidebar--open' : ''}`}
          aria-label="Điều hướng quản trị"
        >
          <div className="admin-sidebar__brand">
            <Link to="/tong-quan" className="admin-sidebar__brand-link">
              <span className="admin-sidebar__logo">
                <img
                  src="https://www.ctu.edu.vn/images/upload/logo.png"
                  alt=""
                />
              </span>
              <span>
                <strong>QBankCTU</strong>
                <small>QUẢN TRỊ</small>
              </span>
            </Link>
            <button
              type="button"
              className="admin-sidebar__close"
              onClick={() => setAdminMenuOpen(false)}
              aria-label="Đóng menu"
            >
              <FontAwesomeIcon icon={faXmark} />
            </button>
          </div>

          <div className="admin-sidebar__context">
            <FontAwesomeIcon icon={faShieldHalved} />
            <div>
              <span>Quản trị</span>
              <small>Vận hành hệ thống</small>
            </div>
          </div>

          <nav className="admin-sidebar__nav" ref={navMenuRef}>
            {visibleAdminSections.map((section) => (
              <section className="admin-nav-section" key={section.id}>
                <h2>{section.label}</h2>
                <div className="admin-nav-section__links">
                  {section.items.map((item) => {
                    const active = isPathActive(location.pathname, item.path);
                    return (
                      <Link
                        to={item.path}
                        className={`admin-nav-link ${active ? 'admin-nav-link--active' : ''}`}
                        key={item.path}
                        aria-current={active ? 'page' : undefined}
                      >
                        <FontAwesomeIcon icon={item.icon} />
                        <span>{item.label}</span>
                        <FontAwesomeIcon className="admin-nav-link__arrow" icon={faChevronRight} />
                      </Link>
                    );
                  })}
                </div>
              </section>
            ))}
          </nav>

          <div className="admin-sidebar__footer">
            <span className="admin-sidebar__status-dot" />
            <div>
              <b>Hệ thống ổn định</b>
              <small>Phiên được bảo vệ</small>
            </div>
          </div>
        </aside>

        <header className="admin-topbar">
          <div className="admin-topbar__title">
            <button
              type="button"
              className="admin-topbar__menu"
              onClick={() => setAdminMenuOpen((current) => !current)}
              aria-label="Mở điều hướng quản trị"
              aria-controls="admin-sidebar-navigation"
              aria-expanded={adminMenuOpen}
            >
              <FontAwesomeIcon icon={faBars} />
            </button>
            <div>
              <span>QBankCTU / Quản trị</span>
              <strong>{activeAdminPage?.label || 'Không gian quản trị'}</strong>
            </div>
          </div>
          <div className="admin-topbar__actions">
            <span className="admin-topbar__environment">
              <i />
              Nội bộ
            </span>
            {notificationMenu}
            <UserProfileMenu />
          </div>
        </header>
      </>
    );
  }

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
            <span className="nav-subtitle">Đại học Cần Thơ</span>
          </div>
        </div>

        <nav className="nav-menu" aria-label="Điều hướng chính" ref={navMenuRef}>
          {visibleNavGroups.map((group) => (
            <div key={group.id} className={`nav-section nav-section--${group.id}`}>
              {showSectionLabels && <span className="nav-section-label">{group.label}</span>}
              <div className="nav-section-links">
                {group.items.map((link) => {
                  const active = isPathActive(location.pathname, link.path);
                  return (
                    <Link
                      key={link.path}
                      to={link.path}
                      className={`nav-link ${active ? 'nav-link--active' : ''}`}
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
          {user ? (
            <>
              {notificationMenu}
              <UserProfileMenu />
            </>
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
