import React from 'react';
import { Link } from 'react-router-dom';
import '../css/AboutPage.css';

const team = [
  {
    name: 'Trương Trí Hào',
    role: 'Chủ nhiệm đề tài',
    tasks: 'Quản lý chung, điều phối tiến độ · Nghiên cứu, huấn luyện và tối ưu mô hình LLM · Tích hợp Core AI vào Backend',
  },
  {
    name: 'Trần Hải Thiên',
    role: 'Thành viên nghiên cứu',
    tasks: 'Phối hợp nghiên cứu kỹ thuật RAG và xử lý tài liệu · Hỗ trợ lập trình giao diện Admin Dashboard · Soạn thảo tài liệu kỹ thuật',
  },
  {
    name: 'Tiêu Lê Gia Linh',
    role: 'Thành viên nghiên cứu',
    tasks: 'Thiết kế UI/UX cho hệ thống quản trị · Lập trình giao diện chỉnh sửa câu hỏi (Question Editor) · Kiểm thử trải nghiệm người dùng',
  },
  {
    name: 'Vương Phan Quốc Cường',
    role: 'Thành viên nghiên cứu',
    tasks: 'Thiết kế cơ sở dữ liệu · Nghiên cứu tích hợp Moodle · Lập trình module tích hợp vào Moodle',
  },
  {
    name: 'Lê Trọng Thiện',
    role: 'Thành viên nghiên cứu',
    tasks: 'Xây dựng kiến trúc hệ thống, API Gateway · Phát triển module bảo mật (Auth/Roles) · Lập trình API quản lý (CRUD) cho Backend',
  },
];

const advisors = [
  {
    name: 'TS. Phan Phương Lan',
    unit: 'Trường Công nghệ Thông tin và Truyền thông · Khoa học máy tính',
    task: 'Hướng dẫn nội dung khoa học và hướng dẫn lập dự toán kinh phí đề tài',
  },
  {
    name: 'KS. Trương Phúc Vĩnh',
    unit: 'Trường Công nghệ Thông tin và Truyền thông · Kỹ thuật phần mềm',
    task: 'Hướng dẫn nội dung kỹ thuật',
  },
];

const scope = [
  {
    title: 'Phạm vi dữ liệu',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
      </svg>
    ),
    items: ['Tài liệu văn bản kỹ thuật số (PDF, DOC)', 'Ngôn ngữ tiếng Việt', 'Trọng tâm học phần Cấu trúc dữ liệu', 'Giáo trình, bài giảng, đề cương chi tiết'],
  },
  {
    title: 'Loại câu hỏi hỗ trợ',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M9 21V9" />
      </svg>
    ),
    items: ['Trắc nghiệm 4 lựa chọn (MCQ)', 'Đúng / Sai (True–False)', 'Điền khuyết (Fill-in-the-blank)', 'Ghép đôi & Câu hỏi tình huống'],
  },
  {
    title: 'Công nghệ cốt lõi',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" /><path d="M8 14s1.5 2 4 2 4-2 4-2" /><line x1="9" y1="9" x2="9.01" y2="9" /><line x1="15" y1="9" x2="15.01" y2="9" />
      </svg>
    ),
    items: ['Mô hình ngôn ngữ lớn mã nguồn mở, chạy local', 'Kỹ thuật RAG truy xuất ngữ cảnh từ tài liệu', 'Plugin đồng bộ trực tiếp vào Moodle'],
  },
];

const objectives = [
  {
    title: 'Nền tảng quản lý tập trung',
    desc: 'Số hóa, lưu trữ và tổ chức dữ liệu câu hỏi – đề thi một cách hệ thống, thuận lợi cho việc truy xuất và tái sử dụng.',
  },
  {
    title: 'Tự động hoá & tiết kiệm thời gian',
    desc: 'Ứng dụng LLM kết hợp kỹ thuật RAG để trích xuất kiến thức từ tài liệu, tạo bộ câu hỏi đa dạng nhanh hơn phương pháp thủ công.',
  },
  {
    title: 'Đảm bảo chất lượng nội dung',
    desc: 'Kiểm soát chất lượng theo mô hình "Con người trong vòng lặp" — AI khởi tạo, giảng viên thẩm định và phê duyệt cuối cùng.',
  },
  {
    title: 'Tương thích & liên kết hệ thống',
    desc: 'Xây dựng cơ chế chuyển đổi, đồng bộ dữ liệu câu hỏi từ hệ thống sang Ngân hàng câu hỏi của Moodle.',
  },
];

