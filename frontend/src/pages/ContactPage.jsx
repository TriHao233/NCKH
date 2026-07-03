import React from 'react';
import '../css/ContactPage.css';

function ContactPage() {
  return (
    <main className="contact-page">
      <section className="page-hero">
        <div className="container">
          <div className="page-hero-badge">Liên hệ</div>
          <h1 className="page-hero-title">Kết nối với nhóm nghiên cứu QBankCTU</h1>
          <p className="page-hero-desc">
            Mọi góp ý về đề tài, đề xuất hợp tác hoặc câu hỏi trong quá trình sử dụng hệ thống, vui lòng liên hệ
            qua thông tin bên dưới hoặc gửi biểu mẫu liên hệ.
          </p>
        </div>
      </section>

      <section className="contact-body">
        <div className="container contact-grid">
          {/* Left column: info cards */}
          <div className="contact-info">
            <div className="info-card">
              <span className="info-label">Đơn vị thực hiện</span>
              <h3>Trường Công nghệ Thông tin &amp; Truyền thông</h3>
              <p>Đại học Cần Thơ</p>
              <ul className="info-list">
                <li>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" /><circle cx="12" cy="10" r="3" /></svg>
                  Khu 2, đường 3/2, phường Xuân Khánh, quận Ninh Kiều, TP. Cần Thơ
                </li>
                <li>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" /></svg>
                  +84 0292 3831301
                </li>
                <li>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16v16H4z" opacity="0"/><path d="M22 6l-10 7L2 6" /><rect x="2" y="4" width="20" height="16" rx="2" /></svg>
                  webmaster@cit.ctu.edu.vn
                </li>
              </ul>
              <a href="https://www.ctu.edu.vn" target="_blank" rel="noreferrer" className="info-link">
                www.ctu.edu.vn →
              </a>
            </div>

            <div className="info-card">
              <span className="info-label">Chủ nhiệm đề tài</span>
              <h3>Trương Trí Hào</h3>
              <p>MSSV: B2203553 · Lớp Kỹ thuật phần mềm (CLC) · Khoá 48</p>
              <ul className="info-list">
                <li>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="4" width="20" height="16" rx="2" /><path d="M22 6l-10 7L2 6" /></svg>
                  haob2203553@student.ctu.edu.vn
                </li>
              </ul>
            </div>

            <div className="info-card info-card--muted">
              <span className="info-label">Cán bộ hướng dẫn</span>
              <h3>TS. Phan Phương Lan</h3>
              <p>Trường Công nghệ Thông tin và Truyền thông · Khoa học máy tính</p>
            </div>
          </div>

          {/* Right column: form */}
          <form className="contact-form" onSubmit={(e) => e.preventDefault()}>
            <h3 className="form-card-title">Gửi liên hệ</h3>
            <p className="form-card-sub">Điền thông tin bên dưới, nhóm nghiên cứu sẽ phản hồi sớm nhất có thể.</p>

            <div className="field-group">
              <label className="field-label">Họ và tên</label>
              <input className="field-input" placeholder="Nhập họ và tên" />
            </div>

            <div className="field-row-2">
              <div className="field-group">
                <label className="field-label">Email</label>
                <input className="field-input" type="email" placeholder="email@ctu.edu.vn" />
              </div>
              <div className="field-group">
                <label className="field-label">Vai trò</label>
                <select className="field-select" defaultValue="lecturer">
                  <option value="lecturer">Giảng viên</option>
                  <option value="student">Sinh viên</option>
                  <option value="other">Khác</option>
                </select>
              </div>
            </div>

            <div className="field-group">
              <label className="field-label">Nội dung</label>
              <textarea className="field-input" rows="5" placeholder="Nội dung liên hệ, góp ý hoặc câu hỏi..." />
            </div>

            <button className="btn btn--primary" type="submit">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
              Gửi liên hệ
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}

export default ContactPage;
