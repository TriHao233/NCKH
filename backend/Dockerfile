FROM python:3.10.14-slim

WORKDIR /app

# Cài đặt các thư viện hệ thống cần thiết cho EasyOCR và pdf2image
RUN apt-get update && apt-get install -y \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy file requirements và cài đặt dependencies Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn
COPY . .

# Expose port mặc định của FastAPI
EXPOSE 8000

# Khởi chạy server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
