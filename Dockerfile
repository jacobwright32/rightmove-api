# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libxml2-dev libxslt1-dev libopenblas-dev && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY --from=frontend-build /build/frontend/dist ./frontend/dist
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh && mkdir -p /data /app/sales_data
ENV DATABASE_URL=sqlite:////data/uk_house_prices.db \
    DATA_DIR=/data \
    PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["./entrypoint.sh"]
