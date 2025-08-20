from flask import session, redirect, url_for, request, current_app
from authlib.integrations.flask_client import OAuth
from functools import wraps
import os

oauth = OAuth()
auth0 = None

def init_auth(app):
    # ★ __init__.py ですでに app.secret_key 設定済み
    cfg = app.config["APP_CFG"]
    oauth.init_app(app)
    global auth0
    auth0 = oauth.register(
        'auth0',
        client_id=cfg.auth0.client_id,
        client_secret=cfg.auth0.client_secret,
        client_kwargs={'scope': 'openid profile email'},
        server_metadata_url=f'https://{cfg.auth0.domain}/.well-known/openid-configuration',
        redirect_uri=cfg.auth0.callback_url
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def handle_login():
    cfg = current_app.config["APP_CFG"]
    return auth0.authorize_redirect(redirect_uri=cfg.auth0.callback_url)

def handle_callback():
    token = auth0.authorize_access_token()
    session['user'] = token['userinfo']
    return redirect('/index')

def handle_logout():
    session.clear()
    cfg = current_app.config["APP_CFG"]
    return redirect(
        f'https://{cfg.auth0.domain}/v2/logout?returnTo={url_for("home", _external=True)}&client_id={cfg.auth0.client_id}'
    )