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
    client_mac = request.args.get("id") or request.args.get("mac")
    ap_mac = request.args.get("ap")
    ssid = request.args.get("ssid", "WiFi")
    redirect_url = request.args.get("url", "http://google.com")
    portal_session = create_pending_session(client_mac, ap_mac, ssid, redirect_url)
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

    visitor = Visitor.find_by_email_or_mobile(email, phone)
    if visitor:
        ok = authorize_visitor(portal_session, visitor)
        if ok:
            return render_template(
                "portal/success.html",
                redirect_url=portal_session.redirect_url,
                name=visitor.full_name,
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
    full_name = request.form.get("name", "").strip()
    cpf = request.form.get("cpf", "").strip()
    marketing_optin = bool(request.form.get("marketing_optin"))
    terms_accepted = bool(request.form.get("terms_accepted"))

    if not terms_accepted:
        flash("Voce precisa aceitar os Termos de Uso para continuar.", "error")
        return redirect(url_for("portal.register"))
    if not full_name or len(full_name) < 3:
        flash("Nome invalido.", "error")
        return redirect(url_for("portal.register"))
    if not validate_cpf(cpf):
        flash("CPF invalido.", "error")
        return redirect(url_for("portal.register"))

    # Verifica se ja existe visitante com este CPF (evita IntegrityError 1062)
    visitor = Visitor.query.filter_by(cpf=cpf).first()
    created = False
    if visitor is None:
        visitor = Visitor.create(full_name=full_name, email=email, mobile=phone, cpf=cpf)
        db.session.add(visitor)
        try:
            db.session.flush()
            created = True
        except IntegrityError:
            # Race condition: outro request inseriu entre o SELECT e o INSERT
            db.session.rollback()
            visitor = Visitor.query.filter_by(cpf=cpf).first()
            if visitor is None:
                flash("Erro ao cadastrar. Tente novamente.", "error")
                return redirect(url_for("portal.register"))

    if created:
        record_consent(visitor, marketing_optin=marketing_optin)

    db.session.commit()

    ok = authorize_visitor(portal_session, visitor)
    session.pop("reg_email", None)
    session.pop("reg_phone", None)

    if ok:
        return render_template(
            "portal/success.html",
            redirect_url=portal_session.redirect_url,
            name=visitor.full_name,
        )
    flash("Cadastro realizado, mas nao foi possivel autorizar agora. Tente novamente.", "error")
    return redirect(url_for("portal.entry"))
