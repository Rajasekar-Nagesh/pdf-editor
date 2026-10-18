# PDFDesk backend image (used by the api, worker and scheduler services).
# Includes every external tool: Ghostscript, Tesseract (eng/tam/hin), LibreOffice, veraPDF, Chromium.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    VERAPDF_PATH=/opt/verapdf/verapdf

RUN apt-get update && apt-get install -y --no-install-recommends \
        ghostscript \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-tam tesseract-ocr-hin \
        unpaper pngquant qpdf \
        libreoffice-writer libreoffice-calc libreoffice-impress \
        fonts-noto-core fonts-dejavu-core fonts-liberation \
        default-jre-headless \
        libglib2.0-0 libgl1 \
        curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# veraPDF (PDF/A validator) - unattended install of the CLI only.
COPY verapdf-auto-install.xml /tmp/verapdf-auto-install.xml
RUN curl -fsSL -o /tmp/verapdf.zip https://software.verapdf.org/releases/verapdf-installer.zip \
    && unzip -q /tmp/verapdf.zip -d /tmp/verapdf \
    && /tmp/verapdf/verapdf-greenfield-*/verapdf-install /tmp/verapdf-auto-install.xml \
    && rm -rf /tmp/verapdf /tmp/verapdf.zip

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY app ./app
COPY tests ./tests
COPY pytest.ini .

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 pdfdesk && mkdir -p /data/files && chown -R pdfdesk /data /app
USER pdfdesk

EXPOSE 8000
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "3", "-b", "0.0.0.0:8000", "--timeout", "300", "--graceful-timeout", "30"]
