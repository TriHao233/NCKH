function AboutPage() {
    return (
        <section className="container page-section">
            <div className="page-header-card">
                <p className="section-chip">Về chúng tôi</p>
                <h1>Giới thiệu QBankCTU</h1>
                <p>
                    Dự án do sinh viên CICT thực hiện, tập trung tự động hóa quy trình biên soạn câu hỏi
                    học thuật với cơ chế Human-in-the-loop.
                </p>
            </div>

            <div className="grid two-col">
                <article className="card">
                    <h3>Nhóm thực hiện</h3>
                    <ul className="plain-list">
                        <li>Trương Trí Hào - Quản lý dự án</li>
                        <li>Tiêu Lê Gia Linh - UI/UX & API</li>
                        <li>Trần Hải Thiên - RAG & Processing</li>
                        <li>Lê Trọng Thiện - Backend</li>
                        <li>V. P. Quốc Cường - Database & Moodle</li>
                    </ul>
                </article>

                <article className="card">
                    <h3>Mục tiêu chính</h3>
                    <ul className="plain-list">
                        <li>Giảm thời gian biên soạn đề thi</li>
                        <li>Phân loại theo Bloom Taxonomy</li>
                        <li>Đánh giá chéo Multi-LLM</li>
                        <li>Tích hợp hệ thống Moodle</li>
                    </ul>
                </article>
            </div>
        </section>
    );
}

export default AboutPage;
