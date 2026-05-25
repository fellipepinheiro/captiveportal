import csv
import io
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, Response
)
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db, limiter
from app.models import Visitor, PortalSession, AdminUser

bp = Blueprint("admin", __name__)


@bp.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/login.html")


@bp.post("/login")
@limiter.limit("10 per minute")
def login_post():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    user = AdminUser.query.filter_by(username=username, is_active=True).first()
    if user and user.check_password(password):
        login_user(user)
        return redirect(url_for("admin.dashboard"))
    flash("Credenciais invalidas.", "error")
    return redirect(url_for("admin.login"))


@bp.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("admin.login"))


@bp.get("/")
@login_required
def dashboard():
    total_visitors = Visitor.query.count()
    total_sessions = PortalSession.query.count()
    authorized_sessions = PortalSession.query.filter_by(authorized=True).count()
    recent = (
        PortalSession.query
        .order_by(PortalSession.created_at.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "admin/dashboard.html",
        total_visitors=total_visitors,
        total_sessions=total_sessions,
        authorized_sessions=authorized_sessions,
        recent=recent,
    )


@bp.get("/visitantes")
@login_required
def visitors():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    query = Visitor.query.order_by(Visitor.created_at.desc())
    if q:
        query = query.filter(
            (Visitor.full_name.ilike(f"%{q}%")) | (Visitor.email.ilike(f"%{q}%"))
        )
    pagination = query.paginate(page=page, per_page=25)
    return render_template("admin/visitors.html", pagination=pagination, q=q)


@bp.get("/visitantes/export")
@login_required
def export_visitors():
    visitors_list = Visitor.query.order_by(Visitor.created_at.desc()).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Nome", "E-mail", "Celular", "Ativo", "Cadastrado em"])
    for v in visitors_list:
        w.writerow([v.id, v.full_name, v.email, v.mobile, v.is_active, v.created_at])
    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=visitantes.csv"},
    )
