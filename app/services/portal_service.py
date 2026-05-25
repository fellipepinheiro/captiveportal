from datetime import datetime, timezone
from flask import request as flask_request
from app.extensions import db
from app.models import Visitor, PortalSession
from app.models.portal_session import PortalSession as PS


def create_pending_session(client_mac, ap_mac, ssid, redirect_url) -> PortalSession:
    ua = flask_request.headers.get("User-Agent", "")[:300]
    client_ip = flask_request.remote_addr
    device_type, os_hint = PS.detect_device(ua)

    ps = PortalSession(
        client_mac   = client_mac,
        ap_mac       = ap_mac,
        ssid         = ssid,
        redirect_url = redirect_url,
        client_ip    = client_ip,
        user_agent   = ua,
        device_type  = device_type,
        os_hint      = os_hint,
        authorized   = False,
    )
    db.session.add(ps)
    db.session.commit()
    return ps


def authorize_visitor(portal_session: PortalSession, visitor: Visitor) -> bool:
    try:
        portal_session.visitor_id    = visitor.id
        portal_session.authorized    = True
        portal_session.authorized_at = datetime.now(timezone.utc)
        visitor.touch()
        db.session.commit()

        # ── Webhook pós-autorização ────────────────────────────────────────
        try:
            from app.services.webhook_service import fire_authorized
            fire_authorized(portal_session, visitor)
        except Exception:
            pass  # nunca bloqueia o fluxo principal

        return True
    except Exception:
        db.session.rollback()
        return False


def record_consent(visitor: Visitor, marketing_optin: bool = False, version: str = "1.0"):
    visitor.terms_accepted_at = datetime.now(timezone.utc)
    visitor.terms_version     = version
    visitor.marketing_optin   = marketing_optin