function AboutPage() {
  return (
    <main className="about-page">
      <section className="page-hero">
        <div className="container">
          <div className="page-hero-badge">Đề tài nghiên cứu khoa học cấp cơ sở · CICT – ĐHCT</div>
          <h1 className="page-hero-title">Giới thiệu về QBankCTU</h1>
          <p className="page-hero-desc">
            Nghiên cứu và xây dựng ứng dụng Web quản lý ngân hàng câu hỏi phục vụ giảng dạy và kiểm tra – đánh giá,
            khai thác khả năng của mô hình ngôn ngữ lớn (LLMs) để hỗ trợ sinh câu hỏi tự động từ tài liệu, đồng thời
            đảm bảo quy trình quản lý và kiểm duyệt chặt chẽ trước khi đưa câu hỏi vào sử dụng chính thức.
          </p>
        </div>
      </section>

      <section className="urgency">
        <div className="container urgency-grid">
          <div className="urgency-text">
            <div className="section-badge">Tính cấp thiết</div>
            <h2 className="section-title">Vì sao cần một hệ thống như vậy?</h2>
            <p>
              Quy trình xây dựng ngân hàng câu hỏi tại nhiều cơ sở giáo dục hiện vẫn thực hiện thủ công, tốn kém
              nguồn lực và dễ dẫn đến chất lượng không đồng đều giữa các câu hỏi. Sự phát triển của các mô hình
              ngôn ngữ lớn mở ra cơ hội tự động hoá khâu này, nhưng cũng đặt ra thách thức về độ tin cậy do hiện
              tượng "ảo giác" (hallucination) của AI.
            </p>
            <p>
              QBankCTU được xây dựng để giải quyết đồng thời hai bài toán: khai thác tốc độ của AI để gợi ý câu hỏi,
              và cung cấp công cụ cho giảng viên kiểm duyệt, hiệu chỉnh, chuẩn hoá nội dung trước khi công bố.
            </p>
          </div>
          <div className="urgency-points">
            <div className="up-item">
              <span className="up-label">Vấn đề</span>
              <p>Biên soạn câu hỏi thủ công tốn thời gian, độ phủ kiến thức và mức tư duy dễ bị lệch.</p>
            </div>
            <div className="up-item">
              <span className="up-label">Rủi ro</span>
              <p>AI tạo sinh có thể gây "ảo giác" — sinh nội dung sai nhưng nghe có vẻ thuyết phục.</p>
            </div>
            <div className="up-item up-item--accent">
              <span className="up-label">Giải pháp</span>
              <p>Kết hợp kỹ thuật RAG và quy trình Human-in-the-loop để vừa tăng tốc, vừa đảm bảo kiểm soát.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="objectives">
        <div className="container">
          <div className="section-header">
            <div className="section-badge">Mục tiêu đề tài</div>
            <h2 className="section-title">Bốn mục tiêu cụ thể</h2>
            <p className="section-desc">Định hướng phát triển hệ thống từ nghiên cứu lý thuyết đến ứng dụng thực tiễn.</p>
          </div>
          <div className="objectives-grid">
            {objectives.map((o, i) => (
              <div className="objective-card" key={o.title}>
                <span className="objective-num">{String(i + 1).padStart(2, '0')}</span>
                <h3>{o.title}</h3>
                <p>{o.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="scope">
        <div className="container">
          <div className="section-header">
            <div className="section-badge">Đối tượng &amp; phạm vi</div>
            <h2 className="section-title">Phạm vi nghiên cứu của đề tài</h2>
          </div>
          <div className="scope-grid">
            {scope.map((s) => (
              <div className="scope-card" key={s.title}>
                <div className="scope-icon">{s.icon}</div>
                <h3>{s.title}</h3>
                <ul>
                  {s.items.map((it) => (
                    <li key={it}>{it}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="team">
        <div className="container">
          <div className="section-header">
            <div className="section-badge">Nhóm thực hiện</div>
            <h2 className="section-title">Sinh viên Trường Công nghệ Thông tin &amp; Truyền thông</h2>
            <p className="section-desc">Khoá 48 · Ngành Kỹ thuật phần mềm (CLC)</p>
          </div>
          <div className="team-grid">
            {team.map((m) => (
              <div className="team-card" key={m.name}>
                <div className="team-avatar">{m.name.split(' ').slice(-1)[0][0]}</div>
                <h3>{m.name}</h3>
                <span className="team-role">{m.role}</span>
                <p>{m.tasks}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="advisors">
        <div className="container">
          <div className="section-header">
            <div className="section-badge">Cán bộ hướng dẫn</div>
            <h2 className="section-title">Đồng hành cùng nhóm nghiên cứu</h2>
          </div>
          <div className="advisors-grid">
            {advisors.map((a) => (
              <div className="advisor-card" key={a.name}>
                <h3>{a.name}</h3>
                <span className="advisor-unit">{a.unit}</span>
                <p>{a.task}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="about-cta">
        <div className="container about-cta-inner">
          <div>
            <h2>Tìm hiểu quy trình hoạt động của hệ thống</h2>
            <p>Xem hướng dẫn chi tiết hoặc dùng thử tính năng sinh câu hỏi bằng AI.</p>
          </div>
          <div className="about-cta-actions">
            <Link to="/huong-dan" className="btn btn--outline">Xem hướng dẫn</Link>
            <Link to="/sinh-cau-hoi" className="btn btn--primary">Trải nghiệm sinh câu hỏi</Link>
          </div>
        </div>
      </section>
    </main>
  );
}

export default AboutPage;
