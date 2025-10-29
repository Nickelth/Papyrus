# papyrus/preflight_app.py

from flask import Flask
from papyrus.blueprints.healthz import bp as healthz_bp
from papyrus.blueprints.dbcheck import bp as dbcheck_bp

def create_app_skeleton():
    """
    CIプリフライト専用の軽量アプリ。
    - DB接続しない
    - Secrets呼ばない
    - authとかガチ機能も無視
    目的はルート構成を静的にチェックすることだけ。
    """
    app = Flask("preflight_only")

    # 必須エンドポイントだけ登録
    app.register_blueprint(healthz_bp)
    app.register_blueprint(dbcheck_bp)

    return app
