# blueprint/dbcheck.py
from flask import Blueprint, jsonify, current_app
import logging, psycopg2
log=logging.getLogger("papyrus")
bp = Blueprint("dbcheck", __name__)

def _do_insert(conn):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO papyrus_schema.products (sku,name,unit_price,note)
        VALUES ('SKU-APP','health',0,'probe')
        ON CONFLICT (sku) DO NOTHING;
    """)
    inserted = (cur.rowcount == 1)
    conn.commit()
    return inserted

@bp.get("/dbcheck")
def dbcheck():
    pool = current_app.config.get("DB_POOL")
    if pool is None:
        log.error("DB_POOL missing", extra={"route":"/dbcheck"})
        return jsonify({"ok": False, "error": "DB_POOL missing"}), 500

    # 1回だけリトライ：失効コネクションを閉じて新規を取り直す
    for attempt in (1, 2):
        conn = pool.getconn()
        try:
            inserted = _do_insert(conn)
            log.info("dbcheck ok", extra={"route":"/dbcheck","inserted":inserted})
            return jsonify({"ok": True, "inserted": inserted}), 200
        except psycopg2.OperationalError as e:
            try: conn.rollback()
            except Exception: pass
            # このコネクションは壊れているのでプールから除外
            pool.putconn(conn, close=True)
            log.error("dbcheck operational error; will retry" if attempt==1 else "dbcheck operational error; giving up",
                      extra={"route":"/dbcheck","err":str(e),"attempt":attempt})
            if attempt == 2:
                return jsonify({"ok": False, "error": "dbcheck failed (operational)"}), 500
            continue
        except Exception as e:
            try: conn.rollback()
            except Exception: pass
            pool.putconn(conn)  # 通常返却
            log.error("dbcheck failed", extra={"route":"/dbcheck","err":str(e)})
            return jsonify({"ok": False, "error": "dbcheck failed"}), 500
        else:
            pool.putconn(conn)
    # 到達しない