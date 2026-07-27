import React, { useContext } from 'react';
import { Link } from 'react-router-dom';
import { canAccessPath } from '../auth/permissions';
import { AuthContext } from '../context/AuthContext';
import './Footer.css';

const Footer = () => {
  const currentYear = new Date().getFullYear();
  const { user } = useContext(AuthContext);
  const role = user?.role;

  // Danh sách các liên kết điều hướng nội bộ
  const footerLinks = [
    { path: '/gioi-thieu', label: 'Giới thiệu' },
    { path: '/trang-chu', label: 'Trang chủ' },
    { path: '/sinh-cau-hoi', label: 'Sinh câu hỏi' },
    { path: '/quan-ly', label: 'Quản lý' },
    { path: '/huong-dan', label: 'Hướng dẫn' },
    { path: '/lien-he', label: 'Liên hệ' },
  ].filter((link) => !role ? canAccessPath(null, link.path) : canAccessPath(role, link.path));

  return (
    <footer className="footer">
      <div className="container">
        <div className="footer-grid">
          {/* Brand Column */}
          <div className="footer-brand">
            <div className="footer-logo-row">
              <img 
                src="https://www.ctu.edu.vn/images/upload/logo.png" 
                alt="Logo CTU" 
                className="footer-logo" 
              />
              <div>
                <div className="footer-name">QBankCTU</div>
                <div className="footer-name-sub">Đại Học Cần Thơ</div>
              </div>
            </div>
            <p className="footer-tagline">
              Hệ thống ngân hàng câu hỏi thông minh ứng dụng AI — phục vụ nghiên cứu và giảng dạy tại Đại học Cần Thơ.
            </p>
          </div>

          {/* Contact Column */}
          <div className="footer-col">
            <h4 className="footer-col-title">Trường CICT</h4>
            <p className="footer-col-text">
              Trường Công Nghệ Thông Tin &amp; Truyền Thông<br />
              Đại học Cần Thơ<br />
              Khu II, Đường 3/2, Xuân Khánh, Ninh Kiều, Cần Thơ
            </p>
            <a 
              href="https://www.ctu.edu.vn" 
              className="footer-link" 
              target="_blank" 
              rel="noopener noreferrer"
            >
              www.ctu.edu.vn
            </a>
          </div>

          {/* Navigation Column */}
          <div className="footer-col">
            <h4 className="footer-col-title">Điều hướng</h4>
            <ul className="footer-links">
              {footerLinks.map((link) => (
                <li key={link.path}>
                  <Link to={link.path} className="footer-link">
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Research Group Column */}
          <div className="footer-col">
            <h4 className="footer-col-title">Nhóm nghiên cứu</h4>
            <p className="footer-col-text">
              Đề tài Nghiên Cứu Khoa Học phát triển bởi sinh viên CICT
            </p>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="footer-bottom">
          <span>&copy; {currentYear} QBankCTU - Trường Công Nghệ Thông Tin &amp; Truyền Thông - Đại học Cần Thơ.</span>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
