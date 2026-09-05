# Stage 1: Build React App
FROM node:20.19-alpine AS builder

WORKDIR /app

ARG VITE_DEMO_MODE=false
ENV VITE_DEMO_MODE=${VITE_DEMO_MODE}
ARG VITE_PIPELINE_3D=false
ENV VITE_PIPELINE_3D=${VITE_PIPELINE_3D}

# Copy package.json và package-lock.json để tận dụng cache
COPY package.json package-lock.json* ./
RUN npm ci

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
