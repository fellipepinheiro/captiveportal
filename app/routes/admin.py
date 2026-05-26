import csv
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, Response, jsonify
)
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db, limiter
from app.models import Visitor, PortalSession, AdminUser
from app.models.site_config import SiteConfig

bp = Blueprint("admin", __name__)

UPLOAD_FOLDER = Path("app/static/uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "svg", "webp"}
MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB

_DEFAULT_CFG = {
    "portal_title": "Wi-Fi Visitantes",
    "portal_welcome": "Identifique-se para acessar a internet.",
    "portal_btn_color": "#0f766e",
    "portal_accent": "#14b8a6",
    "portal_bg_from": "#0f172a",
    "portal_bg_via": "#1e1b4b",
    "portal_bg_to": "#0f172a",
}


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _load_cfg() -> dict:
    cfg = dict(_DEFAULT_CFG)
    for key in _DEFAULT_CFG:
        val = SiteConfig.get(key)
        if val is not None:
            cfg[key] = val
    cfg['logo_title'] = SiteConfig.get('logo_title') or ''
    return cfg


# ─── Auth ────────────────────────────────────────────────────────────────────────────

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


# ─── Dashboard ───────────────────────────────────────────────────────────────────

@bp.get("/")
@login_required
def dashboard():
    total_visitors = Visitor.query.count()
    total_sessions = PortalSession.query.count()
    authorized_sessions = PortalSession.query.filter_by(authorized=True).count()
    auth_rate = round((authorized_sessions / total_sessions * 100) if total_sessions else 0, 1)
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
        auth_rate=auth_rate,
        recent=recent,
    )


# ─── Visitors ────────────────────────────────────────────────────────────────────

@bp.get("/visitantes")
@login_required
def visitors():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    show_blocked = request.args.get("blocked", "") == "1"
    query = Visitor.query.order_by(Visitor.created_at.desc())
    if q:
        query = query.filter(
            (Visitor.full_name.ilike(f"%{q}%")) | (Visitor.email.ilike(f"%{q}%"))
        )
    if show_blocked:
        query = query.filter(Visitor.is_blocked == True)
    pagination = query.paginate(page=page, per_page=25)
    return render_template("admin/visitors.html", pagination=pagination, q=q, show_blocked=show_blocked)


@bp.post("/visitantes/<int:vid>/bloquear")
@login_required
def visitor_block(vid: int):
    visitor = Visitor.query.get_or_404(vid)
    reason = request.form.get("reason", "").strip() or "Bloqueado pelo administrador"
    visitor.is_blocked = True
    visitor.block_reason = reason
    db.session.commit()
    flash(f"Visitante '{visitor.full_name}' bloqueado.", "success")
    return redirect(url_for("admin.visitors"))


@bp.post("/visitantes/<int:vid>/desbloquear")
@login_required
def visitor_unblock(vid: int):
    visitor = Visitor.query.get_or_404(vid)
    visitor.is_blocked = False
    visitor.block_reason = None
    db.session.commit()
    flash(f"Visitante '{visitor.full_name}' desbloqueado.", "success")
    return redirect(url_for("admin.visitors"))


@bp.get("/visitantes/export")
@login_required
def export_visitors():
    visitors_list = Visitor.query.order_by(Visitor.created_at.desc()).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "Nome", "E-mail", "Celular", "CPF", "Visitas", "Último acesso", "Bloqueado", "Cadastrado em"])
    for v in visitors_list:
        w.writerow([
            v.id, v.full_name, v.email, v.mobile, v.cpf,
            v.visit_count or 0,
            v.last_seen.isoformat() if v.last_seen else "",
            "Sim" if v.is_blocked else "Não",
            v.created_at,
        ])
    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=visitantes.csv"},
    )


# ─── Reports ─────────────────────────────────────────────────────────────────────

@bp.get("/relatorios")
@login_required
def reports():
    return render_template("admin/reports.html")


