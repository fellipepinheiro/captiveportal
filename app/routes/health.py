from flask import Blueprint, jsonify, request, abort
from app.extensions import db

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    """Health-check leve — expõe apenas status ok/degraded.
    Não retorna informações de versão, stack ou detalhes do DB.
    """
    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    status = 200 if db_ok else 503
    # Retorna o mínimo necessário para o load balancer / monitor
    return jsonify({"status": "ok" if db_ok else "degraded"}), status
