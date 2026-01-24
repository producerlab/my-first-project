FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости для Playwright
# Добавлены дополнительные зависимости для стабильной работы на Railway
RUN apt-get update && apt-get install -y \
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
    # Дополнительные зависимости для Chromium
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxext6 \
    libxi6 \
    libxtst6 \
    libglib2.0-0 \
    fonts-liberation \
    libnss3-tools \
    xdg-utils \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Копируем и устанавливаем зависимости Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем браузер Playwright с зависимостями
RUN playwright install chromium --with-deps

# Копируем код
COPY . .

# Создаем папки для данных
RUN mkdir -p exports data

# Запуск бота
CMD ["python", "bot.py"]
