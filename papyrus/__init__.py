from flask import Flask
from papyrus.routes import register_routes
from papyrus.api_routes import register_api_routes
from papyrus.auth import init_auth
from papyrus.auth_routes import register_auth_routes
from .db import init_db
from papyrus.config_runtime import load_config, init_db_pool  # ★ 追加
import os
from papyrus.blueprints.dbcheck import bp as dbcheck_bp

def create_app():
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    TEMPLATE_DIR = os.path.join(BASE_DIR, '../templates')
    app = Flask(__name__, template_folder=TEMPLATE_DIR)

    # ★ 本番仕様の設定をロード（env or aws）
    cfg = load_config()
    app.config["APP_CFG"] = cfg
    app.secret_key = cfg.flask_secret_key

    # ★ DBプールを初期化して app に保持
    app.config["DB_POOL"] = init_db_pool(cfg)

    init_auth(app)     # ← cfg から読むよう後述の修正で対応
    init_db(app)       # ← プールを使うよう後述で修正
    register_routes(app)
    register_api_routes(app)
    register_auth_routes(app)
    app.register_blueprint(dbcheck_bp)
    return app