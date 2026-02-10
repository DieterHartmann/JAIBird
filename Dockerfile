FROM python:3.11-slim

# Install system dependencies: Chromium, ChromeDriver, Tesseract, Poppler
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for Chromium/Tesseract in container
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies first (cached layer unless requirements change)
COPY requirements_clean.txt .
RUN pip install --no-cache-dir -r requirements_clean.txt

# Copy application code
COPY . .

# Create data and log directories
RUN mkdir -p data/sens_pdfs/temp logs
