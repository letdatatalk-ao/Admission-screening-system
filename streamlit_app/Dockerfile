FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir \
    streamlit==1.35.0 \
    requests==2.32.3 \
    pandas==2.2.2 \
    plotly==5.22.0 \
    openpyxl==3.1.3

COPY . .
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0"]