import csv
import io
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, Response, jsonify, current_app, send_from_directory
)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from app.extensions import db, limiter, csrf
from app.models import Visitor, PortalSession, AdminUser, Store, AuditLog
from app.models.site_config import SiteConfig
from app.services.unifi_api import get_unifi_for_store, UnifiAPIError
from app.services.datetime_fmt import fmt_datetime, get_tz
from app.services.validator import format_cpf

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
# Serve o logo via /media/logo.png — roteado pelo nginx-proxy junto com /guest/
# Evita o problema de /static/ não ser roteado pelo proxy reverso.

@bp.get("/media/<path:filename>")
@csrf.exempt
def serve_media(filename):
    """Serve arquivos de upload publicamente via /admin/media/<filename>."""
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


# ─── Sessões ─────────────────────────────────────────────────────────────────

@bp.post("/sessoes/<int:sid>/derrubar")
@login_required
@limiter.limit("30 per minute")
def session_revoke(sid: int):
    from app.services.portal_service import revoke_session

    ps = PortalSession.query.get_or_404(sid)
    if not ps.authorized:
        flash("Essa sessão já não está autorizada.", "error")
        return redirect(request.referrer or url_for("admin.dashboard"))

    store = Store.query.get(ps.store_id) if ps.store_id else None
    ok, msg = revoke_session(ps, store)
    flash(msg, "success" if ok else "error")
    return redirect(request.referrer or url_for("admin.dashboard"))


# ─── Visitors ────────────────────────────────────────────────────────────────

@bp.get("/visitantes")
@login_required
def visitors():
    page         = request.args.get("page", 1, type=int)
    q            = request.args.get("q", "").strip()
    show_blocked = request.args.get("blocked", "") == "1"
    query        = Visitor.query.order_by(Visitor.created_at.desc())
    if q:
        # CPF/telefone sao gravados so com digitos — busca pelo termo normalizado
        digits = re.sub(r"\D", "", q)
        filters = [
            Visitor.full_name.ilike(f"%{q}%"),
            Visitor.email.ilike(f"%{q}%"),
        ]
        if digits:
            filters.append(Visitor.cpf.like(f"%{digits}%"))
            filters.append(Visitor.mobile.like(f"%{digits}%"))
        query = query.filter(or_(*filters))
    if show_blocked:
        query = query.filter(Visitor.is_blocked == True)
    pagination = query.paginate(page=page, per_page=25)
    return render_template(
        "admin/visitors.html",
        pagination=pagination,
        q=q,
        show_blocked=show_blocked,
    )


def _periodo_do_request():
    """Le de/ate da querystring. Padrao: ultimos 30 dias.

    As datas chegam no fuso local (é o que o admin digita) e viram UTC,
    que e como os timestamps estao gravados.
    """
    hoje_local = datetime.now(get_tz()).date()
    try:
        ate = date.fromisoformat(request.args.get("ate", "")) if request.args.get("ate") else hoje_local
    except ValueError:
        ate = hoje_local
    try:
        de = date.fromisoformat(request.args.get("de", "")) if request.args.get("de") else ate - timedelta(days=29)
    except ValueError:
        de = ate - timedelta(days=29)
    if de > ate:
        de, ate = ate, de

    tz = get_tz()
    inicio = datetime.combine(de, time.min, tzinfo=tz).astimezone(timezone.utc)
    # 'ate' e inclusivo: vai ate o fim daquele dia
    fim = datetime.combine(ate + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    return de, ate, inicio, fim


def _extrato_sessoes(visitor_id: int, inicio, fim):
    """Sessoes do visitante no periodo, da mais recente para a mais antiga."""
    return (
        PortalSession.query
        .filter(PortalSession.visitor_id == visitor_id)
        .filter(PortalSession.created_at >= inicio, PortalSession.created_at < fim)
        .order_by(PortalSession.created_at.desc())
        .all()
    )


@bp.get("/visitantes/<int:vid>")
@login_required
def visitor_detail(vid: int):
    """Extrato de conexoes/desconexoes do visitante no periodo."""
    visitor = Visitor.query.get_or_404(vid)
    de, ate, inicio, fim = _periodo_do_request()
    sessoes = _extrato_sessoes(vid, inicio, fim)

    autorizadas = [s for s in sessoes if s.authorized_at]
    minutos = sum(s.duration or 0 for s in autorizadas)
    resumo = {
        "acessos":        len(sessoes),
        "autorizados":    len(autorizadas),
        "nao_concluidos": len(sessoes) - len(autorizadas),
        "em_curso":       sum(1 for s in sessoes if s.is_active),
        "minutos_total":  minutos,
        "minutos_medio":  round(minutos / len(autorizadas)) if autorizadas else 0,
    }
    return render_template(
        "admin/visitor_detail.html",
        visitor=visitor, sessoes=sessoes, resumo=resumo,
        de=de.isoformat(), ate=ate.isoformat(),
    )


@bp.get("/visitantes/<int:vid>/extrato.csv")
@login_required
def visitor_detail_export(vid: int):
    visitor = Visitor.query.get_or_404(vid)
    de, ate, inicio, fim = _periodo_do_request()
    sessoes = _extrato_sessoes(vid, inicio, fim)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Visitante", visitor.full_name])
    w.writerow(["CPF", format_cpf(visitor.cpf)])
    w.writerow(["Período", f"{de.strftime('%d/%m/%Y')} a {ate.strftime('%d/%m/%Y')}"])
    w.writerow([])
    w.writerow(["Loja", "Rede", "Conexão", "Desconexão", "Duração (min)",
                "Dispositivo", "IP", "MAC", "Status"])
    for s in sessoes:
        if s.is_active:
            status = "Em curso"
        elif s.authorized_at:
            status = "Encerrada"
        else:
            status = "Não concluída"
        w.writerow([
            s.store.name if s.store else "",
            s.ssid or "",
            fmt_datetime(s.authorized_at) if s.authorized_at else "",
            fmt_datetime(s.expired_at) if s.expired_at else "",
            s.duration if s.duration is not None else "",
            f"{s.device_type or ''} {s.os_hint or ''}".strip(),
            s.client_ip or "",
            s.client_mac or "",
            status,
        ])
    buf.seek(0)
    nome = re.sub(r"[^\w.-]", "_", visitor.full_name)[:40]
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=extrato_{nome}_{de}_{ate}.csv",
            "X-Content-Type-Options": "nosniff",
        },
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


