FROM python:3.11-alpine

WORKDIR /app

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

COPY app ./app

EXPOSE 8000

CMD ["python", "-m", "app.main"]
