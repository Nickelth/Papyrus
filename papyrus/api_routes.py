from flask import jsonify, request
from papyrus.db import get_conn  # ★ 共有ユーティリティを利用

def register_api_routes(app):
# ★ teardown は db.init_db 側でやるので不要

    @app.route("/api/product_by_sku")
    def product_by_sku():
        sku = request.args.get("sku")
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT sku, name, unit_price FROM papyrus_schema.products WHERE sku = %s", (sku,))
        row = cur.fetchone()
        cur.close()
        # ★ ここでcloseしない。teardownで返却される。
        if row:
            return jsonify({"sku": row[0], "name": row[1], "unit_price": row[2]})
        return jsonify({})


    @app.route("/api/product_by_name")
    def product_by_name():
        sku = request.args.get("name")
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT sku, name, unit_price FROM papyrus_schema.products WHERE name = %s", (sku,))
        row = cur.fetchone()
        cur.close()
        # ★ 同上
        if row:
            return jsonify({"sku": row[0], "name": row[1], "unit_price": row[2]})
        return jsonify({})

    if __name__ == "__main__":
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            print("DB Connection is available.")
            cur.close()
            conn.close()
        except Exception as e:
            print("DB Connection is Failure:", e)

        app.run(debug=True)