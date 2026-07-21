FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend/trog

COPY backend/trog/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

COPY backend/trog/ ./
COPY site/ /app/site/

RUN useradd --create-home --uid 10001 trog \
    && chown -R trog:trog /app
USER trog

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8787} --workers 2 --threads 4 --timeout 60 app:app"]
