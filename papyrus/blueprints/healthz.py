from flask import Blueprint, jsonify
bp = Blueprint("healthz", __name__)
@bp.get("/healthz")
def healthz(): return jsonify(ok=True), 200
