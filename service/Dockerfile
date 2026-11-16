FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && useradd --uid 10001 --create-home appuser
COPY app ./app
USER appuser
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
