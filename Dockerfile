# Образ бота и сайта (один образ, разные команды в docker-compose.yaml)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# LibreOffice — конвертация билета docx -> pdf; шрифты, совместимые с шаблоном
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui \
        fonts-liberation fonts-dejavu-core fonts-crosextra-carlito fonts-crosextra-caladea \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd -m app && mkdir -p logs xml_files && chown -R app:app /app
USER app
