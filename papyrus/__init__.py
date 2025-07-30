from flask import Flask
from papyrus.routes import register_routes
from papyrus.api_routes import register_api_routes
from papyrus.auth import init_auth
from papyrus.auth_routes import register_auth_routes
from .db import init_db
from dotenv import load_dotenv
import os

load_dotenv()
def create_app():
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    TEMPLATE_DIR = os.path.join(BASE_DIR, '../templates')
    app = Flask(__name__, template_folder=TEMPLATE_DIR)
    app.secret_key = os.getenv("FLASK_SECRET_KEY")

    init_auth(app)
    init_db(app)
    register_routes(app)
    register_api_routes(app)
    register_auth_routes(app)
    return app