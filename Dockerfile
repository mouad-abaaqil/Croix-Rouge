FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY database.py webapp.py routing.py ./
COPY templates ./templates
COPY static ./static
COPY assets ./assets
COPY data/collection_points.csv ./data/collection_points.csv
RUN useradd --create-home --uid 10001 appuser && mkdir -p /app/instance && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "30", "webapp:app"]
