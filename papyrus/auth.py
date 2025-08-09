from flask import session, redirect, url_for, request
from authlib.integrations.flask_client import OAuth
from functools import wraps
import os

oauth = OAuth()
auth0 = None

def init_auth(app):
    app.secret_key = os.environ['FLASK_SECRET_KEY']
    oauth.init_app(app)
    global auth0
    auth0 = oauth.register(
        'auth0',
        client_id=os.environ['AUTH0_CLIENT_ID'],
        client_secret=os.environ['AUTH0_CLIENT_SECRET'],
        client_kwargs={'scope': 'openid profile email'},
        server_metadata_url=f'https://{os.environ["AUTH0_DOMAIN"]}/.well-known/openid-configuration',
        redirect_uri=os.environ['AUTH0_CALLBACK_URL']
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def handle_login():
    return auth0.authorize_redirect(
        redirect_uri=os.environ["AUTH0_CALLBACK_URL"]
    )

def handle_callback():
    token = auth0.authorize_access_token()
    session['user'] = token['userinfo']
    return redirect('/index')

def handle_logout():
    session.clear()
    return redirect(
        f'https://{os.environ["AUTH0_DOMAIN"]}/v2/logout?returnTo={url_for("home", _external=True)}&client_id={os.environ["AUTH0_CLIENT_ID"]}'
    )