@bp.post("/visitantes/<int:vid>/excluir")
@login_required
def visitor_delete(vid: int):
    """Exclui o cadastro do visitante (LGPD Art. 18, direito a exclusao).

    Os registros de conexao (portal_sessions) NAO sao apagados: o Marco
    Civil da Internet (Lei 12.965/2014, Art. 15) obriga a guarda desses
    logs. Eles apenas deixam de apontar para o visitante, ficando
    anonimos — sem nome, CPF, telefone ou e-mail associados.
    """
    visitor = Visitor.query.get_or_404(vid)
    nome = visitor.full_name

    try:
        # Desvincula os logs em vez de apaga-los
        PortalSession.query.filter_by(visitor_id=visitor.id).update(
            {"visitor_id": None}, synchronize_session=False
        )
        AuditLog.query.filter_by(visitor_id=visitor.id).update(
            {"visitor_id": None}, synchronize_session=False
        )
        # Consentimentos (consent_events) saem junto por cascade: sao dados
        # pessoais e perdem o sentido sem o titular.
        db.session.delete(visitor)

        db.session.add(AuditLog(
            event_type="VISITOR_DELETED",
            status="SUCCESS",
            payload=f"visitante '{nome}' (id={vid}) excluido pelo painel",
            actor=current_user.username,
            ip_address=request.remote_addr,
        ))
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error("falha ao excluir visitante %s: %s", vid, exc)
        flash("Não foi possível excluir o cadastro.", "error")
        return redirect(url_for("admin.visitors"))

    flash(f"Cadastro de '{nome}' excluído. Os registros de acesso foram mantidos "
          f"de forma anônima, conforme o Marco Civil da Internet.", "success")
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
            v.id, v.full_name, v.email or "", v.mobile, v.cpf,
            v.visit_count or 0,
            fmt_datetime(v.last_seen) if v.last_seen else "",
            "Sim" if v.is_blocked else "Não",
            fmt_datetime(v.created_at),
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
    webhook_url = request.form.get("webhook_url", "").strip()
    if webhook_url and not re.match(r'^https?://', webhook_url):
        flash("URL do webhook deve começar com http:// ou https://", "error")
        return redirect(url_for("admin.integrations"))
    SiteConfig.set("webhook_url",     webhook_url)
    SiteConfig.set("webhook_secret",  request.form.get("webhook_secret", "").strip())
    SiteConfig.set("webhook_enabled", "true" if request.form.get("webhook_enabled") else "false")
    db.session.commit()
    flash("Configurações de integração salvas.", "success")
    return redirect(url_for("admin.integrations"))


@bp.post("/integracoes/testar")
@login_required
@limiter.limit("5 per minute")
def integrations_test():
    import hashlib, hmac, json
    import requests as req_lib
    import urllib.parse
    import warnings

    url    = SiteConfig.get("webhook_url", "").strip()
    secret = SiteConfig.get("webhook_secret", "changeme")

    if not url:
        flash("Configure a URL do webhook primeiro.", "error")
        return redirect(url_for("admin.integrations"))

    allow_private = os.environ.get("ALLOW_PRIVATE_WEBHOOK", "false").lower() == "true"
    if not allow_private:
        parsed   = urllib.parse.urlparse(url)
        hostname = parsed.hostname or ""
        _BLOCKED = ("localhost", "127.", "10.", "172.16.", "192.168.", "::1")
        if any(hostname == b or hostname.startswith(b) for b in _BLOCKED):
            flash("URL de destino não permitida (endereço interno). "
                  "Defina ALLOW_PRIVATE_WEBHOOK=true no .env para ambientes on-premise.", "error")
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
                "Content-Type": "application/json",
                "X-Webhook-Signature": f"sha256={sig}",
                "X-Webhook-Event": "webhook_test",
            },
            timeout=8,
            verify=verify_ssl,
        )
        flash(f"Webhook enviado com sucesso (HTTP {resp.status_code}).", "success")
    except Exception as exc:
        flash(f"Falha ao enviar webhook: {exc}", "error")
    return redirect(url_for("admin.integrations"))


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
    # Usa a rota /admin/media/ que é roteada pelo nginx-proxy
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


