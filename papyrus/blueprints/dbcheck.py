from flask import Blueprint, jsonify, current_app
import logging; log=logging.getLogger("papyrus")
bp = Blueprint("dbcheck", __name__)
@bp.get("/dbcheck")
def dbcheck():
    pool = current_app.config["DB_POOL"]
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO papyrus_schema.products (sku,name,unit_price,note) VALUES ('SKU-APP','health',0,'probe') ON CONFLICT (sku) DO NOTHING;")
        conn.commit()
        log.info("dbcheck ok", extra={"route":"/dbcheck"})
        return jsonify({"inserted": True}), 200
    finally:
        pool.putconn(conn)