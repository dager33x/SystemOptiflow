FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.base.txt requirements.ml.txt ./
RUN pip install --no-cache-dir -r requirements.base.txt -r requirements.ml.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
