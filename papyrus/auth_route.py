from flask import app
from papyrus.auth import handle_callback, handle_login, handle_logout

@app.route('/login')
def login():
    return handle_login()

@app.route('/callback')
def callback():
    return handle_callback()

@app.route('/logout')
def logout():
    return handle_logout()