@bp.get("/relatorios/dados")
@login_required
def reports_data():
    from sqlalchemy import func, cast, Date, case as sa_case

    days = min(int(request.args.get("days", 30)), 365)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # SA 2.x: case(condition, value, else_=fallback)
    auth_expr = func.sum(
        sa_case(
            (PortalSession.authorized == True, 1),
            else_=0,
        )
    )

    sessions_by_day = (
        db.session.query(
            cast(PortalSession.created_at, Date).label("day"),
            func.count().label("total"),
            auth_expr.label("auth"),
        )
        .filter(PortalSession.created_at >= since)
        .group_by(cast(PortalSession.created_at, Date))
        .order_by(cast(PortalSession.created_at, Date))
        .all()
    )

    visitors_by_day = (
        db.session.query(
            cast(Visitor.created_at, Date).label("day"),
            func.count().label("total"),
        )
        .filter(Visitor.created_at >= since)
        .group_by(cast(Visitor.created_at, Date))
        .order_by(cast(Visitor.created_at, Date))
        .all()
    )

    date_range   = [(since + timedelta(days=i)).date() for i in range(days + 1)]
    sessions_map = {str(r.day): (int(r.total), int(r.auth or 0)) for r in sessions_by_day}
    visitors_map = {str(r.day): int(r.total) for r in visitors_by_day}

    labels        = [d.strftime("%d/%m") for d in date_range]
    sessions_data = [sessions_map.get(str(d), (0, 0))[0] for d in date_range]
    auth_data     = [sessions_map.get(str(d), (0, 0))[1] for d in date_range]
    new_vis_data  = [visitors_map.get(str(d), 0) for d in date_range]

    total_s = sum(sessions_data)
    total_a = sum(auth_data)
    total_v = sum(new_vis_data)
    rate    = round(total_a / total_s * 100, 1) if total_s else 0

    device_rows = (
        db.session.query(PortalSession.device_type, func.count().label("n"))
        .filter(PortalSession.created_at >= since)
        .group_by(PortalSession.device_type)
        .all()
    )
    device_data = [{"name": r.device_type or "Desconhecido", "value": r.n} for r in device_rows]

    os_rows = (
        db.session.query(PortalSession.os_hint, func.count().label("n"))
        .filter(PortalSession.created_at >= since)
        .group_by(PortalSession.os_hint)
        .all()
    )
    os_data = [{"name": r.os_hint or "Desconhecido", "value": r.n} for r in os_rows]

    return jsonify({
        "labels":       labels,
        "sessions":     sessions_data,
        "authorized":   auth_data,
        "new_visitors": new_vis_data,
        "totals": {
            "sessions":     total_s,
            "authorized":   total_a,
            "new_visitors": total_v,
            "auth_rate":    rate,
        },
        "device_data": device_data,
        "os_data":     os_data,
    })


# ─── Integrations ───────────────────────────────────────────────────────────────

@bp.get("/integracoes")
@login_required
def integrations():
    webhook_url     = SiteConfig.get("webhook_url", "")
    webhook_secret  = SiteConfig.get("webhook_secret", "")
    webhook_enabled = SiteConfig.get("webhook_enabled", "false") == "true"
    return render_template(
        "admin/integrations.html",
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
        webhook_enabled=webhook_enabled,
    )


@bp.post("/integracoes/salvar")
@login_required
def integrations_save():
    SiteConfig.set("webhook_url",     request.form.get("webhook_url", "").strip())
    SiteConfig.set("webhook_secret",  request.form.get("webhook_secret", "").strip())
    SiteConfig.set("webhook_enabled", "true" if request.form.get("webhook_enabled") else "false")
    db.session.commit()
    flash("Configurações de integração salvas.", "success")
    return redirect(url_for("admin.integrations"))


