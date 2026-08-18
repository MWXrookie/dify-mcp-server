FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

RUN useradd --create-home --uid 10001 appuser && mkdir -p /app/data && chown appuser:appuser /app/data
WORKDIR /app

COPY requirements.lock.txt /app/requirements.lock.txt
RUN pip install --no-cache-dir --timeout 120 --retries 10 \
    -r /app/requirements.lock.txt

COPY config.py cache_store.py execution.py llm.py tools.py portal.py analysis.py server_safe.py dashboard.py /app/
COPY docs/test_results_raw*.json /app/docs/
USER 10001:10001

ARG APP_FILE=server_safe.py
ENV APP_FILE=${APP_FILE}
CMD ["/bin/sh", "-c", "exec python /app/${APP_FILE}"]
