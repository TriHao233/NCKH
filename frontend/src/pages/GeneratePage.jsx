function GeneratePage() {
    return (
        <section className="container page-section">
            <div className="page-header-card">
                <p className="section-chip">Sinh câu hỏi</p>
                <h1>Trình tạo câu hỏi bằng AI</h1>
                <p>Nhập nội dung môn học, chọn cấp độ Bloom và loại câu hỏi để sinh tự động.</p>
            </div>

            <div className="grid two-col">
                <form className="card form-grid" onSubmit={(e) => e.preventDefault()}>
                    <label>
                        Chủ đề
                        <input placeholder="Ví dụ: Lập trình hướng đối tượng" />
                    </label>
                    <label>
                        Cấp độ Bloom
                        <select defaultValue="Ap dung">
                            <option>Nho</option>
                            <option>Hieu</option>
                            <option>Ap dung</option>
                            <option>Phan tich</option>
                            <option>Danh gia</option>
                            <option>Sang tao</option>
                        </select>
                    </label>
                    <label>
                        Loại câu hỏi
                        <select defaultValue="MCQ">
                            <option>MCQ</option>
                            <option>True/False</option>
                            <option>Dien khuyet</option>
                        </select>
                    </label>
                    <label>
                        So luong
                        <input type="number" min="1" max="30" defaultValue="10" />
                    </label>
                    <button className="btn btn--primary" type="submit">Sinh câu hỏi</button>
                </form>

                <article className="card">
                    <h3>Xem trước kết quả</h3>
                    <div className="question-preview">
                        <p><strong>#Q001</strong> Trong Java, từ khóa nào gọi constructor lớp cha?</p>
                        <p className="muted">A. super() | B. parent() | C. base() | D. this()</p>
                    </div>
                    <div className="question-preview">
                        <p><strong>#Q002</strong> Một lớp có thể implement nhiều interface cùng lúc.</p>
                        <p className="muted">Đúng/Sai - Bloom: Phân tích</p>
                    </div>
                </article>
            </div>
        </section>
    );
}

export default GeneratePage;