@bp.post("/integracoes/testar")
@login_required
def integrations_test():
    import hashlib, hmac, json, urllib.request

    url    = SiteConfig.get("webhook_url", "").strip()
    secret = SiteConfig.get("webhook_secret", "changeme")
    if not url:
        flash("Configure a URL do webhook primeiro.", "error")
        return redirect(url_for("admin.integrations"))

    payload = {
        "event": "webhook_test",
        "message": "Teste de integração do Captive Portal",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    body = json.dumps(payload, default=str).encode()
    sig  = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    try:
        req = urllib.request.Request(
            url, data=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": f"sha256={sig}",
                "X-Webhook-Event": "webhook_test",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            flash(f"Webhook enviado com sucesso (HTTP {resp.status}).", "success")
    except Exception as exc:
        flash(f"Falha ao enviar webhook: {exc}", "error")
    return redirect(url_for("admin.integrations"))


# ─── Appearance ──────────────────────────────────────────────────────────────────

@bp.get("/aparencia")
@login_required
def settings_appearance():
    cfg = _load_cfg()
    logo_path = UPLOAD_FOLDER / "logo.png"
    has_logo = logo_path.exists()
    return render_template(
        "admin/settings_appearance.html",
        cfg=cfg,
        has_logo=has_logo,
    )


@bp.post("/aparencia/salvar")
@login_required
def settings_appearance_save():
    keys = ["portal_title", "portal_welcome", "portal_btn_color",
            "portal_accent", "portal_bg_from", "portal_bg_via", "portal_bg_to"]
    for key in keys:
        val = request.form.get(key, "").strip()
        if val:
            SiteConfig.set(key, val)
    db.session.commit()
    flash("Configuracoes salvas com sucesso.", "success")
    return redirect(url_for("admin.settings_appearance"))


@bp.post("/aparencia/logo-title")
@login_required
def settings_logo_title_save():
    logo_title = request.form.get("logo_title", "").strip()
    SiteConfig.set("logo_title", logo_title)
    db.session.commit()
    flash("Título da logo salvo com sucesso.", "success")
    return redirect(url_for("admin.settings_appearance"))


@bp.post("/aparencia/logo")
@login_required
def upload_logo():
    file = request.files.get("logo")
    if not file or file.filename == "":
        flash("Nenhum arquivo selecionado.", "error")
        return redirect(url_for("admin.settings_appearance"))
    if not _allowed(file.filename):
        flash("Formato invalido. Use PNG, JPG, SVG ou WEBP.", "error")
        return redirect(url_for("admin.settings_appearance"))
    data = file.read()
    if len(data) > MAX_LOGO_BYTES:
        flash("Arquivo muito grande. Maximo 2 MB.", "error")
        return redirect(url_for("admin.settings_appearance"))
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    logo_path = UPLOAD_FOLDER / "logo.png"
    logo_path.write_bytes(data)
    SiteConfig.set("custom_logo_url", "/static/uploads/logo.png")
    db.session.commit()
    flash("Logo atualizada com sucesso.", "success")
    return redirect(url_for("admin.settings_appearance"))


@bp.post("/aparencia/logo/remover")
@login_required
def remove_logo():
    logo_path = UPLOAD_FOLDER / "logo.png"
    if logo_path.exists():
        logo_path.unlink()
    SiteConfig.set("custom_logo_url", "")
    db.session.commit()
    flash("Logo removida.", "success")
    return redirect(url_for("admin.settings_appearance"))


# ─── Admin Users ─────────────────────────────────────────────────────────────────

@bp.get("/usuarios")
@login_required
def users():
    all_users = AdminUser.query.order_by(AdminUser.created_at).all()
    return render_template("admin/users.html", users=all_users, admin=current_user)


@bp.post("/usuarios/criar")
@login_required
def user_create():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if not username or len(password) < 8:
        flash("Username obrigatorio e senha deve ter ao menos 8 caracteres.", "error")
        return redirect(url_for("admin.users"))
    if AdminUser.query.filter_by(username=username).first():
        flash(f"Username '{username}' ja existe.", "error")
        return redirect(url_for("admin.users"))
    user = AdminUser(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f"Usuario '{username}' criado com sucesso.", "success")
    return redirect(url_for("admin.users"))


@bp.post("/usuarios/<int:uid>/toggle")
@login_required
def user_toggle(uid: int):
    user = AdminUser.query.get_or_404(uid)
    if user.id == current_user.id:
        flash("Voce nao pode desativar sua propria conta.", "error")
        return redirect(url_for("admin.users"))
    user.is_active = not user.is_active
    db.session.commit()
    status = "ativado" if user.is_active else "desativado"
    flash(f"Usuario '{user.username}' {status}.", "success")
    return redirect(url_for("admin.users"))


@bp.post("/usuarios/<int:uid>/senha")
@login_required
def user_password(uid: int):
    user = AdminUser.query.get_or_404(uid)
    new_password = request.form.get("new_password", "")
    if len(new_password) < 8:
        flash("A senha deve ter ao menos 8 caracteres.", "error")
        return redirect(url_for("admin.users"))
    user.set_password(new_password)
    db.session.commit()
    flash(f"Senha de '{user.username}' alterada.", "success")
    return redirect(url_for("admin.users"))


@bp.post("/usuarios/<int:uid>/excluir")
@login_required
def user_delete(uid: int):
    user = AdminUser.query.get_or_404(uid)
    if user.id == current_user.id:
        flash("Voce nao pode excluir sua propria conta.", "error")
        return redirect(url_for("admin.users"))
    db.session.delete(user)
    db.session.commit()
    flash(f"Usuario '{user.username}' excluido.", "success")
    return redirect(url_for("admin.users"))
