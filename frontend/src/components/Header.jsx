import React, { useContext, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faBars, faBell, faCheckDouble, faRightToBracket, faXmark,
  faCircleInfo, faHouse, faWandMagicSparkles, faFilePen, faBookOpen,
  faEnvelope, faClipboardCheck, faChartLine, faLayerGroup, faUsers,
  faClockRotateLeft, faListCheck, faGraduationCap, faCircleQuestion,
  faRobot, faChevronDown, faDatabase, faGear, faFileLines, faCalendarCheck,
} from '@fortawesome/free-solid-svg-icons';
import { AuthContext } from '../context/AuthContext';
import { canAccessPath, hasEffectivePermission } from '../auth/permissions';
import {
  getUnreadNotificationCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '../api/notifications';
import UserProfileMenu from './UserProfileMenu'; 
import './Header.css';

const navIcons = {
  'Giới thiệu': faCircleInfo,
  'Trang chủ': faHouse,
  'Sinh câu hỏi': faWandMagicSparkles,
  'Làm đề thi': faFilePen,
  'Đề thi': faFilePen,
  'Hướng dẫn': faBookOpen,
  'Liên hệ': faEnvelope,
  'Hàng kiểm duyệt': faClipboardCheck,
  'Kiểm duyệt': faClipboardCheck,
  'Lịch công việc': faCalendarCheck,
  'Tổng quan': faChartLine,
  'Ngân hàng': faDatabase,
  'Tài liệu': faFileLines,
  'Người dùng': faUsers,
  'Tài khoản': faUsers,
  'Hệ thống': faGear,
  'Cấu hình': faLayerGroup,
  'Tác vụ hệ thống': faListCheck,
  'Nhật ký hệ thống': faClockRotateLeft,
  'Moodle': faGraduationCap,
  'Câu hỏi': faCircleQuestion,
  'Thẩm định AI': faRobot,
};

const Header = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const navMenuRef = useRef(null);
  const notificationRef = useRef(null);
  
  // Lấy trạng thái user từ AuthContext thay vì tự check localStorage
  const { user, loading } = useContext(AuthContext);
  const role = user?.role;
  const signedIn = Boolean(user) && !loading;
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [openNavGroup, setOpenNavGroup] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [notificationLoading, setNotificationLoading] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

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
        // Opening the deep link should not be blocked by read-state sync.
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
      // Keep the current unread state if the API fails.
    }
  };

  const navGroups = [
    {
      id: 'public',
      label: 'Chung',
      items: [
        { path: '/gioi-thieu', label: 'Giới thiệu' },
        { path: '/trang-chu', label: 'Trang chủ' },
      ],
    },
    {
      id: 'teacher',
      label: 'Giảng viên',
      items: [
        { path: '/sinh-cau-hoi', label: 'Sinh câu hỏi' },
        { path: '/lam-de-thi', label: 'Làm đề thi' },
      ],
    },
    {
      id: 'support',
      label: 'Hỗ trợ',
      isPublic: true,
      items: [
        { path: '/huong-dan', label: 'Hướng dẫn' },
        { path: '/lien-he', label: 'Liên hệ' },
      ],
    },
    {
      id: 'reviewer',
      label: 'Người duyệt',
      items: [
        { path: '/kiem-duyet', label: 'Hàng kiểm duyệt', requires: 'reviews.manage' },
      ],
    },
  ];
  // Menu Quản trị: 5 nhóm theo tần suất dùng; nhóm nhiều mục mở thành menu thả xuống.
  const adminNavGroups = [
    {
      id: 'overview',
      label: 'Tổng quan',
      items: [{ path: '/tong-quan', label: 'Tổng quan' }],
    },
    {
      id: 'review',
      label: 'Kiểm duyệt',
      items: [
        { path: '/kiem-duyet', label: 'Hàng kiểm duyệt' },
        { path: '/duyet-ai', label: 'Thẩm định AI' },
        { path: '/lich-cong-viec', label: 'Lịch công việc' },
      ],
    },
    {
      id: 'bank',
      label: 'Ngân hàng',
      items: [
        { path: '/quan-ly', label: 'Câu hỏi' },
        { path: '/lam-de-thi', label: 'Đề thi' },
        { path: '/quan-ly-tai-lieu', label: 'Tài liệu' },
      ],
    },
    {
      id: 'people',
      label: 'Người dùng',
      items: [
        { path: '/quan-ly-nguoi-dung', label: 'Tài khoản' },
        { path: '/lien-he', label: 'Liên hệ' },
      ],
    },
    {
      id: 'system',
      label: 'Hệ thống',
      items: [
        { path: '/danh-muc', label: 'Cấu hình' },
        { path: '/quan-ly-moodle', label: 'Moodle' },
        { path: '/quan-ly-job', label: 'Tác vụ hệ thống' },
        { path: '/nhat-ky-he-thong', label: 'Nhật ký hệ thống' },
      ],
    },
  ];
  const roleNavGroups = role === 'Admin' ? adminNavGroups : navGroups;
  const visibleNavGroups = roleNavGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => (!role || canAccessPath(user, item.path)) && (!item.requires || hasEffectivePermission(user, item.requires))),
    }))
    .filter((group) => {
      if (!signedIn) return ['public', 'teacher', 'support'].includes(group.id);
      if (role === 'Admin' && group.id === 'public') return false;
      return group.isPublic || group.id === 'public' || (signedIn && group.items.length > 0);
    });
  const showSectionLabels = signedIn && visibleNavGroups.length > 1;
  const isPathActive = (path) => location.pathname === path
    || location.pathname.startsWith(`${path}/`);

  useEffect(() => {
    const activeLink = navMenuRef.current?.querySelector('.nav-link--active');
    activeLink?.scrollIntoView({ block: 'nearest', inline: 'center' });
    setMobileNavOpen(false);
    setOpenNavGroup(null);
  }, [location.pathname, role, signedIn]);

  useEffect(() => {
    if (!openNavGroup) return undefined;
    const handleClick = (event) => {
      if (navMenuRef.current && !navMenuRef.current.contains(event.target)) setOpenNavGroup(null);
    };
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') setOpenNavGroup(null);
    };
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [openNavGroup]);

  useEffect(() => {
    if (!mobileNavOpen) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') setMobileNavOpen(false);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [mobileNavOpen]);

  return (
    <header
      className={`navbar ${role === 'Admin' ? 'navbar--admin' : ''}`}
      id="navbar"
      style={{ '--header-background': `url("${import.meta.env.BASE_URL}images/header-background.png")` }}
    >
      <div className="nav-container">
        <div className="nav-brand">
          <Link to="/" className="nav-brand-link">
            <img 
              src={`${import.meta.env.BASE_URL}images/qbankctu-header-logo.png`}
              alt="QBankCTU - Đại học Cần Thơ"
              className="nav-logo" 
            />
          </Link>
        </div>

        <nav className="nav-menu" aria-label="Điều hướng chính" ref={navMenuRef}>
          {visibleNavGroups.map((group) => (role === 'Admin' && group.items.length > 1 ? (
            <div key={group.id} className={`nav-section nav-section--${group.id} nav-dropdown`}>
              <button
                type="button"
                className={`nav-link nav-dropdown-toggle ${group.items.some((link) => isPathActive(link.path)) ? 'nav-link--active' : ''}`}
                aria-haspopup="true"
                aria-expanded={openNavGroup === group.id}
                aria-controls={openNavGroup === group.id ? `nav-dropdown-${group.id}` : undefined}
                onClick={() => setOpenNavGroup((current) => (current === group.id ? null : group.id))}
              >
                <FontAwesomeIcon icon={navIcons[group.label]} className="nav-link-icon" aria-hidden="true" />
                <span>{group.label}</span>
                <FontAwesomeIcon icon={faChevronDown} className="nav-dropdown-chevron" aria-hidden="true" />
              </button>
              {openNavGroup === group.id && (
                <div className="nav-dropdown-panel" id={`nav-dropdown-${group.id}`}>
                  {group.items.map((link) => (
                    <Link
                      key={link.path}
                      to={link.path}
                      className={`nav-dropdown-link ${isPathActive(link.path) ? 'nav-dropdown-link--active' : ''}`}
                      aria-current={isPathActive(link.path) ? 'page' : undefined}
                      onClick={() => setOpenNavGroup(null)}
                    >
                      <FontAwesomeIcon icon={navIcons[link.label]} className="nav-link-icon" aria-hidden="true" />
                      <span>{link.label}</span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div
              key={group.id}
              className={`nav-section nav-section--${group.id}`}
            >
              {showSectionLabels && <span className="nav-section-label">{group.label}</span>}
              <div className="nav-section-links">
                {group.items.map((link) => {
                  const isActive = isPathActive(link.path);
                  return (
                    <Link
                      key={link.path}
                      to={link.path}
                      className={`nav-link ${isActive ? 'nav-link--active' : ''}`}
                      title={!signedIn && !canAccessPath(null, link.path) ? 'Đăng nhập để sử dụng chức năng này' : undefined}
                    >
                      <FontAwesomeIcon icon={navIcons[link.label]} className="nav-link-icon" aria-hidden="true" />
                      <span>{link.label}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          )))}
        </nav>

        <div className="nav-actions">
          {/* Kiểm tra user từ Context để render nút Đăng nhập hoặc Menu User */}
          {user ? (
            <>
              <div className="notification-menu" ref={notificationRef}>
                <button
                  type="button"
                  className={`notification-button ${unreadCount > 0 ? 'notification-button--unread' : ''}`}
                  onClick={toggleNotifications}
                  aria-label={unreadCount > 0 ? `Thông báo: ${unreadCount} chưa đọc` : 'Thông báo'}
                  aria-expanded={notificationOpen}
                  aria-busy={notificationLoading}
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
              <UserProfileMenu />
            </>
          ) : (
            <Link
              to="/dang-nhap"
              className={`btn btn--login ${loading ? 'btn--login-pending' : ''}`}
              aria-label="Đăng nhập"
              aria-busy={loading}
            >
              <FontAwesomeIcon icon={faRightToBracket} className="btn-icon" />
              <span>Đăng nhập</span>
            </Link>
          )}
          <button
            type="button"
            className="mobile-nav-toggle"
            aria-label={mobileNavOpen ? 'Đóng menu điều hướng' : 'Mở menu điều hướng'}
            aria-expanded={mobileNavOpen}
            aria-controls="mobile-navigation"
            onClick={() => setMobileNavOpen((current) => !current)}
          >
            <FontAwesomeIcon icon={mobileNavOpen ? faXmark : faBars} />
          </button>
        </div>
      </div>

      {mobileNavOpen && (
        <div className="mobile-nav-backdrop" onClick={() => setMobileNavOpen(false)}>
          <nav
            className="mobile-nav-panel"
            id="mobile-navigation"
            aria-label="Điều hướng di động"
            onClick={(event) => event.stopPropagation()}
          >
            {visibleNavGroups.map((group) => (
              <section className="mobile-nav-section" key={group.id}>
                {!(role === 'Admin' && group.items.length === 1) && (
                  <span className="mobile-nav-section-label">{group.label}</span>
                )}
                <div className="mobile-nav-links">
                  {group.items.map((link) => {
                    const isActive = isPathActive(link.path);
                    return (
                      <Link
                        key={link.path}
                        to={link.path}
                        className={`mobile-nav-link ${isActive ? 'mobile-nav-link--active' : ''}`}
                        title={!signedIn && !canAccessPath(null, link.path) ? 'Đăng nhập để sử dụng chức năng này' : undefined}
                        onClick={() => setMobileNavOpen(false)}
                      >
                        <FontAwesomeIcon icon={navIcons[link.label]} className="nav-link-icon" aria-hidden="true" />
                        <span>{link.label}</span>
                      </Link>
                    );
                  })}
                </div>
              </section>
            ))}
          </nav>
        </div>
      )}
    </header>
  );
};

export default Header;
