import React, { useState } from 'react';
import '../css/GeneratePage.css';

const questionTypes = [
  { id: 'mcq', label: 'Trắc nghiệm (MCQ)' },
  { id: 'tf', label: 'Đúng / Sai' },
  { id: 'fill', label: 'Điền khuyết' },
  { id: 'match', label: 'Ghép đôi' },
  { id: 'scenario', label: 'Tình huống' },
];

const bloomLevels = [
  { id: 'remember', label: 'Nhớ' },
  { id: 'understand', label: 'Hiểu' },
  { id: 'apply', label: 'Áp dụng' },
  { id: 'analyze', label: 'Phân tích' },
  { id: 'evaluate', label: 'Đánh giá' },
  { id: 'create', label: 'Sáng tạo' },
];

const draftQuestions = [
  {
    id: 'Q-DRAFT-01',
    type: 'MCQ',
    bloom: 'Nhớ',
    text: 'Cấu trúc dữ liệu nào sau đây hoạt động theo nguyên tắc LIFO (Vào sau ra trước)?',
    choices: ['A. Hàng đợi (Queue)', 'B. Ngăn xếp (Stack)', 'C. Danh sách liên kết', 'D. Đồ thị (Graph)'],
    correct: 1,
  },
  {
    id: 'Q-DRAFT-02',
    type: 'Đúng/Sai',
    bloom: 'Phân tích',
    text: 'Trong cây nhị phân tìm kiếm (BST), phần tử ở nút con trái luôn lớn hơn phần tử ở nút cha.',
    choices: ['Đúng', 'Sai'],
    correct: 1,
  },
  {
    id: 'Q-DRAFT-03',
    type: 'Điền khuyết',
    bloom: 'Hiểu',
    text: 'Thuật toán duyệt đồ thị theo chiều rộng có tên tiếng Anh là ______.',
    choices: ['Breadth-First Search (BFS)'],
    correct: 0,
  },
];

function GeneratePage() {
  const [selectedTypes, setSelectedTypes] = useState(['mcq', 'tf']);
  const [selectedBloom, setSelectedBloom] = useState(['understand', 'apply']);
  const [fileName, setFileName] = useState('');

  const toggle = (list, setList, id) => {
    setList(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  };

  return (
    <main className="generate-page">
      <section className="page-hero">
        <div className="container">
          <div className="page-hero-badge">AI Pipeline · RAG</div>
          <h1 className="page-hero-title">Trình sinh câu hỏi bằng AI</h1>
          <p className="page-hero-desc">
            Tải lên tài liệu học phần, cấu hình loại câu hỏi và cấp độ tư duy theo thang Bloom — hệ thống sẽ dùng
            mô hình ngôn ngữ lớn kết hợp kỹ thuật RAG để sinh câu hỏi nháp từ đúng nội dung tài liệu.
          </p>
        </div>
      </section>

      <section className="gen-steps">
        <div className="container gen-steps-row">
          <div className="gen-step gen-step--active">
            <span className="gen-step-num">1</span>
            <span className="gen-step-label">Tải tài liệu</span>
          </div>
          <div className="gen-step-line" />
          <div className="gen-step gen-step--active">
            <span className="gen-step-num">2</span>
            <span className="gen-step-label">Cấu hình sinh câu hỏi</span>
          </div>
          <div className="gen-step-line" />
          <div className="gen-step">
            <span className="gen-step-num">3</span>
            <span className="gen-step-label">Xem trước &amp; duyệt</span>
          </div>
        </div>
      </section>

      <section className="gen-body">
        <div className="container gen-grid">
          {/* Left: form */}
          <form className="gen-form-card" onSubmit={(e) => e.preventDefault()}>
            <h3 className="gen-card-title">Cấu hình sinh câu hỏi</h3>

            <div className="field-group">
              <label className="field-label">Tài liệu nguồn</label>
              <label className="upload-drop">
                <input
                  type="file"
                  accept=".pdf,.doc,.docx"
                  onChange={(e) => setFileName(e.target.files?.[0]?.name || '')}
                  hidden
                />
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                <span>{fileName || 'Kéo thả hoặc chọn file PDF / DOC'}</span>
                <span className="upload-hint">Hỗ trợ tài liệu tiếng Việt · Tự động OCR với file scan</span>
              </label>
            </div>

            <div className="field-group">
              <label className="field-label">Học phần</label>
              <select className="field-select" defaultValue="ctdl">
                <option value="ctdl">Cấu trúc dữ liệu</option>
                <option value="soon" disabled>Học phần khác (sắp ra mắt)</option>
              </select>
            </div>

            <div className="field-group">
              <label className="field-label">Loại câu hỏi</label>
              <div className="chip-group">
                {questionTypes.map((t) => (
                  <button
                    type="button"
                    key={t.id}
                    className={`chip ${selectedTypes.includes(t.id) ? 'chip--active' : ''}`}
                    onClick={() => toggle(selectedTypes, setSelectedTypes, t.id)}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="field-group">
              <label className="field-label">Cấp độ tư duy (Bloom)</label>
              <div className="chip-group">
                {bloomLevels.map((b) => (
                  <button
                    type="button"
                    key={b.id}
                    className={`chip chip--bloom ${selectedBloom.includes(b.id) ? 'chip--active' : ''}`}
                    onClick={() => toggle(selectedBloom, setSelectedBloom, b.id)}
                  >
                    {b.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="field-row">
              <div className="field-group">
                <label className="field-label">Số lượng câu hỏi</label>
                <input className="field-input" type="number" min="1" max="30" defaultValue="10" />
              </div>
            </div>

            <button className="btn btn--primary gen-submit" type="submit">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5" /><path d="M2 12l10 5 10-5" />
              </svg>
              Sinh câu hỏi bằng AI
            </button>
            <p className="gen-form-note">
              Toàn bộ câu hỏi sinh ra sẽ ở trạng thái nháp và cần giảng viên xác nhận trước khi lưu vào ngân hàng câu hỏi.
            </p>
          </form>

          {/* Right: preview */}
          <div className="gen-preview-card">
            <div className="gen-card-title-row">
              <h3 className="gen-card-title">Xem trước câu hỏi nháp</h3>
              <span className="gen-preview-count">{draftQuestions.length} câu hỏi</span>
            </div>

            <div className="draft-list">
              {draftQuestions.map((q) => (
                <article className="draft-item" key={q.id}>
                  <div className="draft-item-meta">
                    <span className="q-tag">{q.type}</span>
                    <span className="bloom-tag">{q.bloom}</span>
                    <span className="draft-status">Nháp · Chờ duyệt</span>
                  </div>
                  <p className="draft-item-text">{q.text}</p>
                  <div className="draft-item-choices">
                    {q.choices.map((c, i) => (
                      <span key={c} className={`choice ${i === q.correct ? 'choice--correct' : ''}`}>{c}</span>
                    ))}
                  </div>
                  <div className="draft-item-actions">
                    <button type="button" className="icon-btn" title="Chỉnh sửa">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                      </svg>
                      Sửa
                    </button>
                    <button type="button" className="icon-btn icon-btn--approve" title="Duyệt">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      Duyệt
                    </button>
                    <button type="button" className="icon-btn icon-btn--reject" title="Từ chối">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                      Từ chối
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

export default GeneratePage;
