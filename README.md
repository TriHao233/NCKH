# QBankCTU — Ứng dụng Web Quản lý Ngân hàng Câu hỏi tích hợp LLM

> Đề tài NCKH cấp cơ sở, Trường CNTT&TT — Đại học Cần Thơ
> Thời gian thực hiện: 03/2026 – 08/2026
> Chủ nhiệm đề tài: Trương Trí Hào (B2203553) — GVHD: TS. Phan Phương Lan, KS. Trương Phúc Vĩnh

Tài liệu này tóm tắt lại toàn bộ đề tài từ bản Thuyết minh, dùng làm ngữ cảnh tham chiếu nhanh khi phát triển (vibe code) — không cần mở lại file PDF gốc.

---

## 1. Bài toán & lý do làm

Việc soạn ngân hàng câu hỏi tại các cơ sở giáo dục hiện chủ yếu làm **thủ công**: tốn thời gian, chất lượng không đồng đều, thiếu câu hỏi ở mức tư duy cao. Các mô hình ngôn ngữ lớn (LLMs) có thể tự động sinh câu hỏi từ tài liệu, nhưng rào cản lớn nhất là **hallucination** — AI bịa thông tin nghe có vẻ đúng.

**Giải pháp:** xây dựng một hệ thống Web kết hợp:
- **RAG (Retrieval-Augmented Generation)** để LLM sinh câu hỏi bám sát nội dung tài liệu thật, giảm ảo giác.
- **Human-in-the-loop**: AI chỉ tạo câu hỏi *nháp*, giảng viên luôn là người kiểm duyệt/chỉnh sửa/phê duyệt cuối cùng trước khi xuất bản.

## 2. Mục tiêu

**Mục tiêu tổng quát:** Xây dựng ứng dụng Web quản lý ngân hàng câu hỏi, dùng LLM hỗ trợ sinh câu hỏi tự động từ tài liệu văn bản, với quy trình kiểm duyệt chặt chẽ trước khi đưa vào sử dụng chính thức.

**Mục tiêu cụ thể:**
1. Nền tảng quản lý ngân hàng câu hỏi tập trung, số hóa và có tổ chức.
2. Tự động hóa sinh đề bằng LLM + RAG, nhanh hơn nhiều lần so với thủ công.
3. Đảm bảo chất lượng nội dung qua cơ chế Human-in-the-loop (AI khởi tạo → giảng viên thẩm định).
4. Kiểm chứng tính khả thi của LLM **chạy local** (chi phí thấp, bảo mật cao) cho bài toán giáo dục chuyên ngành.
5. Đồng bộ dữ liệu câu hỏi sang **Moodle** (LMS của trường) thông qua Plugin.

## 3. Phạm vi

| Hạng mục | Phạm vi |
|---|---|
| Ngôn ngữ tài liệu | Tiếng Việt |
| Lĩnh vực nội dung | Học phần "Cấu trúc dữ liệu" (Data Structures) |
| Định dạng đầu vào | PDF, DOC (kể cả PDF dạng scan → cần OCR) |
| Loại câu hỏi | Trắc nghiệm 4 lựa chọn (MCQ), Đúng/Sai, Điền khuyết, Ghép đôi, Câu hỏi tình huống |
| Mô hình AI | LLM mã nguồn mở, chạy **local** (ứng viên: Qwen, Llama...) |
| Kỹ thuật lõi | RAG (truy xuất ngữ cảnh từ tài liệu để giảm ảo giác) |
| Đầu ra | Lưu trực tiếp vào Question Bank của Moodle qua Plugin |

## 4. Kiến trúc hệ thống & tech stack hiện tại

