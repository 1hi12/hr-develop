# ==========================================
# STAGE 1 : Compiler le Frontend React
# ==========================================
FROM public.ecr.aws/docker/library/node:20-slim AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm install --legacy-peer-deps

COPY frontend/ ./

ENV NODE_OPTIONS="--max-old-space-size=4096"
RUN npx vite build

# ==========================================
# STAGE 2 : Backend Python + Frontend compilé
# ==========================================
FROM public.ecr.aws/docker/library/python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-ara \
    libpq-dev \
    ca-certificates \
    curl \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Copier le frontend buildé (vite génère dans /frontend/dist)
COPY --from=frontend-builder /static ./static

COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8000

CMD ["./start.sh"]
