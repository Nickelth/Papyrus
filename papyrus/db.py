from flask import g
import psycopg2
import os

def get_conn():
    if "conn" not in g:
        g.conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT") or "5432"
        )
    return g.conn

def init_db(app):
    @app.teardown_appcontext
    def close_conn(exception=None):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()
