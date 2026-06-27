function ContactPage() {
    return (
        <section className="container page-section">
            <div className="page-header-card">
                <p className="section-chip">Liên hệ</p>
                <h1>Kết nối với nhóm phát triển</h1>
            </div>
            <div className="grid two-col">
                <article className="card">
                    <h3>Thông tin trường</h3>
                    <p>Trường Công nghệ Thông tin và Truyền thông - Đại học Cần Thơ</p>
                    <p>Khu II, Đường 3/2, Ninh Kiều, Cần Thơ</p>
                    <a href="https://www.ctu.edu.vn" target="_blank" rel="noreferrer">www.ctu.edu.vn</a>
                </article>
                <form className="card form-grid" onSubmit={(e) => e.preventDefault()}>
                    <label>
                        Họ và tên
                        <input placeholder="Nhập họ tên" />
                    </label>
                    <label>
                        Email
                        <input type="email" placeholder="email@ctu.edu.vn" />
                    </label>
                    <label>
                        Nội dung
                        <textarea rows="5" placeholder="Nội dung liên hệ" />
                    </label>
                    <button className="btn btn--primary" type="submit">Gửi liên hệ</button>
                </form>
            </div>
        </section>
    );
}

export default ContactPage;
