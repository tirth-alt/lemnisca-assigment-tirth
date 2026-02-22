# Stage 1: Build Frontend
FROM node:20 AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Build Backend
FROM python:3.10-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/cache/lists/*

# Copy backend requirements and install
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables for model caching
ENV SENTENCE_TRANSFORMERS_HOME=/app/models
ENV HF_HOME=/app/models

# Pre-download the embedding model
COPY backend/download_model.py ./
RUN python download_model.py

# Copy backend source
COPY backend/ ./

# Copy clearpath_docs (RAG source)
COPY clearpath_docs/ ./clearpath_docs/

# Copy built frontend assets to backend/static
COPY --from=frontend-build /frontend/dist ./static

# Set environment variables for container
ENV PROJECT_ROOT=/app
ENV PORT=8080

# Ensure directories exist
RUN mkdir -p /app/data/index

# Expose port (Cloud Run defaults to 8080)
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
