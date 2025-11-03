from flask import g, current_app
import os
import psycopg2
from psycopg2 import pool

def get_conn():
    # ★ app.config に入れたプールからコネクションを借りる
    if "conn" not in g:
        pool = current_app.config["DB_POOL"]
        g.conn = pool.getconn()
    return g.conn

def init_db(app):
    @app.teardown_appcontext
    def close_conn(exception=None):
        conn = g.pop("conn", None)
        if conn is not None:
            # ★ 返却（closeではない）
            current_app.config["DB_POOL"].putconn(conn)

def create_pool():
    dsn = (
        f"host={os.environ['PGHOST']} "
        f"port={os.environ.get('PGPORT','5432')} "
        f"dbname={os.environ['PGDATABASE']} "
        f"user={os.environ['PGUSER']} "
        f"password={os.environ['PGPASSWORD']} "
        f"sslmode={os.environ.get('PGSSLMODE','require')}"
    )
    # 可能なら CA 検証も（任意）: sslrootcert=/app/certs/rds-combined-ca-bundle.pem

    # TCP keepalive を有効化（ネットワーク断を早く検知）
    conn_kwargs = dict(
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3
    )

    return pool.SimpleConnectionPool(
        minconn=int(os.getenv("PG_POOL_MIN", "1")),
        maxconn=int(os.getenv("PG_POOL_MAX", "5")),
        dsn=dsn,
        **conn_kwargs
    )