/**
 * Hero của khu làm việc Người duyệt/Quản trị, cùng cấu trúc với trang Giảng viên:
 * badge, tiêu đề, mô tả ngắn bên trái; nút hành động bên phải; phần chân tuỳ chọn (tabs).
 */
function WorkspaceHero({ lead, badge, title, description, actions, children }) {
  return (
    <section className="page-hero">
      <div className="container">
        {lead}
        <div className="ws-hero-row">
          <div>
            {badge && <div className="page-hero-badge">{badge}</div>}
            <h1 className="page-hero-title">{title}</h1>
            {description && <p className="page-hero-desc">{description}</p>}
          </div>
          {actions && <div className="ws-hero-actions">{actions}</div>}
        </div>
        {children && <div className="ws-hero-foot">{children}</div>}
      </div>
    </section>
  );
}

export default WorkspaceHero;
