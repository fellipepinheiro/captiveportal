from flask import Blueprint, jsonify, redirect, url_for
from app.extensions import db

bp = Blueprint("health", __name__)


@bp.get("/")
def root():
    """Redireciona a raiz do site para o portal de acesso Wi-Fi."""
    return redirect(url_for("portal.entry"))


@bp.get("/health")
def health():
    """Health-check leve — expõe apenas status ok/degraded."""
    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    status = 200 if db_ok else 503
    return jsonify({"status": "ok" if db_ok else "degraded"}), status