# ─── Lojas (UDM Pro por loja) ─────────────────────────────────────────────────

_SLUG_RE = re.compile(r'^[a-z0-9-]{2,80}$')


@bp.get("/lojas")
@login_required
def stores():
    all_stores = Store.query.order_by(Store.name).all()
    return render_template("admin/stores.html", stores=all_stores)


@bp.get("/lojas/nova")
@login_required
def store_new():
    return render_template("admin/store_form.html", store=None)


@bp.post("/lojas/nova")
@login_required
def store_create():
    name = request.form.get("name", "").strip()[:120]
    slug = request.form.get("slug", "").strip().lower() or Store.slugify(name)

    if not name:
        flash("Informe o nome da loja.", "error")
        return redirect(url_for("admin.store_new"))
    if not _SLUG_RE.match(slug):
        flash("Slug inválido. Use apenas letras minúsculas, números e hífen.", "error")
        return redirect(url_for("admin.store_new"))
    if Store.query.filter_by(slug=slug).first():
        flash(f"Já existe uma loja com o slug '{slug}'.", "error")
        return redirect(url_for("admin.store_new"))

    store = Store(
        name=name,
        slug=slug,
        unifi_base_url=request.form.get("unifi_base_url", "").strip(),
        unifi_api_key=request.form.get("unifi_api_key", "").strip(),
        unifi_site_id=request.form.get("unifi_site_id", "").strip() or "default",
        unifi_verify_ssl=bool(request.form.get("unifi_verify_ssl")),
        session_minutes=request.form.get("session_minutes", type=int),
        is_active=True,
    )
    db.session.add(store)
    db.session.commit()
    flash(f"Loja '{store.name}' criada. Configure o Hotspot Manager do UDM Pro dessa loja "
          f"para usar /guest/s/{store.slug}/.", "success")
    return redirect(url_for("admin.stores"))


@bp.get("/lojas/<int:sid>/editar")
@login_required
def store_edit(sid: int):
    store = Store.query.get_or_404(sid)
    return render_template("admin/store_form.html", store=store)


@bp.post("/lojas/<int:sid>/editar")
@login_required
def store_update(sid: int):
    store = Store.query.get_or_404(sid)
    name = request.form.get("name", "").strip()[:120]
    slug = request.form.get("slug", "").strip().lower()

    if not name:
        flash("Informe o nome da loja.", "error")
        return redirect(url_for("admin.store_edit", sid=sid))
    if not _SLUG_RE.match(slug):
        flash("Slug inválido. Use apenas letras minúsculas, números e hífen.", "error")
        return redirect(url_for("admin.store_edit", sid=sid))
    if Store.query.filter(Store.slug == slug, Store.id != sid).first():
        flash(f"Já existe uma loja com o slug '{slug}'.", "error")
        return redirect(url_for("admin.store_edit", sid=sid))

    store.name             = name
    store.slug             = slug
    store.unifi_base_url   = request.form.get("unifi_base_url", "").strip()
    store.unifi_site_id    = request.form.get("unifi_site_id", "").strip() or "default"
    store.unifi_verify_ssl = bool(request.form.get("unifi_verify_ssl"))
    store.session_minutes  = request.form.get("session_minutes", type=int)

    new_key = request.form.get("unifi_api_key", "").strip()
    if new_key:
        store.unifi_api_key = new_key

    db.session.commit()
    flash(f"Loja '{store.name}' atualizada.", "success")
    return redirect(url_for("admin.stores"))


@bp.post("/lojas/<int:sid>/toggle")
@login_required
def store_toggle(sid: int):
    store = Store.query.get_or_404(sid)
    store.is_active = not store.is_active
    db.session.commit()
    status = "ativada" if store.is_active else "desativada"
    flash(f"Loja '{store.name}' {status}.", "success")
    return redirect(url_for("admin.stores"))


@bp.post("/lojas/<int:sid>/excluir")
@login_required
def store_delete(sid: int):
    store = Store.query.get_or_404(sid)
    if PortalSession.query.filter_by(store_id=store.id).first():
        flash(f"Loja '{store.name}' possui sessões registradas — desative-a em vez de excluir.", "error")
        return redirect(url_for("admin.stores"))
    db.session.delete(store)
    db.session.commit()
    flash(f"Loja '{store.name}' excluída.", "success")
    return redirect(url_for("admin.stores"))


@bp.post("/lojas/<int:sid>/testar")
@login_required
@limiter.limit("10 per minute")
def store_test(sid: int):
    store = Store.query.get_or_404(sid)
    try:
        unifi = get_unifi_for_store(store)
        sites = unifi.get_sites()
        return jsonify({"ok": True, "mock": unifi.mock, "sites": sites})
    except UnifiAPIError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


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
