from flask import g, current_app

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
