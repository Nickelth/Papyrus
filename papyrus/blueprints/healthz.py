from flask import Blueprint, jsonify
import logging; log=logging.getLogger("papyrus")
bp = Blueprint("healthz", __name__)
@bp.get("/healthz")
def healthz(): 
    log.info("healthz ok", extra={"route":"/healthz"})
    return jsonify({"ok": True}), 200
