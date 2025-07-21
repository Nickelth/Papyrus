from flask import Flask, make_response, render_template, request
from weasyprint import HTML, CSS

app = Flask(__name__)
delivery_list = []

@app.route("/")
def home():
    return "<h2>Welcome to Papyrus DEV</h2>"

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
        item = {
            "sku": request.form["sku"],
            "name": request.form["name"],
            "qty": int(request.form["qty"]),
            "unit_price": int(request.form["unit_price"]),
            "total": int(request.form["unit_price"])*int(request.form["qty"]),
            "note": request.form["note"]
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

if __name__ == "__main__":
    app.run(debug=True)
