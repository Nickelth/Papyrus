from flask import Flask
from papyrus.auth import init_auth
from .db import init_db

def create_app():
    app = Flask(__name__)
    app.secret_key = "your_secret"
    init_auth(app)
    init_db(app)

    from .routes import register_routes
    register_routes(app)

    return app
