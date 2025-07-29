from flask import flash, make_response, redirect, render_template, request, session
from papyrus.auth import requires_auth
from weasyprint import HTML, CSS

def register_routes(app):
    @app.route("/")
    def home():
        return "<h2>Welcome to Papyrus</h2>"
    
    @app.route("/test-session")
    def test_session():
        session["foo"] = "bar"
        return f"Session says: {session.get('foo')}"


    @app.route("/index", methods=["GET"])
    @requires_auth
    def index():
        form_data = {} 
        delivery_list = session.get("delivery_list", [])
        return render_template("index.html", delivery_list=delivery_list, form_data=form_data)

    @app.route("/index", methods=["POST"])
    @requires_auth
    def handle_submit():
        form_data = {}
        action = request.form.get("action")
        delivery_list = session.get("delivery_list", [])

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
            session["delivery_list"] = delivery_list

        elif action == "clear":
            form_data = {}

        elif action == "clear_list":
            session["delivery_list"] = []

        return render_template("index.html", delivery_list=session.get("delivery_list", []), form_data=form_data)


    @app.route("/generate_pdf", methods=["POST"])
    @requires_auth
    def generate_pdf():
        delivery_list = session.get("delivery_list", [])
        total_sum = sum(item["total"] for item in delivery_list)
        html = render_template("report.html", delivery_list=delivery_list, total_sum=total_sum)
        pdf = HTML(string=html).write_pdf(stylesheets=[CSS('static/style.css')])

        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'inline; filename=invoice.pdf'
        return response