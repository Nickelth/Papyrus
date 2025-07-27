from flask import Flask, flash, jsonify, make_response, redirect, render_template, request
from weasyprint import HTML, CSS
from dotenv import load_dotenv
import os
import psycopg2

load_dotenv()

def get_conn():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT") or "5432"
    )

app = Flask(__name__)
delivery_list = []

@app.route("/")
def home():
    return "<h2>Welcome to Papyrus Master</h2>"

@app.route("/index")
def index():
    form_data = {} 
    return render_template("index.html", delivery_list=delivery_list, form_data=form_data)

@app.route("/index", methods=["POST"])
def handle_submit():
    global delivery_list
    form_data = {}
    action = request.form.get("action")
    if action == "add":
        try:
            sku = request.form["sku"].strip()
            name = request.form["name"].strip()
            qty = int(request.form["qty"])
            unit_price = int(request.form["unit_price"])
            note = request.form.get("note", "").strip()

            if not sku or not name:
                raise ValueError("商品コード・商品名は必須です")
            if qty <= 0 or unit_price <= 0:
                raise ValueError("数量・単価は1以上の数字を入力してください")

        except (ValueError, KeyError) as e:
            flash(str(e), "danger")
            return redirect("/index")

        item = {
            "sku": sku,
            "name": name,
            "qty": qty,
            "unit_price": unit_price,
            "total": qty*unit_price,
            "note": note
        }
        
        delivery_list.append(item)
        form_data = {}

    elif action == "clear":
        form_data = {}

    elif action == "clear_list":
        delivery_list = []

    else:
        form_data = {}

    return render_template("index.html", delivery_list=delivery_list, form_data=form_data)

@app.route("/generate_pdf", methods=["POST"])
def generate_pdf():
    # フォームから渡されたデータ
    '''
    data = {
        "title": "納　品　書",
        "name": "田中 太郎",
        "total": 407957393,
        "items": [
            {"name": "ホッチキス", "qty": "2 個", "unit_price": 300, "total": 600},
            {"name": "コピー用紙", "qty": "3 枚", "unit_price": 500, "total": 1500},
            {"name": "USBメモリ", "qty": "4 個", "unit_price": 1200, "total": 6000},
            {"name": "〇〇〇〇〇　サンプル　タイプA", "qty": "12,345,678 個数", "unit_price": 10, "total": 123456780},
            {"name": "システム機器（自動調整タイプ）", "qty": "2 台", "unit_price": 123456789, "total": 246913578, "note": "担当：〇〇"},
            {"name": "システムの取付作業", "qty": "3 人", "unit_price": 30000, "total": 90000},
            {"name": "システムの操作説明　講習会", "qty": "40 個数", "unit_price": 4000, "total": 160000},
            {"name": "□□□の素材（××を含む）", "qty": "50 Kg", "unit_price": 5000, "total": 250000},
        ]
    }'''

    total_sum = sum(item["total"] for item in delivery_list)
    html = render_template("report.html", delivery_list=delivery_list, total_sum=total_sum)
    pdf = HTML(string=html).write_pdf(stylesheets=[CSS('static/style.css')])

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=invoice.pdf'
    return response

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
