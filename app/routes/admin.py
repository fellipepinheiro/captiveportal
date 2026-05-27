import csv
import io
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, Response, jsonify, current_app, send_from_directory
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db, limiter, csrf
from app.models import Visitor, PortalSession, AdminUser
from app.models.site_config import SiteConfig

bp = Blueprint("admin", __name__)

UPLOAD_FOLDER      = Path("app/static/uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_LOGO_BYTES     = 2 * 1024 * 1024
HEX_COLOR_RE       = re.compile(r'^#[0-9A-Fa-f]{6}$')

_DEFAULT_CFG = {
    "portal_title":    "Wi-Fi Visitantes",
    "portal_welcome":  "Identifique-se para acessar a internet.",
    "portal_btn_color": "#0f766e",
    "portal_accent":   "#14b8a6",
    "portal_bg_from":  "#0f172a",
    "portal_bg_via":   "#1e1b4b",
    "portal_bg_to":    "#0f172a",
}


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _valid_hex(value: str) -> bool:
    return bool(HEX_COLOR_RE.match(value))


def _load_cfg() -> dict:
    cfg = dict(_DEFAULT_CFG)
    for key in _DEFAULT_CFG:
        val = SiteConfig.get(key)
        if val is not None:
            cfg[key] = val
    cfg['logo_title'] = SiteConfig.get('logo_title') or ''
    return cfg


# ─── Media (logo pública) ────────────────────────────────────────────────────

@bp.get("/media/<path:filename>")
@csrf.exempt
def serve_media(filename):
    safe = secure_filename(filename)
    return send_from_directory(UPLOAD_FOLDER.resolve(), safe)


# ─── Auth ────────────────────────────────────────────────────────────────────

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
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()
        login_user(user, remember=False)
        return redirect(url_for("admin.dashboard"))
    flash("Credenciais inválidas.", "error")
    return redirect(url_for("admin.login"))


@bp.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("admin.login"))


# ─── Dashboard ───────────────────────────────────────────────────────────────

@bp.get("/")
@login_required
def dashboard():
    total_visitors       = Visitor.query.count()
    total_sessions       = PortalSession.query.count()
    authorized_sessions  = PortalSession.query.filter_by(authorized=True).count()
    auth_rate = round((authorized_sessions / total_sessions * 100) if total_sessions else 0, 1)
    recent = (
        PortalSession.query
        .order_by(PortalSession.created_at.desc())
        .limit(20).all()
    )
    return render_template(
        "admin/dashboard.html",
        total_visitors=total_visitors,
        total_sessions=total_sessions,
        authorized_sessions=authorized_sessions,
        auth_rate=auth_rate,
        recent=recent,
    )


# ─── Visitors ────────────────────────────────────────────────────────────────

@bp.get("/visitantes")
@login_required
def visitors():
    page         = request.args.get("page", 1, type=int)
    q            = request.args.get("q", "").strip()
    show_blocked = request.args.get("blocked", "") == "1"
    query        = Visitor.query.order_by(Visitor.created_at.desc())
    if q:
        query = query.filter(
            (Visitor.full_name.ilike(f"%{q}%")) |
            (Visitor.email.ilike(f"%{q}%"))
        )
    if show_blocked:
        query = query.filter(Visitor.is_blocked == True)
    pagination = query.paginate(page=page, per_page=25)
    return render_template(
        "admin/visitors.html",
        pagination=pagination,
        q=q,
        show_blocked=show_blocked,
    )


@bp.post("/visitantes/<int:vid>/bloquear")
@login_required
def visitor_block(vid: int):
    visitor = Visitor.query.get_or_404(vid)
    reason  = request.form.get("reason", "").strip()[:200] or "Bloqueado pelo administrador"
    visitor.is_blocked   = True
    visitor.block_reason = reason
    db.session.commit()
    flash(f"Visitante '{visitor.full_name}' bloqueado.", "success")
    return redirect(url_for("admin.visitors"))


@bp.post("/visitantes/<int:vid>/desbloquear")
@login_required
def visitor_unblock(vid: int):
    visitor = Visitor.query.get_or_404(vid)
    visitor.is_blocked   = False
    visitor.block_reason = None
    db.session.commit()
    flash(f"Visitante '{visitor.full_name}' desbloqueado.", "success")
    return redirect(url_for("admin.visitors"))


