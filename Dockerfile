FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 RUN_MIGRATIONS=true
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic
EXPOSE 8000
CMD ["sh", "-ec", "if [ \"$RUN_MIGRATIONS\" = \"true\" ]; then alembic upgrade head; fi; exec uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
