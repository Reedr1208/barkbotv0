FROM python:3.11-slim

# Install system dependencies for Playwright/Chromium and Node.js for build.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    nodejs \
    npm \
    # Playwright Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser
RUN python -m playwright install chromium

# Copy project files
COPY . .

# Build the inlined index.html for dog_meta SSR
RUN npm install --omit=dev 2>/dev/null || true
RUN node build.js 2>/dev/null || true

EXPOSE 8000

# Railway sets PORT env var — app must listen on it
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
