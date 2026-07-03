import React, { useState } from 'react';
import '../css/ManagePage.css';

const mockQuestions = [
  {
    id: 'Q001',
    type: 'MCQ',
    bloom: 'Vận dụng',
    status: 'Đã duyệt',
    source: 'AI + Giảng viên',
    text: 'Cấu trúc dữ liệu nào sau đây hoạt động theo nguyên tắc LIFO?',
  },
  {
    id: 'Q002',
    type: 'Đúng/Sai',
    bloom: 'Phân tích',
    status: 'Chờ duyệt',
    source: 'AI sinh',
    text: 'Trong cây nhị phân tìm kiếm (BST), nút con trái luôn lớn hơn nút cha.',
  },
  {
    id: 'Q003',
    type: 'Điền khuyết',
    bloom: 'Hiểu',
    status: 'Chờ duyệt',
    source: 'AI sinh',
    text: 'Thuật toán duyệt đồ thị theo chiều rộng có tên tiếng Anh là ______.',
  },
  {
    id: 'Q004',
    type: 'MCQ',
    bloom: 'Nhớ',
    status: 'Cần sửa',
    source: 'AI sinh',
    text: 'Độ phức tạp trung bình của thuật toán Quick Sort là bao nhiêu?',
  },
  {
    id: 'Q005',
    type: 'Ghép đôi',
    bloom: 'Áp dụng',
    status: 'Đã duyệt',
    source: 'Giảng viên',
    text: 'Ghép tên cấu trúc dữ liệu với ứng dụng thực tế tương ứng.',
  },
];

const documents = [
  { name: 'Giáo trình Cấu trúc dữ liệu.pdf', pages: 186, status: 'Đã xử lý' },
  { name: 'Bài giảng - Cây & Đồ thị.pdf', pages: 42, status: 'Đã xử lý' },
  { name: 'Đề cương chi tiết học phần.docx', pages: 8, status: 'Đang xử lý' },
];

const statusClass = {
  'Đã duyệt': 'status--approved',
  'Chờ duyệt': 'status--pending',
  'Cần sửa': 'status--revise',
};

function ManagePage() {
  const [statusFilter, setStatusFilter] = useState('all');

  const filtered = statusFilter === 'all'
    ? mockQuestions
    : mockQuestions.filter((q) => q.status === statusFilter);

  const counts = {
    all: mockQuestions.length,
    'Đã duyệt': mockQuestions.filter((q) => q.status === 'Đã duyệt').length,
    'Chờ duyệt': mockQuestions.filter((q) => q.status === 'Chờ duyệt').length,
    'Cần sửa': mockQuestions.filter((q) => q.status === 'Cần sửa').length,
  };

  return (
    <main className="manage-page">
      <section className="page-hero">
        <div className="container manage-hero-row">
          <div>
            <div className="page-hero-badge">Admin Dashboard</div>
            <h1 className="page-hero-title">Quản lý ngân hàng câu hỏi</h1>
            <p className="page-hero-desc">
              Theo dõi, chỉnh sửa và phê duyệt câu hỏi trước khi đồng bộ vào ngân hàng đề thi trên Moodle.
            </p>
          </div>
          <div className="manage-hero-actions">
            <button type="button" className="btn btn--outline">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>
              Xuất đề thi
            </button>
            <button type="button" className="btn btn--primary">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="17 1 21 5 17 9" /><path d="M3 11V9a4 4 0 0 1 4-4h14" /><polyline points="7 23 3 19 7 15" /><path d="M21 13v2a4 4 0 0 1-4 4H3" /></svg>
              Đồng bộ Moodle
            </button>
          </div>
        </div>
      </section>

      <section className="manage-body">
        <div className="container manage-grid">
          {/* Main column */}
          <div className="manage-main">
            <div className="stats-row">
              <button type="button" className={`stat-card ${statusFilter === 'all' ? 'stat-card--active' : ''}`} onClick={() => setStatusFilter('all')}>
                <b>{counts.all}</b>
                <span>Tổng câu hỏi</span>
              </button>
              <button type="button" className={`stat-card ${statusFilter === 'Đã duyệt' ? 'stat-card--active' : ''}`} onClick={() => setStatusFilter('Đã duyệt')}>
                <b>{counts['Đã duyệt']}</b>
                <span>Đã duyệt</span>
              </button>
              <button type="button" className={`stat-card ${statusFilter === 'Chờ duyệt' ? 'stat-card--active' : ''}`} onClick={() => setStatusFilter('Chờ duyệt')}>
                <b>{counts['Chờ duyệt']}</b>
                <span>Chờ duyệt</span>
              </button>
              <button type="button" className={`stat-card ${statusFilter === 'Cần sửa' ? 'stat-card--active' : ''}`} onClick={() => setStatusFilter('Cần sửa')}>
                <b>{counts['Cần sửa']}</b>
                <span>Cần sửa</span>
              </button>
            </div>

            <div className="card list-card">
              <div className="list-card-header">
                <h3>Danh sách câu hỏi</h3>
                <div className="list-toolbar">
                  <select className="field-select" defaultValue="ctdl">
                    <option value="ctdl">Cấu trúc dữ liệu</option>
                  </select>
                  <select className="field-select" defaultValue="all-type">
                    <option value="all-type">Tất cả loại câu hỏi</option>
                    <option>MCQ</option>
                    <option>Đúng/Sai</option>
                    <option>Điền khuyết</option>
                    <option>Ghép đôi</option>
                  </select>
                  <input className="field-input search-input" placeholder="Tìm câu hỏi..." />
                </div>
              </div>

              <div className="question-list">
                {filtered.map((item) => (
                  <article key={item.id} className="question-item">
                    <div className="question-main">
                      <div className="question-meta-row">
                        <span className="q-id">{item.id}</span>
                        <span className="q-tag">{item.type}</span>
                        <span className="bloom-tag">{item.bloom}</span>
                        <span className="source-tag">{item.source}</span>
                      </div>
                      <p>{item.text}</p>
                    </div>
                    <div className="question-side">
                      <span className={`status-badge ${statusClass[item.status]}`}>{item.status}</span>
                      <div className="question-actions">
                        <button type="button" className="icon-btn" title="Chỉnh sửa">
                          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" /></svg>
                        </button>
                        <button type="button" className="icon-btn icon-btn--danger" title="Xoá">
                          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6" /></svg>
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
                {filtered.length === 0 && (
                  <p className="empty-note">Không có câu hỏi nào ở trạng thái này.</p>
                )}
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <aside className="manage-side">
            <div className="card side-card">
              <h3>Tài liệu nguồn</h3>
              <div className="doc-list">
                {documents.map((d) => (
                  <div className="doc-item" key={d.name}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
                    <div className="doc-info">
                      <span className="doc-name">{d.name}</span>
                      <span className="doc-meta">{d.pages} trang · {d.status}</span>
                    </div>
                  </div>
                ))}
              </div>
              <button type="button" className="btn btn--outline doc-upload-btn">+ Tải tài liệu mới</button>
            </div>

            <div className="card side-card">
              <h3>Trạng thái Moodle</h3>
              <p className="side-note">
                Câu hỏi đã duyệt sẽ được chuyển đổi sang định dạng chuẩn của Moodle (nội dung, đáp án, thiết lập xáo trộn)
                trước khi đồng bộ.
              </p>
              <div className="moodle-status">
                <span className="moodle-dot" />
                Plugin Moodle: sẵn sàng đồng bộ
              </div>
            </div>
          </aside>
        </div>
      </section>
    </main>
  );
}

export default ManagePage;
