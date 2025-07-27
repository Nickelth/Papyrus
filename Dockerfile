FROM python:3.12-slim

# 環境変数で非対話インストール指定
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 必須ライブラリのインストール --weasyprint対策
RUN apt-get update && apt-get install -y \
    build-essential \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Python依存のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードをコピー
COPY . .

CMD ["python", "app.py"]
