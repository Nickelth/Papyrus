from flask import Flask, make_response, render_template, request
from weasyprint import HTML

app = Flask(__name__)

@app.route("/")
def home():
    return "<h2>Welcome to Papyrus DEV</h2>"

@app.route("/index")
def report():
    data = {
        "title": "帳票タイトル",
        "name": "田中 太郎",
        "items": [
            {"name": "ホッチキス", "price": 300},
            {"name": "コピー用紙", "price": 500},
            {"name": "USBメモリ", "price": 1200},
        ]
    }
    return render_template("report.html", data=data)

@app.route("/generate_pdf", methods=["POST"])
def generate_pdf():
    # フォームから渡されたデータ
    data = {
        "title": "納品書",
        "name": "田中 太郎",
        "items": [
            {"name": "USBメモリ", "price": 1200},
            {"name": "LANケーブル", "price": 800},
            {"name": "ディスプレイ", "price": 24000},
        ]
    }

    html = render_template("report.html", data=data)
    pdf = HTML(string=html).write_pdf()

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=invoice.pdf'
    return response

if __name__ == "__main__":
    app.run(debug=True)
