function GuidePage() {
    return (
        <section className="container page-section">
            <div className="page-header-card">
                <p className="section-chip">Hướng dẫn</p>
                <h1>Quy trình sử dụng hệ thống</h1>
            </div>
            <div className="card">
                <ol>
                    <li>Đăng nhập bằng tài khoản giảng viên.</li>
                    <li>Vào mục Sinh câu hỏi và nhập nội dung tài liệu.</li>
                    <li>Chọn cấp độ Bloom và số lượng câu hỏi.</li>
                    <li>Duyệt kết quả trong mục Quản lý trước khi xuất đề.</li>
                </ol>
            </div>
        </section>
    );
}

export default GuidePage;
