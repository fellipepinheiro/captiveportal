from flask import (
    Blueprint, render_template, request, redirect,
    session, url_for, flash, current_app
)
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
    mac_client = request.args.get("id") or request.args.get("mac")
    mac_ap = request.args.get("ap")
    ssid = request.args.get("ssid", "WiFi")
    redirect_url = request.args.get("url", "http://google.com")
    portal_session = create_pending_session(mac_client, mac_ap, ssid, redirect_url)
    session[PORTAL_SESSION_KEY] = portal_session.id
    return render_template(
        "portal/start.html",
        ssid=ssid,
        privacy_url=current_app.config["PRIVACY_POLICY_URL"],
    )


@bp.post("/guest/check")
@limiter.limit("10 per minute")
def check_visitor():
    portal_session = _get_portal_session()
    if not portal_session:
        flash("Sessao expirada. Por favor, conecte-se novamente.", "error")
        return redirect(url_for("portal.entry"))

    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()

    if not email or not phone:
        flash("Preencha e-mail e celular.", "error")
        return redirect(url_for("portal.entry"))

    if not validate_phone(phone):
        flash("Numero de celular invalido.", "error")
        return redirect(url_for("portal.entry"))

    visitor = Visitor.find_by_email_or_phone(email, phone)
    if visitor:
        ok = authorize_visitor(portal_session, visitor)
        if ok:
            return render_template(
                "portal/success.html",
                redirect_url=portal_session.redirect_url,
                name=visitor.name,
            )
        flash("Nao foi possivel autorizar o acesso agora. Tente novamente.", "error")
        return redirect(url_for("portal.entry"))

    session["reg_email"] = email
    session["reg_phone"] = normalize_phone(phone)
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
        privacy_url=current_app.config["PRIVACY_POLICY_URL"],
        terms_version=current_app.config["TERMS_VERSION"],
    )


@bp.post("/guest/cadastro")
@limiter.limit("5 per minute")
def register_submit():
    portal_session = _get_portal_session()
    if not portal_session:
        flash("Sessao expirada. Por favor, conecte-se novamente.", "error")
        return redirect(url_for("portal.entry"))

    email = session.get("reg_email", "").strip().lower()
    phone = session.get("reg_phone", "").strip()
    name = request.form.get("name", "").strip()
    cpf = request.form.get("cpf", "").strip()
    marketing_optin = bool(request.form.get("marketing_optin"))
    terms_accepted = bool(request.form.get("terms_accepted"))

    if not terms_accepted:
        flash("Voce precisa aceitar os Termos de Uso para continuar.", "error")
        return redirect(url_for("portal.register"))
    if not name or len(name) < 3:
        flash("Nome invalido.", "error")
        return redirect(url_for("portal.register"))
    if not validate_cpf(cpf):
        flash("CPF invalido.", "error")
        return redirect(url_for("portal.register"))

    visitor = Visitor.create(name=name, email=email, phone=phone, cpf=cpf)
    db.session.flush()
    record_consent(visitor, marketing_optin=marketing_optin)
    db.session.commit()

    ok = authorize_visitor(portal_session, visitor)
    session.pop("reg_email", None)
    session.pop("reg_phone", None)

    if ok:
        return render_template(
            "portal/success.html",
            redirect_url=portal_session.redirect_url,
            name=visitor.name,
        )
    flash("Cadastro realizado, mas nao foi possivel autorizar agora. Tente novamente.", "error")
    return redirect(url_for("portal.entry"))
