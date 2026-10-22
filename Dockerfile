FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 RUN_MIGRATIONS=true
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends redis-server \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic
EXPOSE 8000
CMD ["sh", "-ec", "redis-server --daemonize yes; if [ \"$RUN_MIGRATIONS\" = \"true\" ]; then alembic upgrade head; fi; exec uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
