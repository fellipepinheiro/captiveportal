import csv
import io
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, Response, jsonify, current_app, send_from_directory
)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import or_, func
from werkzeug.utils import secure_filename

from app.extensions import db, limiter, csrf
from app.models import Visitor, PortalSession, AdminUser, Store, AuditLog, FormField
from app.models.site_config import SiteConfig
from app.services.unifi_api import get_unifi_for_store, UnifiAPIError
from app.services.datetime_fmt import fmt_datetime, get_tz
from app.services.validator import format_cpf

bp = Blueprint("admin", __name__)

UPLOAD_FOLDER      = Path("app/static/uploads")
AVATAR_FOLDER      = Path("app/static/uploads/avatars")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_LOGO_BYTES     = 2 * 1024 * 1024
MAX_AVATAR_BYTES   = 20 * 1024 * 1024   # 20 MB – Pillow vai compactar depois
AVATAR_SIZE        = (256, 256)          # px máximo do avatar salvo
AVATAR_QUALITY     = 82                  # qualidade JPEG do avatar salvo
HEX_COLOR_RE       = re.compile(r'^#[0-9A-Fa-f]{6}$')
LOCAL_TZ           = ZoneInfo("America/Sao_Paulo")

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


def _compress_avatar(data: bytes) -> bytes:
    """
    Recebe bytes de qualquer imagem (iPhone HEIC/JPEG, PNG, WEBP…),
    redimensiona para no máximo AVATAR_SIZE mantendo proporção,
    converte para JPEG e retorna os bytes compactados.
    Resultado típico: 15–50 KB independente do arquivo original.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return data

    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    w, h = img.size
    side = min(w, h)
    left   = (w - side) // 2
    top    = (h - side) // 2
    img    = img.crop((left, top, left + side, top + side))
    img    = img.resize(AVATAR_SIZE, Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=AVATAR_QUALITY, optimize=True)
    return buf.getvalue()


# ─── Media (logo pública + avatars) ─────────────────────────────────────────────────────────────

@bp.get("/media/<filename>")
@csrf.exempt
def serve_media(filename):
    """Serve arquivos de mídia: logo (UPLOAD_FOLDER) e avatars (AVATAR_FOLDER).

    avatars são salvos como 'avatar_<id>.jpg' diretamente em AVATAR_FOLDER.
    A URL gerada pelo model é /admin/media/avatar_<id>.jpg (sem subpasta).
    """
    safe = secure_filename(filename)
    if not safe:
        from flask import abort
        abort(404)

    # Verifica primeiro na pasta de avatars
    avatar_file = AVATAR_FOLDER / safe
    if avatar_file.exists():
        return send_from_directory(AVATAR_FOLDER.resolve(), safe)

    # Depois na pasta raíz de uploads (logo, favicon etc.)
    upload_file = UPLOAD_FOLDER / safe
    if upload_file.exists():
        return send_from_directory(UPLOAD_FOLDER.resolve(), safe)

    from flask import abort
    abort(404)


# ─── Auth ───────────────────────────────────────────────────────────────────────────────────────

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
        # Gravado em UTC como todos os demais timestamps; a conversao para
        # o fuso local acontece na exibicao, pelo filtro `datahora`.
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


# ─── Dashboard ───────────────────────────────────────────────────────────────────────────────

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
    """Desconecta no controlador um dispositivo com acesso liberado."""
    from app.services.portal_service import revoke_session

    ps = PortalSession.query.get_or_404(sid)
    if not ps.authorized:
        flash("Essa sessão já não está autorizada.", "error")
        return redirect(request.referrer or url_for("admin.dashboard"))

    store = Store.query.get(ps.store_id) if ps.store_id else None
    ok, msg = revoke_session(ps, store)
    flash(msg, "success" if ok else "error")
    return redirect(request.referrer or url_for("admin.dashboard"))


@bp.post("/sessoes/<int:sid>/apagar")
@login_required
def session_delete(sid: int):
    """Apaga do banco uma sessão que nunca chegou a ser autorizada.

    O criterio e authorized_at, nao authorized: uma sessao encerrada
    tambem fica com authorized False, e apagar essas destruiria o
    historico de conexoes que o extrato do visitante mostra.
    """
    portal_session = PortalSession.query.get_or_404(sid)
    if portal_session.authorized_at:
        flash("Só é possível apagar acessos que nunca foram autorizados. "
              "Para encerrar uma conexão ativa, use 'Derrubar'.", "error")
        return redirect(request.referrer or url_for("admin.dashboard"))
    db.session.delete(portal_session)
    db.session.commit()
    flash("Acesso pendente removido.", "success")
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
                "Dispositivo", "IP", "MAC", "Latitude", "Longitude",
                "Distância da loja (km)", "Status"])
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
            s.latitude if s.latitude is not None else "",
            s.longitude if s.longitude is not None else "",
            s.distancia_da_loja if s.distancia_da_loja is not None else "",
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

    # Bloquear sem derrubar nao tira ninguem da rede: a autorizacao ja
    # concedida vale ate a janela expirar.
    from app.services.portal_service import revoke_visitor_sessions
    derrubadas = revoke_visitor_sessions(visitor)

    aviso = f"Visitante '{visitor.full_name}' bloqueado."
    if derrubadas:
        aviso += f" {derrubadas} conexão(ões) encerrada(s)."
    flash(aviso, "success")
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

    # Derruba antes de apagar: depois de desvincular as sessoes nao ha mais
    # como saber quais dispositivos eram dele.
    from app.services.portal_service import revoke_visitor_sessions
    derrubadas = revoke_visitor_sessions(visitor)

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

    aviso = f"Cadastro de '{nome}' excluído."
    if derrubadas:
        aviso += f" {derrubadas} conexão(ões) encerrada(s)."
    aviso += (" Os registros de acesso foram mantidos de forma anônima, "
              "conforme o Marco Civil da Internet.")
    flash(aviso, "success")
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


# ─── Reports ─────────────────────────────────────────────────────────────────────────────────

@bp.get("/relatorios")
@login_required
def reports():
    de, ate, _, _ = _periodo_do_request()
    visitor = None
    vid = request.args.get("visitante", type=int)
    if vid:
        visitor = Visitor.query.get(vid)
    return render_template(
        "admin/reports.html",
        lojas=Store.query.order_by(Store.name).all(),
        loja_id=request.args.get("loja", type=int),
        visitante=visitor,
        de=de.isoformat(), ate=ate.isoformat(),
    )


@bp.get("/relatorios/dados")
@login_required
def reports_data():
    from app.services.analytics import coletar

    de, ate, inicio, fim = _periodo_do_request()
    return jsonify(coletar(
        inicio, fim, de, ate,
        store_id=request.args.get("loja", type=int),
        visitor_id=request.args.get("visitante", type=int),
    ))


@bp.get("/relatorios/exportar.csv")
@login_required
def reports_export():
    """Exporta as sessoes do periodo com os mesmos filtros da tela."""
    de, ate, inicio, fim = _periodo_do_request()
    loja_id = request.args.get("loja", type=int)
    vid = request.args.get("visitante", type=int)

    q = (PortalSession.query
         .filter(PortalSession.created_at >= inicio, PortalSession.created_at < fim))
    if loja_id:
        q = q.filter(PortalSession.store_id == loja_id)
    if vid:
        q = q.filter(PortalSession.visitor_id == vid)
    sessoes = q.order_by(PortalSession.created_at.desc()).all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Período", f"{de.strftime('%d/%m/%Y')} a {ate.strftime('%d/%m/%Y')}"])
    w.writerow([])
    w.writerow(["Loja", "Visitante", "CPF", "Rede", "Conexão", "Desconexão",
                "Duração (min)", "Download (MB)", "Upload (MB)",
                "Dispositivo", "Sistema", "IP", "MAC",
                "Latitude", "Longitude", "Distância da loja (km)", "Status"])
    for s in sessoes:
        if s.is_active:
            status = "Em curso"
        elif s.authorized_at:
            status = "Encerrada"
        else:
            status = "Não concluída"
        w.writerow([
            s.store.name if s.store else "",
            s.visitor.full_name if s.visitor else "",
            format_cpf(s.visitor.cpf) if s.visitor else "",
            s.ssid or "",
            fmt_datetime(s.authorized_at) if s.authorized_at else "",
            fmt_datetime(s.expired_at) if s.expired_at else "",
            s.duration if s.duration is not None else "",
            round((s.bytes_down or 0) / 1048576, 2),
            round((s.bytes_up or 0) / 1048576, 2),
            s.device_type or "",
            s.os_hint or "",
            s.client_ip or "",
            s.client_mac or "",
            s.latitude if s.latitude is not None else "",
            s.longitude if s.longitude is not None else "",
            s.distancia_da_loja if s.distancia_da_loja is not None else "",
            status,
        ])
    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=relatorio_{de}_{ate}.csv",
            "X-Content-Type-Options": "nosniff",
        },
    )


@bp.get("/relatorios/buscar-visitante")
@login_required
def reports_find_visitor():
    """Autocomplete do filtro por cliente."""
    termo = request.args.get("q", "").strip()
    if len(termo) < 2:
        return jsonify([])
    digitos = re.sub(r"\D", "", termo)
    filtros = [Visitor.full_name.ilike(f"%{termo}%")]
    if digitos:
        filtros.append(Visitor.cpf.like(f"%{digitos}%"))
        filtros.append(Visitor.mobile.like(f"%{digitos}%"))
    achados = Visitor.query.filter(or_(*filtros)).limit(10).all()
    return jsonify([
        {"id": v.id, "nome": v.full_name, "cpf": format_cpf(v.cpf)}
        for v in achados
    ])


# ─── Integrations ──────────────────────────────────────────────────────────────────────────────────

@bp.get("/integracoes")
@login_required
def integrations():
    return render_template(
        "admin/integrations.html",
        webhook_url=SiteConfig.get("webhook_url", ""),
        webhook_secret=SiteConfig.get("webhook_secret", ""),
        webhook_enabled=SiteConfig.get("webhook_enabled", "false") == "true",
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


# ─── Appearance ───────────────────────────────────────────────────────────────────────────────────

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


# ─── Lojas (UDM Pro por loja) ─────────────────────────────────────────────────

_SLUG_RE = re.compile(r'^[a-z0-9-]{2,80}$')


@bp.get("/lojas")
@login_required
def stores():
    all_stores = Store.query.order_by(Store.name).all()

    # Sessoes abertas por loja, em uma consulta so. E o que o portal
    # registrou; o numero real do controlador aparece ao abrir a loja.
    abertas = dict(
        db.session.query(PortalSession.store_id, func.count())
        .filter(PortalSession.authorized.is_(True))
        .filter(PortalSession.expired_at.is_(None))
        .group_by(PortalSession.store_id).all()
    )
    return render_template("admin/stores.html", stores=all_stores, abertas=abertas)


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

    destino = request.form.get("redirect_url", "").strip()
    if destino and not re.match(r"^https?://", destino):
        flash("A URL de destino deve começar com http:// ou https://", "error")
        return redirect(url_for("admin.store_new"))

    store = Store(
        name=name,
        slug=slug,
        unifi_base_url=request.form.get("unifi_base_url", "").strip(),
        unifi_api_key=request.form.get("unifi_api_key", "").strip(),
        unifi_site_id=request.form.get("unifi_site_id", "").strip() or "default",
        unifi_verify_ssl=bool(request.form.get("unifi_verify_ssl")),
        session_minutes=request.form.get("session_minutes", type=int),
        redirect_url=request.form.get("redirect_url", "").strip()[:512] or None,
        address=request.form.get("address", "").strip()[:255] or None,
        latitude=request.form.get("latitude", type=float),
        longitude=request.form.get("longitude", type=float),
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

    destino = request.form.get("redirect_url", "").strip()
    if destino and not re.match(r"^https?://", destino):
        flash("A URL de destino deve começar com http:// ou https://", "error")
        return redirect(url_for("admin.store_edit", sid=sid))

    store.name             = name
    store.slug             = slug
    store.unifi_base_url   = request.form.get("unifi_base_url", "").strip()
    store.unifi_site_id    = request.form.get("unifi_site_id", "").strip() or "default"
    store.unifi_verify_ssl = bool(request.form.get("unifi_verify_ssl"))
    store.session_minutes  = request.form.get("session_minutes", type=int)
    store.redirect_url     = request.form.get("redirect_url", "").strip()[:512] or None
    store.address          = request.form.get("address", "").strip()[:255] or None
    store.latitude         = request.form.get("latitude", type=float)
    store.longitude        = request.form.get("longitude", type=float)

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


@bp.get("/lojas/<int:sid>/conexoes")
@login_required
def store_connections(sid: int):
    """Quem esta com acesso liberado nesta loja, segundo o controlador.

    A fonte e o controlador, nao o banco: o UniFi reautoriza sozinho um
    dispositivo cuja janela de acesso ainda nao expirou, sem passar pelo
    portal. Essas conexoes existem de fato mas nao tem sessao registrada —
    e aparecem aqui marcadas como tal, senao a tela mostraria menos gente
    conectada do que realmente esta usando a rede.
    """
    store = Store.query.get_or_404(sid)
    unifi = get_unifi_for_store(store)
    if unifi.mock:
        return jsonify({"ok": True, "mock": True, "conexoes": []})

    site_id = store.unifi_site_id or "default"
    try:
        clientes = unifi.list_clients(site_id)
        trafego = unifi.get_client_traffic(unifi.site_name_from_id(site_id))
    except UnifiAPIError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502

    ativos = [
        c for c in clientes
        if (c.get("access") or {}).get("authorized") is True
    ]
    macs = [(c.get("macAddress") or "").lower() for c in ativos]

    # Uma consulta so para todas as sessoes abertas destes MACs
    sessoes = {}
    if macs:
        for ps in (PortalSession.query
                   .filter(func.lower(PortalSession.client_mac).in_(macs))
                   .filter(PortalSession.authorized.is_(True))
                   .filter(PortalSession.expired_at.is_(None))
                   .order_by(PortalSession.id.desc()).all()):
            sessoes.setdefault((ps.client_mac or "").lower(), ps)

    conexoes = []
    for c in ativos:
        mac = (c.get("macAddress") or "").lower()
        ps = sessoes.get(mac)
        uso = trafego.get(mac) or {}
        conexoes.append({
            "mac":        mac,
            "nome_rede":  c.get("name") or "",
            "ip":         c.get("ipAddress") or "",
            "desde":      c.get("connectedAt"),
            "bytes":      (uso.get("rx") or 0) + (uso.get("tx") or 0),
            "sessao_id":  ps.id if ps else None,
            "visitante":  ps.visitor.full_name if ps and ps.visitor else None,
            "visitante_id": ps.visitor_id if ps else None,
            "inicio":     fmt_datetime(ps.authorized_at) if ps and ps.authorized_at else None,
            "sem_sessao": ps is None,
        })
    conexoes.sort(key=lambda x: -x["bytes"])
    return jsonify({"ok": True, "mock": False, "conexoes": conexoes})


@bp.post("/lojas/<int:sid>/derrubar")
@login_required
@limiter.limit("30 per minute")
def store_disconnect(sid: int):
    """Derruba uma conexao desta loja pelo MAC.

    Age pelo MAC e nao pelo id da sessao porque a conexao pode existir no
    controlador sem sessao no portal (reautorizacao automatica). A sessao
    local, quando houver, e encerrada junto.
    """
    store = Store.query.get_or_404(sid)
    mac = (request.form.get("mac") or "").strip().lower()
    if not mac:
        return jsonify({"ok": False, "error": "MAC não informado"}), 400

    site_id = store.unifi_site_id or "default"
    try:
        unifi = get_unifi_for_store(store)
        cliente = unifi.find_client_by_mac(site_id, mac)
        if not cliente or not cliente.get("id"):
            msg = "Dispositivo já não está no controlador."
        else:
            try:
                unifi.revoke_guest(site_id, cliente["id"])
                msg = "Dispositivo desconectado."
            except UnifiAPIError as exc:
                if exc.code != "api.client.no-active-guest-authorization":
                    raise
                msg = "O dispositivo já estava sem acesso."
    except UnifiAPIError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502

    encerradas = 0
    for ps in (PortalSession.query
               .filter(func.lower(PortalSession.client_mac) == mac)
               .filter(PortalSession.authorized.is_(True))
               .filter(PortalSession.expired_at.is_(None)).all()):
        ps.close(max_minutes=store.session_minutes or
                 current_app.config.get("UNIFI_SESSION_MINUTES", 480))
        encerradas += 1
    if encerradas:
        db.session.commit()

    return jsonify({"ok": True, "mensagem": msg, "sessoes_encerradas": encerradas})


# ─── Campos do formulário ─────────────────────────────────────────────────────

@bp.get("/formulario")
@login_required
def form_fields():
    from app.models.form_field import CAMPOS_CONHECIDOS, CHAVES_POSSIVEIS, TIPOS
    from app.services import form_service

    return render_template(
        "admin/form_fields.html",
        login=form_service.campos("login"),
        signup=form_service.campos("signup"),
        chave=form_service.campo_chave(),
        conhecidos=CAMPOS_CONHECIDOS,
        chaves_possiveis=CHAVES_POSSIVEIS,
        tipos=TIPOS,
        usados={(f.stage, f.key) for f in FormField.query.all()},
    )


@bp.post("/formulario/salvar")
@login_required
def form_fields_save():
    """Grava a configuração de todos os campos de uma vez.

    Valida o conjunto antes de gravar: um formulário sem chave deixaria o
    portal sem como reconhecer visitante recorrente, e uma chave desabilitada
    teria o mesmo efeito — melhor recusar do que publicar algo quebrado.
    """
    from app.models.form_field import CHAVES_POSSIVEIS

    campos = FormField.query.all()
    chave_escolhida = request.form.get("chave", "").strip()

    habilitados_login = [
        c for c in campos
        if c.stage == "login" and request.form.get(f"enabled_{c.id}")
    ]
    if not habilitados_login:
        flash("A identificação precisa ter ao menos um campo ativo.", "error")
        return redirect(url_for("admin.form_fields"))

    if chave_escolhida not in {c.key for c in habilitados_login}:
        flash("O campo de identificação escolhido precisa estar ativo no login.", "error")
        return redirect(url_for("admin.form_fields"))
    if chave_escolhida not in CHAVES_POSSIVEIS:
        flash("Esse campo não pode identificar o visitante.", "error")
        return redirect(url_for("admin.form_fields"))

    for c in campos:
        c.enabled  = bool(request.form.get(f"enabled_{c.id}"))
        c.required = bool(request.form.get(f"required_{c.id}"))
        c.is_key   = (c.stage == "login" and c.key == chave_escolhida)
        c.label    = (request.form.get(f"label_{c.id}", "").strip() or c.label)[:80]
        c.order    = request.form.get(f"order_{c.id}", type=int) or 0
        c.placeholder = request.form.get(f"placeholder_{c.id}", "").strip()[:120] or None
        c.help_text   = request.form.get(f"help_{c.id}", "").strip()[:200] or None
        if c.field_type == "select":
            c.options = request.form.get(f"options_{c.id}", "").strip() or None

    # A chave e sempre obrigatoria: sem ela nao ha como identificar ninguem.
    for c in campos:
        if c.is_key:
            c.required = True

    db.session.commit()
    flash("Formulário atualizado.", "success")
    return redirect(url_for("admin.form_fields"))


@bp.post("/formulario/adicionar")
@login_required
def form_field_add():
    from app.models.form_field import CAMPOS_CONHECIDOS, TIPOS

    stage = request.form.get("stage", "signup")
    key   = request.form.get("key", "").strip().lower()
    label = request.form.get("label", "").strip()[:80]
    tipo  = request.form.get("field_type", "text")

    if stage not in ("login", "signup"):
        flash("Etapa inválida.", "error")
        return redirect(url_for("admin.form_fields"))
    if not key or not re.match(r"^[a-z][a-z0-9_]{1,39}$", key):
        flash("Identificador inválido. Use letras minúsculas, números e _ (começando por letra).", "error")
        return redirect(url_for("admin.form_fields"))
    if not label:
        flash("Informe o rótulo do campo.", "error")
        return redirect(url_for("admin.form_fields"))
    if tipo not in TIPOS:
        flash("Tipo de campo inválido.", "error")
        return redirect(url_for("admin.form_fields"))
    if FormField.query.filter_by(key=key, stage=stage).first():
        flash(f"Já existe um campo '{key}' nessa etapa.", "error")
        return redirect(url_for("admin.form_fields"))

    # Campo conhecido mantem o tipo que o sistema sabe validar; campo livre
    # usa o tipo escolhido.
    if key in CAMPOS_CONHECIDOS:
        tipo = CAMPOS_CONHECIDOS[key]["tipo"]

    ultimo = (db.session.query(func.max(FormField.order))
              .filter_by(stage=stage).scalar() or 0)
    campo = FormField(
        key=key, stage=stage, label=label, field_type=tipo,
        enabled=True, required=False, is_key=False, order=ultimo + 10,
        options=(CAMPOS_CONHECIDOS.get(key) or {}).get("opcoes"),
    )
    db.session.add(campo)
    db.session.commit()
    flash(f"Campo '{label}' adicionado.", "success")
    return redirect(url_for("admin.form_fields"))


@bp.post("/formulario/<int:fid>/remover")
@login_required
def form_field_delete(fid: int):
    campo = FormField.query.get_or_404(fid)
    if campo.is_key:
        flash("Não é possível remover o campo que identifica o visitante. "
              "Escolha outro como identificador antes.", "error")
        return redirect(url_for("admin.form_fields"))
    nome = campo.label
    db.session.delete(campo)
    db.session.commit()
    flash(f"Campo '{nome}' removido. Os dados já coletados continuam guardados.", "success")
    return redirect(url_for("admin.form_fields"))


# ─── Auditoria (LGPD) ─────────────────────────────────────────────────────────

@bp.get("/auditoria")
@login_required
def audit():
    """Histórico de eventos para compliance e investigação.

    Junta o audit_logs (tentativas de acesso e ações do painel) com o
    consent_events (histórico de consentimento), que ate agora eram
    gravados mas nao tinham como ser consultados.
    """
    from app.models import ConsentEvent

    de, ate, inicio, fim = _periodo_do_request()
    tipo = request.args.get("tipo", "").strip()
    page = request.args.get("page", 1, type=int)

    q = (AuditLog.query
         .filter(AuditLog.created_at >= inicio, AuditLog.created_at < fim))
    if tipo:
        q = q.filter(AuditLog.event_type == tipo)
    eventos = q.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=50)

    # Os tipos vem do proprio historico: a lista cresce sozinha conforme
    # novos eventos passam a ser registrados.
    tipos = [t[0] for t in db.session.query(AuditLog.event_type)
             .distinct().order_by(AuditLog.event_type).all()]

    consentimentos = (ConsentEvent.query
                      .filter(ConsentEvent.created_at >= inicio, ConsentEvent.created_at < fim)
                      .order_by(ConsentEvent.created_at.desc()).limit(50).all())

    visitantes = {}
    ids = {e.visitor_id for e in eventos.items if e.visitor_id}
    ids |= {c.visitor_id for c in consentimentos if c.visitor_id}
    if ids:
        visitantes = {v.id: v.full_name for v in Visitor.query.filter(Visitor.id.in_(ids)).all()}

    return render_template(
        "admin/audit.html",
        eventos=eventos, tipos=tipos, tipo=tipo,
        consentimentos=consentimentos, visitantes=visitantes,
        de=de.isoformat(), ate=ate.isoformat(),
    )


# ─── Admin Users ──────────────────────────────────────────────────────────────────────────────────

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
    flash(f"Senha de '{user.username}' alterada com sucesso.", "success")
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


# ─── My Profile ─────────────────────────────────────────────────────────────────────────────────

@bp.get("/perfil")
@login_required
def profile():
    return render_template("admin/profile.html")


@bp.post("/perfil/salvar")
@login_required
def profile_save():
    current_user.full_name = request.form.get("full_name", "").strip()[:120] or None
    current_user.phone     = request.form.get("phone", "").strip()[:30] or None
    current_user.email     = request.form.get("email", "").strip()[:120] or None
    db.session.commit()
    flash("Perfil atualizado com sucesso.", "success")
    return redirect(url_for("admin.profile"))


@bp.post("/perfil/senha")
@login_required
@limiter.limit("5 per minute")
def profile_change_password():
    current_password = request.form.get("current_password", "")
    new_password     = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not current_user.check_password(current_password):
        flash("Senha atual incorreta.", "error")
        return redirect(url_for("admin.profile"))

    if len(new_password) < 12:
        flash("A nova senha deve ter ao menos 12 caracteres.", "error")
        return redirect(url_for("admin.profile"))

    if new_password != confirm_password:
        flash("A confirmação da senha não confere.", "error")
        return redirect(url_for("admin.profile"))

    if current_user.check_password(new_password):
        flash("A nova senha deve ser diferente da senha atual.", "error")
        return redirect(url_for("admin.profile"))

    current_user.set_password(new_password)
    db.session.commit()
    flash("Senha alterada com sucesso.", "success")
    return redirect(url_for("admin.profile"))


@bp.post("/perfil/avatar")
@login_required
def profile_avatar():
    file = request.files.get("avatar")
    if not file or file.filename == "":
        flash("Nenhum arquivo selecionado.", "error")
        return redirect(url_for("admin.profile"))

    filename = secure_filename(file.filename)
    if not _allowed(filename):
        flash("Formato inválido. Use PNG, JPG ou WEBP.", "error")
        return redirect(url_for("admin.profile"))

    data = file.read()

    if len(data) > MAX_AVATAR_BYTES:
        flash("Imagem muito grande. Máximo 20 MB.", "error")
        return redirect(url_for("admin.profile"))

    try:
        compressed = _compress_avatar(data)
    except Exception:
        flash("Não foi possível processar a imagem. Tente outro arquivo.", "error")
        return redirect(url_for("admin.profile"))

    AVATAR_FOLDER.mkdir(parents=True, exist_ok=True)
    save_name = f"avatar_{current_user.id}.jpg"
    (AVATAR_FOLDER / save_name).write_bytes(compressed)
    current_user.avatar_path = save_name
    db.session.commit()
    flash("Foto de perfil atualizada.", "success")
    return redirect(url_for("admin.profile"))


@bp.post("/perfil/avatar/remover")
@login_required
def profile_avatar_remove():
    if current_user.avatar_path:
        path = AVATAR_FOLDER / current_user.avatar_path
        if path.exists():
            path.unlink()
        current_user.avatar_path = None
        db.session.commit()
    flash("Foto removida.", "success")
    return redirect(url_for("admin.profile"))
