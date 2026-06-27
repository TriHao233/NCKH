const mockQuestions = [
    {
        id: 'Q001',
        type: 'MCQ',
        bloom: 'Vận dụng',
        status: 'Đã duyệt',
        text: 'Trong Java, từ khóa nào gọi constructor lớp cha?',
        score: '4.8/5'
    },
    {
        id: 'Q002',
        type: 'T/F',
        bloom: 'Phân tích',
        status: 'Chờ duyệt',
        text: 'Một lớp có thể implement nhiều interface cùng lúc.',
        score: '4.5/5'
    }
];

function ManagePage() {
    return (
        <section className="container page-section">
            <div className="page-header-card">
                <p className="section-chip">Quản lý</p>
                <h1>Ngân hàng câu hỏi</h1>
            </div>

            <div className="stats-row">
                <div className="stat-card"><b>10</b><span>Câu hỏi</span></div>
                <div className="stat-card"><b>3</b><span>Đã duyệt</span></div>
                <div className="stat-card"><b>5</b><span>Chờ duyệt</span></div>
                <div className="stat-card"><b>2</b><span>Cần sửa</span></div>
            </div>

            <div className="card">
                <h3>Danh sách câu hỏi</h3>
                <div className="question-list">
                    {mockQuestions.map((item) => (
                        <article key={item.id} className="question-item">
                            <div>
                                <strong>{item.id}</strong> · {item.type} · {item.bloom}
                                <p>{item.text}</p>
                            </div>
                            <div className="question-meta">
                                <span>{item.status}</span>
                                <span>{item.score}</span>
                            </div>
                        </article>
                    ))}
                </div>
            </div>
        </section>
    );
}

export default ManagePage;
