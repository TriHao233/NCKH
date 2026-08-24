# Stage 1: Build React App
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package.json và package-lock.json để tận dụng cache
COPY package.json package-lock.json* ./
RUN npm install

# Copy toàn bộ source code và build
COPY . .
RUN npm run build

# Stage 2: Serve với Nginx
FROM nginx:alpine

# Copy kết quả build từ stage 1 sang thư mục html của Nginx
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy cấu hình Nginx custom (để hỗ trợ React Router)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
