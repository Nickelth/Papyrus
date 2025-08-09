# ベースイメージ
FROM python:3.11-slim

# 環境変数で非対話インストール指定
ENV DEBIAN_FRONTEND=noninteractive \
    # ゴミファイル生成防止
    PYTHONDONTWRITEBYTECODE=1 \
    # 遅延なしデバッグ
    PYTHONUNBUFFERED=1\
    LANG=ja_JP.UTF-8 \
    LC_ALL=ja_JP.UTF-8

WORKDIR /app

# WeasyPrint/Pillow/cffi が必要とするネイティブ依存を入れる
# ※ libgdk-pixbuf のパッケージ名は `libgdk-pixbuf-2.0-0`（ハイフンあり）
RUN apt-get update && apt-get install -y --no-install-recommends \
    # コンパイル系
    build-essential \
    python3-dev \
    pkg-config \
    # WeasyPrint ランタイム
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    # Pillow画像系（多くはwheelで入るけど保険）
    libjpeg62-turbo \
    libopenjp2-7 \
    zlib1g \
    # 日本語フォント
    fonts-noto-cjk \
    fonts-dejavu-core \
    # ロケール周り（必要なら）
    locales \
 && sed -i '/ja_JP.UTF-8/s/^# //g' /etc/locale.gen \
 && locale-gen \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# 依存を先に入れてレイヤキャッシュを効かせる
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r requirements.txt

# アプリ本体
COPY . .

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "run:app"]