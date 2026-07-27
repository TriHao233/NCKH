import React from 'react';
import { Link } from 'react-router-dom';
import '../css/GuidePage.css';

const roles = [
  {
    title: 'Giảng viên',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
      </svg>
    ),
    desc: 'Tải tài liệu học phần, sinh câu hỏi nháp, chỉnh sửa nội dung và gửi sang hàng kiểm duyệt.',
  },
  {
    title: 'Người duyệt',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </svg>
    ),
    desc: 'Nhận câu hỏi trong hàng đợi, đối chiếu nguồn, ghi lỗi cần sửa, duyệt hoặc từ chối phiên bản hiện tại.',
  },
  {
    title: 'Quản trị viên',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2l8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6l8-4z" />
      </svg>
    ),
    desc: 'Quản lý tài khoản, phân quyền, danh mục, hàng đợi vận hành và cấu hình ghi mô phỏng Moodle.',
  },
];

const steps = [
  {
    num: '01',
    title: 'Đăng nhập hệ thống',
    desc: 'Sử dụng tài khoản giảng viên, người duyệt hoặc quản trị viên do nhà trường cấp để đăng nhập vào QBankCTU.',
  },
  {
    num: '02',
    title: 'Tải tài liệu học phần',
    desc: 'Vào mục "Sinh câu hỏi", tải lên giáo trình, bài giảng hoặc đề cương dạng PDF/DOC của môn Cấu trúc dữ liệu.',
  },
  {
    num: '03',
    title: 'Cấu hình tham số sinh câu hỏi',
    desc: 'Chọn loại câu hỏi (MCQ, Đúng/Sai, Điền khuyết, Ghép đôi, Tình huống), cấp độ Bloom và số lượng câu hỏi cần tạo.',
  },
  {
    num: '04',
    title: 'AI sinh câu hỏi nháp',
    desc: 'Hệ thống dùng kỹ thuật RAG truy xuất đúng ngữ cảnh từ tài liệu, sau đó mô hình ngôn ngữ lớn sinh ra bộ câu hỏi nháp.',
  },
  {
    num: '05',
    title: 'Gửi kiểm duyệt',
    desc: 'Giảng viên rà soát nội dung, đáp án, CLO và gửi câu hỏi nháp sang hàng đợi kiểm duyệt.',
  },
  {
    num: '06',
    title: 'Duyệt, sửa và xuất bản',
    desc: 'Người duyệt phê duyệt, từ chối hoặc yêu cầu sửa. Câu cần sửa quay lại cho giảng viên chỉnh rồi gửi duyệt lại; câu đã duyệt có thể export GIFT/XML hoặc ghi mô phỏng Moodle.',
  },
];

const faqs = [
  {
    q: 'Tài liệu đầu vào cần định dạng gì?',
    a: 'Hệ thống nhận tài liệu dạng PDF hoặc DOC bằng tiếng Việt. Với file PDF dạng scan (hình ảnh), hệ thống tích hợp OCR để nhận dạng và trích xuất văn bản trước khi xử lý.',
  },
  {
    q: 'Hệ thống hỗ trợ những loại câu hỏi nào?',
    a: 'Năm loại: Trắc nghiệm 4 lựa chọn (MCQ), Đúng/Sai, Điền khuyết, Ghép đôi và Câu hỏi tình huống.',
  },
  {
    q: 'Câu hỏi do AI sinh ra có tự động lưu vào ngân hàng câu hỏi không?',
    a: 'Không. Câu hỏi AI sinh ra ở trạng thái "Nháp"; giảng viên gửi kiểm duyệt và chỉ câu đã được người duyệt phê duyệt mới đi tiếp vào luồng xuất bản.',
  },
  {
    q: 'Tôi có thể chỉnh sửa câu hỏi sau khi AI tạo ra không?',
    a: 'Có. Giảng viên có thể chỉnh sửa nội dung, đáp án, mức Bloom/CLO trước khi gửi duyệt, hoặc sửa lại theo phản hồi "Cần sửa" của người duyệt.',
  },
  {
    q: 'Câu hỏi đã duyệt được đưa vào Moodle như thế nào?',
    a: 'Hệ thống chuyển đổi dữ liệu câu hỏi sang cấu trúc chuẩn của Moodle (nội dung, đáp án, thiết lập xáo trộn) để export GIFT/XML; publication hiện là mô phỏng trong demo.',
  },
];

function GuidePage() {
  return (
    <main className="guide-page">
      <section className="page-hero">
        <div className="container">
          <div className="page-hero-badge">Hướng dẫn sử dụng</div>
          <h1 className="page-hero-title">Bắt đầu với QBankCTU chỉ trong vài bước</h1>
          <p className="page-hero-desc">
            Từ tải tài liệu đến export câu hỏi theo chuẩn Moodle — quy trình được thiết kế đơn giản, rõ ràng, phù hợp cho
            cả giảng viên chưa quen thao tác kỹ thuật.
          </p>
        </div>
      </section>

      <section className="roles">
        <div className="container roles-grid">
          {roles.map((r) => (
            <div className="role-card" key={r.title}>
              <div className="role-icon">{r.icon}</div>
              <h3>{r.title}</h3>
              <p>{r.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="steps">
        <div className="container">
          <div className="section-header">
            <div className="section-badge">Quy trình</div>
            <h2 className="section-title">6 bước sử dụng hệ thống</h2>
            <p className="section-desc">Áp dụng nguyên tắc "Con người trong vòng lặp" — AI hỗ trợ khởi tạo, giảng viên giữ quyền quyết định cuối cùng.</p>
          </div>

          <div className="steps-list">
            {steps.map((s) => (
              <div className="step-row" key={s.num}>
                <span className="step-num">{s.num}</span>
                <div className="step-body">
                  <h3>{s.title}</h3>
                  <p>{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="faq">
        <div className="container">
          <div className="section-header">
            <div className="section-badge">Câu hỏi thường gặp</div>
            <h2 className="section-title">Giải đáp nhanh</h2>
          </div>
          <div className="faq-list">
            {faqs.map((f) => (
              <details className="faq-item" key={f.q}>
                <summary>{f.q}</summary>
                <p>{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <section className="guide-cta">
        <div className="container guide-cta-inner">
          <div>
            <h2>Sẵn sàng tạo bộ câu hỏi đầu tiên?</h2>
            <p>Chuyển sang mục Sinh câu hỏi để trải nghiệm quy trình đầy đủ.</p>
          </div>
          <Link to="/sinh-cau-hoi" className="btn btn--primary">Đến trang Sinh câu hỏi</Link>
        </div>
      </section>
    </main>
  );
}

export default GuidePage;
