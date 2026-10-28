# One application image is used for the one-shot bootstrap, FastAPI, and Streamlit services.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/runtime-data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000 8501
