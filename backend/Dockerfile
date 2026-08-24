FROM python:3.10-slim

WORKDIR /app


# Copy file requirements và cài đặt dependencies Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn
COPY . .

# Expose port mặc định của FastAPI
EXPOSE 8000

# Khởi chạy server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