```
NCKH/
├── frontend/                  # React + Vite — Admin Dashboard
│   └── src/
│       ├── pages/             # HomePage, LoginPage, RegisterPage, GeneratePage,
│       │                      # ManagePage, GuidePage, AboutPage, ContactPage, UserProfile
│       ├── components/        # Header, Footer, Layout, UserProfileMenu
│       └── context/           # AuthContext (Firebase Auth)
│
├── backend/                   # FastAPI — Auth & orchestration
│   ├── main.py                 # App entrypoint, CORS, router mount
│   ├── auth/                   # register / login / profile (Firebase Auth)
│   ├── database.py, models.py  # Pydantic models
│   │
│   └── rag-ocr-pipeline/       # FastAPI con — Core AI (OCR + RAG + Generation)
│       └── app/
│           ├── engine/          # easyocr_engine.py, chromadb_engine.py
│           ├── models/          # ocr.py, chunking.py, schemas.py
│           ├── services/        # ocr/, rag/, llm/, generation/
│           ├── prompts/         # system.txt, bloom/, question_type/, examples.txt
│           ├── db/               # mongodb.py
│           └── api/v1/
```

**Stack:**
- **Frontend:** React 18 + Vite, React Router, Firebase SDK (auth), FontAwesome.
- **Backend (auth/orchestration):** FastAPI, Firebase Admin (xác thực người dùng).
- **Core AI (`rag-ocr-pipeline`):** FastAPI riêng, chạy độc lập.
  - OCR: `easyocr` + `pdf2image` (xử lý PDF scan tiếng Việt).
  - Vector DB: `chromadb` + `sentence-transformers` (embedding & retrieval cho RAG).
  - LLM: `google-genai` hiện dùng để thử nghiệm (mục tiêu cuối là LLM local qua PyTorch CUDA — `torch`/`torchvision`/`torchaudio` đã có trong requirements).
  - Lưu trữ tài liệu/metadata: MongoDB (`pymongo`).
  - Prompt được tổ chức theo **thang đo BLOOM** và theo **loại câu hỏi** (`prompts/bloom/`, `prompts/question_type/`).

> Ghi chú: `backend/` (auth) và `backend/rag-ocr-pipeline/` (AI core) là 2 service FastAPI tách biệt — backend chính lo auth/CRUD, pipeline lo xử lý tài liệu + sinh câu hỏi. Cần làm rõ giao tiếp giữa 2 service này (gọi trực tiếp qua HTTP nội bộ, hay gộp lại) khi phát triển tiếp.

## 5. Flow hoạt động dự kiến (end-to-end)

```
1. Giảng viên đăng nhập (Firebase Auth) → vào Admin Dashboard
2. Upload tài liệu (PDF/DOC) — môn Cấu trúc dữ liệu
        │
        ▼
3. Tiền xử lý tài liệu
   - Nếu là PDF scan → OCR (easyocr) trích xuất văn bản
   - Làm sạch, chuẩn hóa văn bản
        │
        ▼
4. Chunking — chia văn bản thành đoạn nhỏ, sinh embedding
   → lưu vào Vector DB (ChromaDB) — đây là "kho tri thức" cho RAG
        │
        ▼
5. Sinh câu hỏi (Generation)
   - Truy xuất (retrieve) đoạn liên quan từ ChromaDB theo chủ đề
   - Ghép prompt (system + BLOOM level + loại câu hỏi + ngữ cảnh truy xuất)
   - Gọi LLM → sinh câu hỏi nháp (MCQ / True-False / Fill-in-blank / Matching / Scenario)
        │
        ▼
6. Human-in-the-loop — Question Editor (giảng viên)
   - Xem, chỉnh sửa nội dung, đáp án, độ khó (BLOOM)
   - Duyệt (approve) hoặc từ chối
        │
        ▼
7. Câu hỏi đã duyệt → lưu vào Ngân hàng câu hỏi (Question Bank nội bộ)
        │
        ▼
8. Xuất bản / đồng bộ sang Moodle
   - Chuyển đổi dữ liệu sang định dạng chuẩn Moodle (nội dung, đáp án, xáo trộn)
   - Plugin Moodle (PHP + Moodle Database API) nhận và lưu vào Question Bank của Moodle
```

**Vòng đời một câu hỏi:** `Soạn thảo (AI draft) → Phản biện → Duyệt → Xuất bản (Moodle)`

## 6. Chức năng chính (theo nhóm người dùng)

**Admin:**
- Quản lý người dùng, phân quyền (Admin / Giảng viên).
- Quản lý học phần, cấu hình tham số AI (model, prompt, RAG settings).

