import React from 'react';
import { Link } from 'react-router-dom';
import '../css/HomePage.css';

function HomePage() {
  return (
    <main className="home-page">
      {/* ═══════════════════════════════════════════
          HERO SECTION
      ═══════════════════════════════════════════ */}
      <section className="hero">
        <div className="hero-bg-mesh" aria-hidden="true">
          <div className="mesh-circle mesh-circle--1"></div>
          <div className="mesh-circle mesh-circle--2"></div>
          <div className="mesh-circle mesh-circle--3"></div>
        </div>

        <div className="container hero-container">
          {/* Left: Text */}
          <div className="hero-text">
            <div className="hero-badge">
              <span className="badge-dot"></span>
              Trường Công Nghệ Thông Tin &amp; Truyền Thông – ĐH Cần Thơ
            </div>

            <h1 className="hero-heading">
              Ngân Hàng Câu Hỏi<br />
              <em>Thông Minh </em>Với AI<br />
            </h1>

            <p className="hero-desc">
              Hệ thống sinh và quản lý ngân hàng câu hỏi dựa trên các mô hình
              LLM theo thang phân loại Bloom và đánh giá chất lượng tự động — hỗ
              trợ giảng viên tối ưu hoá quy trình kiểm tra đánh giá.
            </p>

            <div className="hero-cta">
              <Link to="/sinh-cau-hoi" className="btn btn--primary">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
                Bắt đầu ngay
              </Link>
              <Link to="/gioi-thieu" className="btn btn--outline">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 16v-4" />
                  <path d="M12 8h.01" />
                </svg>
                Tìm hiểu hệ thống
              </Link>
            </div>

            <div className="hero-trust">
              <div className="trust-item">
                <span className="trust-num">RAG</span>
                <span className="trust-label">Truy xuất tài liệu</span>
              </div>
              <div className="trust-divider"></div>
              <div className="trust-item">
                <span className="trust-num">Bloom</span>
                <span className="trust-label">Phân loại 6 cấp độ</span>
              </div>
              <div className="trust-divider"></div>
              <div className="trust-item">
                <span className="trust-num">Review</span>
                <span className="trust-label">Kiểm duyệt bởi người duyệt</span>
              </div>
            </div>
          </div>

          {/* Right: Illustration */}
          <div className="hero-visual" aria-hidden="true">
            <div className="visual-card visual-card--main">
              <div className="vc-header">
                <div className="vc-dots">
                  <span></span><span></span><span></span>
                </div>
                <span className="vc-title">Ngân hàng câu hỏi · Cấu trúc dữ liệu</span>
              </div>
              <div className="vc-body">
                <div className="vc-qitem">
                  <div className="vc-qitem-meta">
                    <span className="q-tag">MCQ</span>
                    <span className="bloom-tag bloom-tag--apply">Nhớ</span>
                  </div>
                  <p className="vc-qitem-text">Cấu trúc dữ liệu nào sau đây hoạt động theo nguyên tắc LIFO (Vào sau ra trước)?</p>
                  <div className="vc-qitem-choices">
                    <span className="choice">A. Hàng đợi (Queue)</span>
                    <span className="choice choice--correct">B. Ngăn xếp (Stack)</span>
                    <span className="choice">C. Danh sách liên kết</span>
                    <span className="choice">D. Đồ thị (Graph)</span>
                  </div>
                </div>
                <div className="vc-qitem">
                  <div className="vc-qitem-meta">
                    <span className="q-tag q-tag--tf">T/F</span>
                    <span className="bloom-tag bloom-tag--analyze">Phân tích</span>
                  </div>
                  <p className="vc-qitem-text">Trong cây nhị phân tìm kiếm (BST), phần tử ở nút con trái luôn lớn hơn phần tử ở nút cha.</p>
                  <div className="vc-qitem-choices">
                    <span className="choice">✓ Đúng</span>
                    <span className="choice choice--correct">✗ Sai</span>
                  </div>
                </div>
                <div className="vc-footer-meta">
                  <span className="vc-meta-chip">Llama 3</span>
                  <span className="vc-meta-score">Chất lượng: 4.8 / 5</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          WORKFLOW SECTION
      ═══════════════════════════════════════════ */}
      <section className="workflow" id="workflow">
        <div className="container">
          <div className="section-header">
            <div className="section-badge">AI Pipeline</div>
            <h2 className="section-title">Quy trình xử lý thông minh</h2>
            <p className="section-desc">
              Pipeline tích hợp đa mô hình LLM — từ tài liệu thô đến ngân hàng câu hỏi chất lượng cao.
            </p>
          </div>

          <div className="workflow-timeline">
            <div className="workflow-step">
              <div className="ws-icon-wrap">
                <div className="ws-icon">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="17 8 12 3 7 8" />
                    <line x1="12" y1="3" x2="12" y2="15" />
                  </svg>
                </div>
                <div className="ws-connector"></div>
              </div>
              <div className="ws-card">
                <span className="ws-step-num">01</span>
                <h3 className="ws-title">Tải tài liệu</h3>
                <p className="ws-desc">Nhập tài liệu học thuật dạng PDF hoặc văn bản thuần — hỗ trợ tiếng Việt đầy đủ với thư viện OCR.</p>
                <div className="ws-tags">
                  <span className="ws-tag">PDF</span>
                  <span className="ws-tag">DOCX</span>
                </div>
              </div>
            </div>

            <div className="workflow-step">
              <div className="ws-icon-wrap">
                <div className="ws-icon">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <line x1="3" y1="9" x2="21" y2="9" />
                    <line x1="3" y1="15" x2="21" y2="15" />
                    <line x1="9" y1="9" x2="9" y2="21" />
                  </svg>
                </div>
                <div className="ws-connector"></div>
              </div>
              <div className="ws-card">
                <span className="ws-step-num">02</span>
                <h3 className="ws-title">Chunking & Embedding</h3>
                <p className="ws-desc">Phân đoạn văn bản thông minh theo ngữ nghĩa, áp dụng kỹ thuật RAG để truy xuất ngữ cảnh chính xác.</p>
                <div className="ws-tags">
                  <span className="ws-tag">Semantic Split</span>
                  <span className="ws-tag">Vector DB</span>
                </div>
              </div>
            </div>

            <div className="workflow-step">
              <div className="ws-icon-wrap">
                <div className="ws-icon ws-icon--highlight">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <path d="M12 8v4l3 3" />
                  </svg>
                </div>
                <div className="ws-connector"></div>
              </div>
              <div className="ws-card ws-card--highlight">
                <span className="ws-step-num">03</span>
                <h3 className="ws-title">Đa mô hình LLM xử lý</h3>
                <p className="ws-desc">
                  Sử dụng các mô hình ngôn ngữ lớn (Qwen, Llama, Gemini) để phân tích tài liệu nội bộ, giảm thiểu ảo giác (hallucination).
                </p>
                <div className="ws-tags">
                  <span className="ws-tag ws-tag--blue">Gemini</span>
                  <span className="ws-tag ws-tag--blue">Qwen</span>
                  <span className="ws-tag ws-tag--blue">Llama</span>
                </div>
              </div>
            </div>

            <div className="workflow-step">
              <div className="ws-icon-wrap">
                <div className="ws-icon ws-icon--highlight">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 20h9" />
                    <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                  </svg>
                </div>
                <div className="ws-connector"></div>
              </div>
              <div className="ws-card ws-card--highlight">
                <span className="ws-step-num">04</span>
                <h3 className="ws-title">Sinh câu hỏi (Bloom)</h3>
                <p className="ws-desc">
                  Hệ thống tự động tạo câu hỏi dựa trên 6 cấp độ tư duy của thang Bloom:
                  Nhớ → Hiểu → Áp dụng → Phân tích → Đánh giá → Sáng tạo.
                </p>
                <div className="ws-tags">
                  <span className="ws-tag ws-tag--blue">Trắc Nghiệm</span>
                  <span className="ws-tag ws-tag--blue">Đúng/Sai</span>
                  <span className="ws-tag ws-tag--blue">Điền Khuyết</span>
                </div>
              </div>
            </div>

            <div className="workflow-step">
              <div className="ws-icon-wrap">
                <div className="ws-icon">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                  </svg>
                </div>
                <div className="ws-connector"></div>
              </div>
              <div className="ws-card">
                <span className="ws-step-num">05</span>
                <h3 className="ws-title">Kiểm duyệt có phản hồi</h3>
                <p className="ws-desc">AI đánh giá sơ bộ, người duyệt kiểm tra phiên bản hiện tại; câu cần sửa quay lại cho giảng viên chỉnh và gửi duyệt lại.</p>
                <div className="ws-tags">
                  <span className="ws-tag">AI đánh giá</span>
                  <span className="ws-tag">Người duyệt quyết định</span>
                </div>
              </div>
            </div>

            <div className="workflow-step workflow-step--last">
              <div className="ws-icon-wrap">
                <div className="ws-icon ws-icon--success">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                </div>
              </div>
              <div className="ws-card ws-card--success">
                <span className="ws-step-num">06</span>
                <h3 className="ws-title">Tích hợp Moodle</h3>
                <p className="ws-desc">Ngân hàng câu hỏi chất lượng cao được lưu trữ, export theo chuẩn Moodle và ghi nhận mô phỏng trong môi trường demo.</p>
                <div className="ws-tags">
                  <span className="ws-tag ws-tag--green">Moodle Export</span>
                  <span className="ws-tag ws-tag--green">JSON / DOCX</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════
          FEATURES SECTION
      ═══════════════════════════════════════════ */}
      <section className="features" id="features">
        <div className="container">
          <div className="section-header">
            <div className="section-badge">Tính năng</div>
            <h2 className="section-title">Được thiết kế cho học thuật</h2>
            <p className="section-desc">Bộ công cụ toàn diện hỗ trợ giảng viên và nhà nghiên cứu giáo dục theo chuẩn Đại học Cần Thơ.</p>
          </div>

          <div className="features-grid">
            <div className="feature-card">
              <div className="fc-icon fc-icon--1">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                </svg>
              </div>
              <h3 className="fc-title">Sinh câu hỏi tự động</h3>
              <p className="fc-desc">Tự động hoá hoàn toàn quy trình biên soạn câu hỏi từ giáo trình bằng AI tạo sinh.</p>
            </div>

            <div className="feature-card">
              <div className="fc-icon fc-icon--2">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5" /><path d="M2 12l10 5 10-5" />
                </svg>
              </div>
              <h3 className="fc-title">Chuẩn Bloom Taxonomy</h3>
              <p className="fc-desc">Phân loại câu hỏi chính xác theo 6 cấp độ nhận thức để đánh giá đúng năng lực người học.</p>
            </div>

            <div className="feature-card">
              <div className="fc-icon fc-icon--3">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M9 21V9" />
                </svg>
              </div>
              <h3 className="fc-title">Đa dạng định dạng</h3>
              <p className="fc-desc">Hỗ trợ MCQ, True/False, Điền khuyết, Ghép đôi và các câu hỏi tình huống phức tạp.</p>
            </div>

            <div className="feature-card feature-card--featured">
              <div className="fc-icon fc-icon--4">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" /><path d="M8 14s1.5 2 4 2 4-2 4-2" /><line x1="9" y1="9" x2="9.01" y2="9" /><line x1="15" y1="9" x2="15.01" y2="9" />
                </svg>
              </div>
              <h3 className="fc-title">Kỹ thuật RAG & Multi-LLM</h3>
              <p className="fc-desc">Giảm thiểu tối đa tình trạng AI bịa đặt thông tin (hallucination) nhờ kết hợp kho ngữ cảnh (RAG) và xác thực chéo LLM.</p>
              <div className="fc-featured-tag">Cốt lõi</div>
            </div>

            <div className="feature-card">
              <div className="fc-icon fc-icon--5">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" /><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
                </svg>
              </div>
              <h3 className="fc-title">Quản lý trực quan</h3>
              <p className="fc-desc">Bảng quản trị dễ sử dụng, phân quyền rõ ràng, hỗ trợ giảng viên tinh chỉnh ngân hàng câu hỏi linh hoạt.</p>
            </div>

            <div className="feature-card">
              <div className="fc-icon fc-icon--6">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                </svg>
              </div>
              <h3 className="fc-title">Export Moodle</h3>
              <p className="fc-desc">Đóng gói câu hỏi tự động theo định dạng chuẩn và ghi nhận mô phỏng publication cho demo.</p>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

export default HomePage;
