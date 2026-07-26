# 🧠 Hệ Thống Quản Lý & Tự Động Sinh Câu Hỏi Thi Bằng LLMs (RAG)

Đây là Backend API cho hệ thống tự động trích xuất tri thức từ tài liệu (PDF) và sinh câu hỏi trắc nghiệm/tự luận dựa trên **Bloom's Revised Taxonomy**. Hệ thống ứng dụng kiến trúc **RAG (Retrieval-Augmented Generation)** và **Programmatic Prompt Chains** để đảm bảo câu hỏi sinh ra bám sát ngữ liệu, tuân thủ nghiêm ngặt định dạng cấu trúc, và chống ảo giác (hallucination).

## ✨ Tính năng nổi bật

* **👁️ Xử lý OCR & Trích xuất:** Tự động đọc file PDF, làm sạch văn bản và bóc tách các khối công thức toán học phức tạp.
* **📚 Retrieval-Augmented Generation (RAG):** Băm nhỏ tài liệu (Chunking) và lưu trữ vector vào ChromaDB để truy xuất ngữ cảnh chính xác cao dựa trên Information Density.
* **🤖 Kiến trúc LLM Factory:** Dễ dàng chuyển đổi linh hoạt giữa các mô hình ngôn ngữ:
    * Google Gemini (Cloud)
    * Qwen (Local via Ollama)
    * Ollama local models for evaluation (DeepSeek-R1 is the demo default)
* **⛓️ Chuỗi Prompt Tự động (Programmatic Prompt Chains):** Điều khiển LLM hoàn toàn bằng code backend, hỗ trợ 7 loại câu hỏi và 6 cấp độ tư duy Bloom.

## 🛠️ Tech Stack

* **Framework:** FastAPI (Python)
* **Vector Database:** ChromaDB
* **Database:** MongoDB
* **Local LLM Engine:** Ollama

## 📁 Cấu trúc thư mục lõi (`app/services/`)

Hệ thống được thiết kế theo nguyên tắc Separation of Concerns:

```text
services/
├── llm/         # Factory Pattern cung cấp sức mạnh AI (Gemini, DeepSeek, Qwen)
├── ocr/         # Pipeline thị giác máy tính và làm sạch văn bản
├── rag/         # Xử lý cắt chunk, học từ vựng và tìm kiếm vector 
└── generation/  # Trái tim nghiệp vụ sinh câu hỏi và quản lý Prompt Chains
```

## 🚀 Hướng dẫn cài đặt và chạy dự án (Local Development)

### 1. Yêu cầu hệ thống (Prerequisites)

* Python 3.11+
* MongoDB (chạy local, cổng mặc định 27017)
* Ollama (nếu muốn chạy local model như DeepSeek/Qwen)
* Git

### 2. Clone Repository

```bash
git clone https://github.com/TriHao233/NCKH.git
cd NCKH/backend/rag-ocr-pipeline
```

### 3. Cài đặt mô hình AI (Chạy cục bộ)

Hệ thống dùng Ollama cho local model. Model evaluator mặc định là `deepseek-r1`, nhưng có thể đổi bằng biến môi trường:

```bash
ollama pull deepseek-r1:8b
```

Ví dụ đổi evaluator sang model Ollama khác:

```env
EVALUATION_MODEL_PROVIDER=ollama:qwen2.5:7b
```

### 4. Cài đặt dependencies

```bash
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Linux/macOS
pip install -r requirements.txt
```

### 5. Cấu hình biến môi trường

Tạo file `.env` ở thư mục gốc (`backend/rag-ocr-pipeline/.env`) và thêm các cấu hình sau:

```
APP_NAME="RAG API"
APP_VERSION="0.1.0"
HOST="0.0.0.0"
PORT=8000

MONGO_URI=mongodb://localhost:27017/

# OCR Path (đường dẫn Poppler trên máy host)
POPPLER_PATH=/usr/bin

# LLM
GEMINI_API_KEY=gemini-api-key
DEFAULT_MODEL=models/gemini-3.5-flash

# Chunking / Embedding
CHUNK_SIZE_DEFAULT=1000
CHUNK_SIZE_MIN=200
CHUNK_SIZE_MAX=4000
CHUNK_OVERLAP_DEFAULT=150
CHUNK_OVERLAP_MIN=0
CHUNK_OVERLAP_MAX=800
CHUNK_BUFFER_MAX_PAGES=30
CHUNK_BUFFER_MAX_CHARS=200000
MAX_CODE_BLOCK_LINES=50
CHROMADB_COLLECTION_NAME=chunks
CHROMADB_BATCH_SIZE=50
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
```

### 6. Khởi động hệ thống

Đảm bảo MongoDB đang chạy, sau đó khởi động server:

```bash
python main.py
```

Hoặc:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Hệ thống sẽ khởi động:

* FastAPI Backend: http://localhost:8000
* MongoDB Database: cổng 27017

## 📖 API Documentation (Swagger UI)

Khi server đã chạy thành công, truy cập vào giao diện tương tác API Swagger:
👉 http://localhost:8000/docs

## Flow chạy thử nghiệm (Happy Path)

* `POST /api/v1/documents/upload`: Upload file PDF, tạo document, lưu artifact gốc và enqueue OCR. Route cũ `POST /api/v1/ocr/upload` vẫn giữ để tương thích client/script cũ.
* `POST /api/v1/chunk/document`: Băm tài liệu đã OCR và lưu vào MongoDB + ChromaDB.
* `POST /api/v1/generate/questions`: Gọi API sinh câu hỏi với body mẫu:

```json
{
  "document_id": "id_tra_ve_tu_buoc_1",
  "collection_name": "Test",
  "target_heading": null,
  "bloom_level": "hieu",
  "question_type": "trac_nghiem",
  "num_questions": 5,
  "model_provider": "deepseek"
}
```