**Giảng viên:**
- Upload tài liệu nguồn (`GeneratePage`) → kích hoạt pipeline sinh câu hỏi.
- Chỉnh sửa câu hỏi bằng Question Editor.
- Quản lý ngân hàng câu hỏi cá nhân/môn học (`ManagePage`).
- Duyệt & xuất bản câu hỏi sang Moodle.
- Quản lý hồ sơ cá nhân (`UserProfile`).

Các trang frontend hiện có khớp với các chức năng trên: `HomePage`, `LoginPage`/`RegisterPage` (auth), `GeneratePage` (sinh câu hỏi từ tài liệu), `ManagePage` (quản lý ngân hàng câu hỏi), `GuidePage`, `AboutPage`, `ContactPage`.

## 7. Tiêu chí chất lượng câu hỏi

- Phân loại theo **thang đo BLOOM**: Nhận biết – Thông hiểu – Vận dụng – ...
- Đúng kiến thức nguồn (nhờ RAG bám tài liệu), văn phong tự nhiên tiếng Việt.
- Đúng định dạng nhập liệu Moodle (đáp án, thiết lập xáo trộn, hiển thị tiếng Việt ổn định).

## 8. Timeline nghiên cứu (mốc tham khảo)

| Giai đoạn | Thời gian | Nội dung |
|---|---|---|
| 1. Thu thập dữ liệu & nghiên cứu công nghệ | 03/2026 | Tìm hiểu LLM/RAG, thu thập giáo trình Cấu trúc dữ liệu, tiền xử lý (clean/OCR) |
| 2. Phân tích & thiết kế | 03–04/2026 | Đặc tả yêu cầu, thiết kế DB & Moodle mapping, thiết kế UI Dashboard |
| 3. Module AI (Core) | 04–05/2026 | Pipeline Đọc tài liệu → Chunking → Embedding → LLM Generation; tối ưu prompt |
| 4. Backend & tích hợp Moodle | 05–06/2026 | API CRUD, Plugin Moodle |
| 5. Frontend (Admin Dashboard) | 06–07/2026 | Giao diện quản lý ngân hàng câu hỏi, Question Editor |
| 6. Kiểm thử & hoàn thiện | 07–08/2026 | Kiểm thử chức năng + kiểm thử chất lượng AI, báo cáo, video demo |

## 9. Sản phẩm bàn giao

- Hệ thống Web quản lý & sinh câu hỏi trắc nghiệm (Admin Dashboard).
- Plugin tích hợp Moodle (đồng bộ câu hỏi tự động, đúng chuẩn Moodle).
- Mã nguồn hoàn chỉnh Backend + Moodle Plugin, tài liệu hướng dẫn cài đặt/tích hợp.
- Báo cáo tổng kết + video demo quy trình (≤ 2 phút).

## 10. Định hướng kỹ thuật cần lưu ý khi code tiếp

- **RAG là xương sống chống hallucination** — mọi câu hỏi sinh ra phải truy xuất ngữ cảnh từ ChromaDB trước khi gọi LLM, không sinh "chay" từ kiến thức nội tại của model.
- **LLM mục tiêu là chạy local/mã nguồn mở** (Qwen, Llama...) — `google-genai` trong requirements hiện tại là phương án thử nghiệm/tạm thời, không phải đích cuối.
- **OCR chỉ cần khi tài liệu là PDF scan** (ảnh) — tài liệu PDF text thuần không cần qua easyocr.
- **Không được auto-publish câu hỏi AI sinh ra** — luôn phải qua bước duyệt của giảng viên (human-in-the-loop) trước khi vào Moodle.
- **Chuẩn hóa output theo Moodle**: đáp án, thiết lập xáo trộn, mã hóa tiếng Việt phải đúng ngay từ bước Generation để Plugin xuất bản không cần xử lý lại.
- Hai service FastAPI (`backend/` và `backend/rag-ocr-pipeline/`) hiện tách rời — cần quyết định cơ chế giao tiếp (REST nội bộ, message queue, hay hợp nhất) khi ghép luồng end-to-end.
