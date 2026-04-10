FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-fra \
    tesseract-ocr-ara \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    poppler-utils \
    gcc \
    g++ \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --prefer-binary --no-cache-dir -r requirements.txt

# Installation Groq
RUN pip install groq

RUN python -m spacy download en_core_web_sm

COPY . .

ENV PYTHONPATH=/app
ENV TESSERACT_PATH=/usr/bin/tesseract