@bp.get("/visitantes/export")
@login_required
def export_visitors():
    visitors_list = Visitor.query.order_by(Visitor.created_at.desc()).all()
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["ID", "Nome", "E-mail", "Celular", "CPF",
                "Visitas", "Último acesso", "Bloqueado", "Cadastrado em"])
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
        headers={
            "Content-Disposition": "attachment; filename=visitantes.csv",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ─── Reports ─────────────────────────────────────────────────────────────────

@bp.get("/relatorios")
@login_required
def reports():
    return render_template("admin/reports.html")


@bp.get("/relatorios/dados")
@login_required
def reports_data():
    from sqlalchemy import func, cast, Date, case as sa_case

    try:
        days = max(1, min(int(request.args.get("days", 30)), 365))
    except (ValueError, TypeError):
        days = 30

    since = datetime.now(timezone.utc) - timedelta(days=days)

    auth_expr = func.sum(
        sa_case((PortalSession.authorized == True, 1), else_=0)
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
        .group_by(PortalSession.device_type).all()
    )
    device_data = [{"name": r.device_type or "Desconhecido", "value": r.n} for r in device_rows]

    os_rows = (
        db.session.query(PortalSession.os_hint, func.count().label("n"))
        .filter(PortalSession.created_at >= since)
        .group_by(PortalSession.os_hint).all()
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


# ─── Integrations ────────────────────────────────────────────────────────────

@bp.get("/integracoes")
@login_required
def integrations():
    return render_template(
        "admin/integrations.html",
        webhook_url=SiteConfig.get("webhook_url", ""),
        webhook_secret=SiteConfig.get("webhook_secret", ""),
        webhook_enabled=SiteConfig.get("webhook_enabled", "false") == "true",
        unifi_enabled=SiteConfig.get("unifi_enabled", "false") == "true",
        unifi_host=SiteConfig.get("unifi_host", "https://192.168.1.1"),
        unifi_api_key=SiteConfig.get("unifi_api_key", ""),
        unifi_site=SiteConfig.get("unifi_site", "default"),
        unifi_minutes=SiteConfig.get("unifi_minutes", "480"),
    )


@bp.post("/integracoes/salvar")
@login_required
def integrations_save():
    webhook_url = request.form.get("webhook_url", "").strip()
    if webhook_url and not re.match(r'^https?://', webhook_url):
        flash("URL do webhook deve começar com http:// ou https://", "error")
        return redirect(url_for("admin.integrations"))
    SiteConfig.set("webhook_url",     webhook_url)
    SiteConfig.set("webhook_secret",  request.form.get("webhook_secret", "").strip())
    SiteConfig.set("webhook_enabled", "true" if request.form.get("webhook_enabled") else "false")

    unifi_host = request.form.get("unifi_host", "").strip().rstrip("/")
    if unifi_host and not re.match(r'^https?://', unifi_host):
        flash("Host UniFi deve começar com https://", "error")
        return redirect(url_for("admin.integrations"))
    SiteConfig.set("unifi_enabled",  "true" if request.form.get("unifi_enabled") else "false")
    SiteConfig.set("unifi_host",     unifi_host)
    SiteConfig.set("unifi_api_key",  request.form.get("unifi_api_key", "").strip())
    SiteConfig.set("unifi_site",     request.form.get("unifi_site", "default").strip() or "default")
    try:
        mins = max(1, min(int(request.form.get("unifi_minutes", "480")), 44640))
    except (ValueError, TypeError):
        mins = 480
    SiteConfig.set("unifi_minutes",  str(mins))

    db.session.commit()
    flash("Configurações de integração salvas.", "success")
    return redirect(url_for("admin.integrations"))


@bp.post("/integracoes/testar")
@login_required
@limiter.limit("5 per minute")
def integrations_test():
    import hashlib, hmac, json
    import requests as req_lib
    import warnings

    url    = SiteConfig.get("webhook_url", "").strip()
    secret = SiteConfig.get("webhook_secret", "changeme")

    if not url:
        flash("Configure a URL do webhook primeiro.", "error")
        return redirect(url_for("admin.integrations"))

    verify_ssl = os.environ.get("UNIFI_VERIFY_SSL", "true").lower() != "false"

    payload = {
        "event":     "webhook_test",
        "message":   "Teste de integração do Captive Portal",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    body = json.dumps(payload, default=str).encode()
    sig  = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    try:
        if not verify_ssl:
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        resp = req_lib.post(
            url,
            data=body,
            headers={
                "Content-Type":       "application/json",
                "X-Webhook-Signature": f"sha256={sig}",
                "X-Webhook-Event":    "webhook_test",
            },
            timeout=8,
            verify=verify_ssl,
        )
        flash(f"Webhook enviado (HTTP {resp.status_code}).", "success" if resp.ok else "error")
    except Exception as exc:
        flash(f"Falha ao enviar webhook: {exc}", "error")
    return redirect(url_for("admin.integrations"))


@bp.post("/integracoes/testar-unifi")
@login_required
@limiter.limit("5 per minute")
def integrations_test_unifi():
    import requests as req_lib
    import warnings

    host    = SiteConfig.get("unifi_host", "").strip().rstrip("/")
    api_key = SiteConfig.get("unifi_api_key", "").strip()

    if not host or not api_key:
        flash("Configure o Host e a API Key do UniFi antes de testar.", "error")
        return redirect(url_for("admin.integrations"))

    verify_ssl = os.environ.get("UNIFI_VERIFY_SSL", "false").lower() != "true"

    try:
        if not verify_ssl:
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        resp = req_lib.get(
            f"{host}/proxy/network/integration/v1/sites",
            headers={"X-API-KEY": api_key, "Accept": "application/json"},
            timeout=8,
            verify=not verify_ssl,
        )
        if resp.status_code == 200:
            sites = resp.json().get("data", [])
            names = ", ".join(s.get("name", s.get("id", "?")) for s in sites[:5]) or "(nenhum)"
            flash(f"Conexão UniFi OK! Sites encontrados: {names}", "success")
        elif resp.status_code == 401:
            flash("UniFi recusou a API Key (HTTP 401). Verifique se a chave está correta.", "error")
        elif resp.status_code == 403:
            flash("UniFi negou acesso (HTTP 403). Verifique as permissões da API Key.", "error")
        else:
            flash(f"UniFi respondeu HTTP {resp.status_code}: {resp.text[:200]}", "error")
    except Exception as exc:
        flash(f"Falha ao conectar no UniFi: {exc}", "error")
    return redirect(url_for("admin.integrations"))


def unifi_authorize_client(
    client_mac: str,
    client_ip: str | None = None,
    minutes: int | None = None,
) -> tuple[bool, str]:
    import requests as req_lib
    import warnings

    if SiteConfig.get("unifi_enabled", "false") != "true":
        return False, "Integração UniFi desativada."

    host    = SiteConfig.get("unifi_host", "").strip().rstrip("/")
    api_key = SiteConfig.get("unifi_api_key", "").strip()
    site    = SiteConfig.get("unifi_site", "default").strip() or "default"
    if minutes is None:
        try:
            minutes = int(SiteConfig.get("unifi_minutes", "480"))
        except (ValueError, TypeError):
            minutes = 480

    if not host or not api_key:
        return False, "Host ou API Key do UniFi não configurados."

    verify_ssl = os.environ.get("UNIFI_VERIFY_SSL", "false").lower() != "true"

    payload = {"mac": client_mac, "minutes": minutes}
    if client_ip:
        payload["ip"] = client_ip

    try:
        if not verify_ssl:
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        resp = req_lib.post(
            f"{host}/proxy/network/integration/v1/sites/{site}/guests",
            json=payload,
            headers={
                "X-API-KEY":    api_key,
                "Accept":       "application/json",
                "Content-Type": "application/json",
            },
            timeout=10,
            verify=not verify_ssl,
        )
        if resp.status_code in (200, 201):
            return True, f"Cliente {client_mac} autorizado no UniFi ({minutes} min)."
        else:
            return False, f"UniFi recusou: HTTP {resp.status_code} — {resp.text[:300]}"
    except Exception as exc:
        return False, f"Erro ao comunicar com UniFi: {exc}"


# ─── Appearance ──────────────────────────────────────────────────────────────

@bp.get("/aparencia")
@login_required
def settings_appearance():
    cfg = _load_cfg()
    logo_path = UPLOAD_FOLDER / "logo.png"
    has_logo  = logo_path.exists()
    return render_template(
        "admin/settings_appearance.html",
        cfg=cfg,
        has_logo=has_logo,
    )


@bp.post("/aparencia/salvar")
@login_required
def settings_appearance_save():
    color_keys = [
        "portal_btn_color", "portal_accent",
        "portal_bg_from", "portal_bg_via", "portal_bg_to",
    ]
    text_keys = ["portal_title", "portal_welcome"]

    for key in text_keys:
        val = request.form.get(key, "").strip()[:200]
        if val:
            SiteConfig.set(key, val)

    for key in color_keys:
        val = request.form.get(key, "").strip()
        if val and _valid_hex(val):
            SiteConfig.set(key, val)
        elif val:
            flash(f"Cor inválida para {key}. Use formato #RRGGBB.", "error")
            return redirect(url_for("admin.settings_appearance"))

    db.session.commit()
    flash("Configurações salvas com sucesso.", "success")
    return redirect(url_for("admin.settings_appearance"))


@bp.post("/aparencia/logo-title")
@login_required
def settings_logo_title_save():
    logo_title = request.form.get("logo_title", "").strip()[:100]
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

    filename = secure_filename(file.filename)
    if not _allowed(filename):
        flash("Formato inválido. Use PNG, JPG ou WEBP.", "error")
        return redirect(url_for("admin.settings_appearance"))

    data = file.read()
    if len(data) > MAX_LOGO_BYTES:
        flash("Arquivo muito grande. Máximo 2 MB.", "error")
        return redirect(url_for("admin.settings_appearance"))

    MAGIC = {
        b'\x89PNG': 'png',
        b'\xff\xd8\xff': 'jpg',
        b'RIFF': 'webp',
    }
    is_image = any(data.startswith(magic) for magic in MAGIC)
    if not is_image:
        flash("Arquivo não reconhecido como imagem válida.", "error")
        return redirect(url_for("admin.settings_appearance"))

    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    logo_path = UPLOAD_FOLDER / "logo.png"
    logo_path.write_bytes(data)
    SiteConfig.set("custom_logo_url", "/admin/media/logo.png")
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


# ─── Admin Users ─────────────────────────────────────────────────────────────

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
    if not username or len(password) < 12:
        flash("Username obrigatório e senha deve ter ao menos 12 caracteres.", "error")
        return redirect(url_for("admin.users"))
    if not re.match(r'^[\w.-]{3,64}$', username):
        flash("Username deve ter entre 3 e 64 caracteres alfanuméricos.", "error")
        return redirect(url_for("admin.users"))
    if AdminUser.query.filter_by(username=username).first():
        flash(f"Username '{username}' já existe.", "error")
        return redirect(url_for("admin.users"))
    user = AdminUser(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f"Usuário '{username}' criado com sucesso.", "success")
    return redirect(url_for("admin.users"))


@bp.post("/usuarios/<int:uid>/toggle")
@login_required
def user_toggle(uid: int):
    user = AdminUser.query.get_or_404(uid)
    if user.id == current_user.id:
        flash("Você não pode desativar sua própria conta.", "error")
        return redirect(url_for("admin.users"))
    user.is_active = not user.is_active
    db.session.commit()
    status = "ativado" if user.is_active else "desativado"
    flash(f"Usuário '{user.username}' {status}.", "success")
    return redirect(url_for("admin.users"))


@bp.post("/usuarios/<int:uid>/senha")
@login_required
def user_password(uid: int):
    user         = AdminUser.query.get_or_404(uid)
    new_password = request.form.get("new_password", "")
    if len(new_password) < 12:
        flash("A senha deve ter ao menos 12 caracteres.", "error")
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
        flash("Você não pode excluir sua própria conta.", "error")
        return redirect(url_for("admin.users"))
    db.session.delete(user)
    db.session.commit()
    flash(f"Usuário '{user.username}' excluído.", "success")
    return redirect(url_for("admin.users"))
