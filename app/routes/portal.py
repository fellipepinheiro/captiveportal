from flask import (
    Blueprint, render_template, request, redirect,
    session, url_for, flash, current_app
)
from sqlalchemy.exc import IntegrityError
from app.extensions import db, limiter
from app.models import Visitor, PortalSession
from app.services.portal_service import (
    create_pending_session, authorize_visitor, record_consent
)
from app.services.validator import validate_cpf, validate_phone, normalize_phone

bp = Blueprint("portal", __name__)
PORTAL_SESSION_KEY = "portal_session_id"


def _get_portal_session():
    sid = session.get(PORTAL_SESSION_KEY)
    if not sid:
        return None
    return PortalSession.query.get(sid)


@bp.get("/guest/s/default/")
@bp.get("/guest/")
def entry():
    client_mac  = request.args.get("id") or request.args.get("mac")
    ap_mac      = request.args.get("ap")
    ssid        = request.args.get("ssid", "WiFi")
    redirect_url= request.args.get("url", "http://google.com")

    # Sem MAC: acesso direto (teste ou redirect sem parâmetros)
    # Não cria sessão no banco — apenas renderiza a página de entrada
    if not client_mac:
        return render_template(
            "portal/start.html",
            ssid=ssid,
            privacy_url=current_app.config.get("PRIVACY_POLICY_URL", "#"),
        )

    portal_session = create_pending_session(client_mac, ap_mac, ssid, redirect_url)
    session[PORTAL_SESSION_KEY] = portal_session.id

    return render_template(
        "portal/start.html",
        ssid=ssid,
        privacy_url=current_app.config.get("PRIVACY_POLICY_URL", "#"),
    )


@bp.post("/guest/identify")
@limiter.limit("10 per minute")
def identify():
    portal_session = _get_portal_session()
    if not portal_session:
        flash("Sessão expirada. Por favor, conecte-se novamente.", "error")
        return redirect(url_for("portal.entry"))

    email  = request.form.get("email",  "").strip().lower()
    mobile = request.form.get("mobile", "").strip()

    # Validações
    if not email or not mobile:
        flash("Preencha e-mail e celular.", "error")
        return redirect(url_for("portal.entry"))
    if not validate_phone(mobile):
        flash("Número de celular inválido.", "error")
        return redirect(url_for("portal.entry"))
    # Aceite de termos obrigatório desde a etapa 1
    if not request.form.get("terms_accepted"):
        flash("Você precisa aceitar os Termos de Uso para continuar.", "error")
        return redirect(url_for("portal.entry"))

    visitor = Visitor.find_by_email_or_mobile(email, mobile)
    if visitor:
        # Visitante bloqueado
        if visitor.is_blocked:
            flash("Seu acesso foi restrito. Entre em contato com o suporte.", "error")
            return redirect(url_for("portal.entry"))

        ok = authorize_visitor(portal_session, visitor)
        if ok:
            return render_template(
                "portal/success.html",
                redirect_url=portal_session.redirect_url,
                name=visitor.full_name,
            )
        flash("Não foi possível autorizar o acesso agora. Tente novamente.", "error")
        return redirect(url_for("portal.entry"))

    # Novo visitante → cadastro
    session["reg_email"]  = email
    session["reg_mobile"] = normalize_phone(mobile)
    return redirect(url_for("portal.register"))


@bp.get("/guest/cadastro")
def register():
    if not session.get("reg_email"):
        return redirect(url_for("portal.entry"))
    portal_session = _get_portal_session()
    if not portal_session:
        return redirect(url_for("portal.entry"))
    return render_template(
        "portal/register.html",
        email=session.get("reg_email"),
        mobile=session.get("reg_mobile"),
        privacy_url=current_app.config.get("PRIVACY_POLICY_URL", "#"),
        terms_version=current_app.config.get("TERMS_VERSION", "1.0"),
    )


@bp.post("/guest/cadastro")
@limiter.limit("5 per minute")
def register_submit():
    portal_session = _get_portal_session()
    if not portal_session:
        flash("Sessão expirada. Por favor, conecte-se novamente.", "error")
        return redirect(url_for("portal.entry"))

    email          = session.get("reg_email",  "").strip().lower()
    mobile         = session.get("reg_mobile", "").strip()
    full_name      = request.form.get("full_name",     "").strip()
    cpf            = request.form.get("cpf",           "").strip()
    marketing_optin= bool(request.form.get("marketing_optin"))
    terms_version  = current_app.config.get("TERMS_VERSION", "1.0")

    if not full_name or len(full_name.split()) < 2:
        flash("Informe seu nome completo (mínimo 2 palavras).", "error")
        return redirect(url_for("portal.register"))
    if not validate_cpf(cpf):
        flash("CPF inválido.", "error")
        return redirect(url_for("portal.register"))

    visitor = Visitor.query.filter_by(cpf=cpf).first()
    created = False
    if visitor is None:
        visitor = Visitor.create(
            full_name=full_name, email=email, mobile=mobile,
            cpf=cpf, terms_version=terms_version, marketing_optin=marketing_optin,
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

    ok = authorize_visitor(portal_session, visitor)
    session.pop("reg_email", None)
    session.pop("reg_mobile", None)

    if ok:
        return render_template(
            "portal/success.html",
            redirect_url=portal_session.redirect_url,
            name=visitor.full_name,
        )
    flash("Cadastro realizado, mas não foi possível autorizar agora. Tente novamente.", "error")
    return redirect(url_for("portal.entry"))
