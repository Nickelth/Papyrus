import os
from flask import jsonify, request
import psycopg2
from flask import g

def register_api_routes(app):
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

    @app.teardown_appcontext
    def close_conn(exception=None):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    @app.route("/api/product_by_sku")
    def product_by_sku():
        sku = request.args.get("sku")
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT sku, name, unit_price FROM papyrus_schema.products WHERE sku = %s", (sku,))
        row = cur.fetchone()
        cur.close()
        conn.close()
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
        conn.close()
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