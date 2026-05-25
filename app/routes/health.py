from flask import Blueprint, jsonify
from app.extensions import db

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    status = 200 if db_ok else 503
    return jsonify({"status": "ok" if db_ok else "degraded", "db": db_ok}), status
