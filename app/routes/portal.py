from datetime import datetime, timezone

from flask import (
    Blueprint, render_template, request, redirect,
    session, url_for, flash, current_app, jsonify
)
from sqlalchemy.exc import IntegrityError
from app.extensions import db, limiter, csrf
from app.models import Visitor, PortalSession, Store
from app.models.site_config import SiteConfig
from app.services.portal_service import (
    create_pending_session, authorize_visitor, record_consent, refresh_consent
)
from app.services.validator import (
    validate_cpf, validate_phone, validate_email, normalize_phone, normalize_cpf
)

bp = Blueprint("portal", __name__)
PORTAL_SESSION_KEY = "portal_session_id"

_DEFAULT_CFG = {
    "portal_title":    "Wi-Fi Visitantes",
    "portal_welcome":  "Identifique-se para acessar a internet.",
    "portal_btn_color": "#0f766e",
    "portal_accent":   "#14b8a6",
    "portal_bg_from":  "#0f172a",
    "portal_bg_via":   "#1e1b4b",
    "portal_bg_to":    "#0f172a",
}


def _portal_cfg() -> dict:
    """Carrega configurações de aparência + logo do banco."""
    cfg = dict(_DEFAULT_CFG)
    for key in _DEFAULT_CFG:
        val = SiteConfig.get(key)
        if val is not None:
            cfg[key] = val
    cfg["custom_logo_url"] = SiteConfig.get("custom_logo_url") or ""
    cfg["logo_title"]      = SiteConfig.get("logo_title") or ""
    return cfg


def _get_portal_session():
    sid = session.get(PORTAL_SESSION_KEY)
    if not sid:
        return None
    return PortalSession.query.get(sid)


def _get_session_store(portal_session):
    if not portal_session or not portal_session.store_id:
        return None
    return Store.query.get(portal_session.store_id)


def _resolve_store(slug: str):
    """Resolve a loja pelo slug da URL configurada no Hotspot Manager do UDM Pro.

    Cai para a loja 'default' se o slug nao existir/estiver inativo, para nao
    quebrar acessos com URL desatualizada.
    """
    store = Store.query.filter_by(slug=slug, is_active=True).first()
    if store:
        return store
    if slug != "default":
        return Store.query.filter_by(slug="default", is_active=True).first()
    return None


@bp.get("/guest/s/<slug>/")
@bp.get("/guest/")
@csrf.exempt
def entry(slug="default"):
    client_mac   = request.args.get("id") or request.args.get("mac")
    ap_mac       = request.args.get("ap")
    ssid         = request.args.get("ssid", "WiFi")
    redirect_url = request.args.get("url", "http://google.com")
    store        = _resolve_store(slug)

    if client_mac:
        portal_session = create_pending_session(client_mac, ap_mac, ssid, redirect_url, store)
        session[PORTAL_SESSION_KEY] = portal_session.id
    else:
        session[PORTAL_SESSION_KEY] = None
        session.modified = True

    return render_template(
        "portal/start.html",
        ssid=ssid,
        privacy_url=current_app.config.get("PRIVACY_POLICY_URL", "#"),
        **_portal_cfg(),
    )


@bp.post("/guest/identify")
@csrf.exempt
@limiter.limit("10 per minute")
def identify():
    portal_session = _get_portal_session()
    if not portal_session:
        flash("Sess\u00e3o expirada. Por favor, conecte-se novamente ao WiFi.", "error")
        return redirect(url_for("portal.entry"))

    cpf    = request.form.get("cpf",    "").strip()
    mobile = request.form.get("mobile", "").strip()

    if not cpf or not mobile:
        flash("Preencha CPF e celular.", "error")
        return redirect(url_for("portal.entry"))
    if not validate_cpf(cpf):
        flash("CPF inv\u00e1lido.", "error")
        return redirect(url_for("portal.entry"))
    if not validate_phone(mobile):
        flash("N\u00famero de celular inv\u00e1lido.", "error")
        return redirect(url_for("portal.entry"))
    if not request.form.get("terms_accepted"):
        flash("Voc\u00ea precisa aceitar os Termos de Uso para continuar.", "error")
        return redirect(url_for("portal.entry"))

    cpf_norm    = normalize_cpf(cpf)
    mobile_norm = normalize_phone(mobile)
    visitor = Visitor.find_by_cpf(cpf_norm)
    if visitor:
        if visitor.is_blocked:
            flash("Seu acesso foi restrito. Entre em contato com o suporte.", "error")
            return redirect(url_for("portal.entry"))

        # CPF é a chave de identificação; o telefone é atualizado quando muda,
        # exceto se já pertencer a outro cadastro.
        if visitor.mobile != mobile_norm:
            taken = Visitor.query.filter(
                Visitor.mobile == mobile_norm, Visitor.id != visitor.id
            ).first()
            if not taken:
                visitor.mobile = mobile_norm
                db.session.commit()

        # Ele marcou o aceite agora; se os termos mudaram desde o cadastro,
        # o registro precisa refletir a versao que ele de fato aceitou.
        refresh_consent(visitor, current_app.config.get("TERMS_VERSION", "1.0"))

        store = _get_session_store(portal_session)
        ok = authorize_visitor(portal_session, visitor, store)
        if ok:
            return render_template(
                "portal/success.html",
                redirect_url=portal_session.redirect_url,
                name=visitor.full_name,
                **_portal_cfg(),
            )
        flash("N\u00e3o foi poss\u00edvel autorizar o acesso agora. Tente novamente.", "error")
        return redirect(url_for("portal.entry"))

    session["reg_cpf"]    = cpf_norm
    session["reg_mobile"] = mobile_norm
    return redirect(url_for("portal.register"))


