from datetime import datetime, timezone, timedelta
import structlog
from flask import current_app, request as flask_request
from app.extensions import db
from app.models import Visitor, PortalSession, ConsentRecord
from app.services.unifi_api import get_unifi, UnifiAPIError

logger = structlog.get_logger(__name__)


def create_pending_session(mac_client, mac_ap, ssid, redirect_url) -> PortalSession:
    s = PortalSession(
        mac_client=(mac_client or "UNKNOWN").upper(),
        mac_ap=(mac_ap or "").upper(),
        ssid=ssid,
        redirect_url=redirect_url,
        ip_address=flask_request.remote_addr,
        user_agent=flask_request.user_agent.string[:512],
        unifi_site_id=current_app.config["UNIFI_SITE_ID"],
    )
    db.session.add(s)
    db.session.commit()
    return s


def authorize_visitor(portal_session: PortalSession, visitor: Visitor) -> bool:
    portal_session.visitor_id = visitor.id
    try:
        api = get_unifi()
        site_id = portal_session.unifi_site_id or current_app.config["UNIFI_SITE_ID"]
        client = api.find_client_by_mac(site_id, portal_session.mac_client)
        if not client:
            logger.warning("unifi_client_not_found", mac=portal_session.mac_client)
            db.session.commit()
            return False
        client_id = client.get("id") or client.get("clientId") or client.get("_id")
        minutes = current_app.config["UNIFI_SESSION_MINUTES"]
        api.authorize_guest(site_id, client_id, minutes)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        portal_session.mark_authorized(client_id, expires_at)
        db.session.commit()
        logger.info("guest_authorized", mac=portal_session.mac_client, visitor_id=visitor.id)
        return True
    except UnifiAPIError as e:
        logger.error("authorization_failed", error=str(e), mac=portal_session.mac_client)
        db.session.commit()
        return False


def record_consent(visitor: Visitor, marketing_optin: bool = False):
    c = ConsentRecord(
        visitor_id=visitor.id,
        terms_version=current_app.config["TERMS_VERSION"],
        marketing_optin=marketing_optin,
        ip_address=flask_request.remote_addr,
        user_agent=flask_request.user_agent.string[:512],
    )
    db.session.add(c)
