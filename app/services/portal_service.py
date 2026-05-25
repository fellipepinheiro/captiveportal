import uuid
from datetime import datetime, timezone, timedelta
import structlog
from flask import current_app, request as flask_request
from app.extensions import db
from app.models import Visitor, PortalSession, ConsentEvent
from app.services.unifi_api import get_unifi, UnifiAPIError

logger = structlog.get_logger(__name__)


def create_pending_session(client_mac, ap_mac, ssid, redirect_url) -> PortalSession:
    s = PortalSession(
        client_mac=(client_mac or "UNKNOWN").upper(),
        ap_mac=(ap_mac or "").upper() or None,
        ssid=ssid,
        redirect_url=redirect_url,
        ip_address=flask_request.remote_addr,
        user_agent=(flask_request.user_agent.string or "")[:512],
        correlation_id=str(uuid.uuid4()),
    )
    db.session.add(s)
    db.session.commit()
    return s


def authorize_visitor(portal_session: PortalSession, visitor: Visitor) -> bool:
    portal_session.visitor_id = visitor.id
    portal_session.consent_version = current_app.config["TERMS_VERSION"]
    try:
        api = get_unifi()
        site_id = current_app.config["UNIFI_SITE_ID"]
        portal_session.site_id = site_id
        client = api.find_client_by_mac(site_id, portal_session.client_mac)
        if not client:
            logger.warning("unifi_client_not_found", mac=portal_session.client_mac)
            db.session.commit()
            return False
        unifi_client_id = (
            client.get("id") or client.get("clientId") or client.get("_id")
        )
        minutes = current_app.config["UNIFI_SESSION_MINUTES"]
        api.authorize_guest(site_id, unifi_client_id, minutes)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        portal_session.mark_authorized(unifi_client_id, expires_at)
        db.session.commit()
        logger.info("guest_authorized", mac=portal_session.client_mac, visitor_id=visitor.id)
        return True
    except UnifiAPIError as e:
        logger.error("authorization_failed", error=str(e), mac=portal_session.client_mac)
        db.session.commit()
        return False


def record_consent(visitor: Visitor, marketing_optin: bool = False):
    """Registra evento de consentimento na tabela consent_events."""
    terms_version = current_app.config["TERMS_VERSION"]
    event = ConsentEvent(
        visitor_id=visitor.id,
        event_type="GRANT",
        terms_version=terms_version,
        ip_address=flask_request.remote_addr,
        user_agent=(flask_request.user_agent.string or "")[:512],
        channel="wifi_portal",
        marketing_opt_in=marketing_optin,
    )
    db.session.add(event)
    # Atualiza flags de consentimento direto no visitante tambem
    visitor.consent_version = terms_version
    visitor.consent_ip = flask_request.remote_addr
    visitor.consent_channel = "wifi_portal"
    visitor.marketing_opt_in = marketing_optin
    visitor.consent_at = datetime.now(timezone.utc)
