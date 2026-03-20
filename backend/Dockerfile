FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --prefer-binary --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_lg

COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]