@bp.get("/guest/cadastro")
@csrf.exempt
def register():
    if not session.get("reg_cpf"):
        return redirect(url_for("portal.entry"))
    portal_session = _get_portal_session()
    if not portal_session:
        return redirect(url_for("portal.entry"))
    return render_template(
        "portal/register.html",
        cpf=session.get("reg_cpf"),
        mobile=session.get("reg_mobile"),
        privacy_url=current_app.config.get("PRIVACY_POLICY_URL", "#"),
        terms_version=current_app.config.get("TERMS_VERSION", "1.0"),
        **_portal_cfg(),
    )


@bp.post("/guest/localizacao")
@csrf.exempt
@limiter.limit("20 per minute")
def registrar_localizacao():
    """Recebe a posicao informada pelo navegador do visitante.

    Chamado da tela de sucesso, depois que o acesso ja foi liberado: a
    coleta nao pode atrasar nem condicionar a entrada na internet. Quem
    recusa a permissao simplesmente nao envia nada.
    """
    portal_session = _get_portal_session()
    if not portal_session:
        return jsonify({"ok": False}), 204

    dados = request.get_json(silent=True) or {}
    try:
        lat = float(dados.get("lat"))
        lon = float(dados.get("lon"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "erro": "coordenadas invalidas"}), 400

    # Fora destas faixas nao e coordenada valida — descarta em vez de gravar
    # sujeira que depois apareceria como ponto perdido no mapa.
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return jsonify({"ok": False, "erro": "coordenadas fora de faixa"}), 400

    try:
        precisao = int(float(dados.get("precisao") or 0))
    except (TypeError, ValueError):
        precisao = 0

    portal_session.latitude = lat
    portal_session.longitude = lon
    portal_session.location_accuracy = precisao or None
    portal_session.location_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"ok": True})


@bp.post("/guest/cadastro")
@csrf.exempt
@limiter.limit("5 per minute")
def register_submit():
    portal_session = _get_portal_session()
    if not portal_session:
        flash("Sess\u00e3o expirada. Por favor, conecte-se novamente.", "error")
        return redirect(url_for("portal.entry"))

    cpf            = session.get("reg_cpf",    "").strip()
    mobile         = session.get("reg_mobile", "").strip()
    full_name      = request.form.get("full_name", "").strip()
    email          = request.form.get("email",     "").strip().lower()
    marketing_optin= bool(request.form.get("marketing_optin"))
    terms_version  = current_app.config.get("TERMS_VERSION", "1.0")

    if not full_name or len(full_name.split()) < 2:
        flash("Informe seu nome completo (m\u00ednimo 2 palavras).", "error")
        return redirect(url_for("portal.register"))
    if email and not validate_email(email):
        flash("E-mail inv\u00e1lido.", "error")
        return redirect(url_for("portal.register"))

    visitor = Visitor.query.filter_by(cpf=cpf).first()
    created = False
    if visitor is None:
        visitor = Visitor.create(
            full_name=full_name, mobile=mobile, cpf=cpf,
            email=email or None, terms_version=terms_version, marketing_optin=marketing_optin,
        )
        db.session.add(visitor)
        try:
            db.session.flush()
            created = True
        except IntegrityError:
            db.session.rollback()
            visitor = Visitor.query.filter_by(cpf=cpf).first()
            if visitor is None:
                flash("Erro ao cadastrar. Tente novamente.", "error")
                return redirect(url_for("portal.register"))

    if created:
        record_consent(visitor, marketing_optin=marketing_optin, version=terms_version)

    db.session.commit()

    store = _get_session_store(portal_session)
    ok = authorize_visitor(portal_session, visitor, store)
    session.pop("reg_cpf", None)
    session.pop("reg_mobile", None)

    if ok:
        return render_template(
            "portal/success.html",
            redirect_url=portal_session.redirect_url,
            name=visitor.full_name,
            **_portal_cfg(),
        )
    flash("Cadastro realizado, mas n\u00e3o foi poss\u00edvel autorizar agora. Tente novamente.", "error")
    return redirect(url_for("portal.entry"))
