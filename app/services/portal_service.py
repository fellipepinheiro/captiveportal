import logging
from datetime import datetime, timedelta
from flask import current_app, request
from app.extensions import db
from app.models import PortalSession, Visitor, AuditLog
from app.services.unifi_api import UnifiAPI

logger = logging.getLogger(__name__)


def normalize_digits(value):
    return ''.join(ch for ch in (value or '') if ch.isdigit())


def create_or_update_pending_session(ap_mac, client_mac, ssid, redirect_url, token):
    portal_session = (
        PortalSession.query
        .filter_by(client_mac=client_mac, authorized=False)
        .order_by(PortalSession.id.desc())
        .first()
    )

    if not portal_session:
        portal_session = PortalSession(client_mac=client_mac)

    portal_session.ap_mac = ap_mac
    portal_session.ssid = ssid
    portal_session.redirect_url = redirect_url
    portal_session.query_token = token
    portal_session.ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    portal_session.user_agent = request.headers.get('User-Agent')

    db.session.add(portal_session)
    db.session.commit()
    return portal_session


def find_visitor(email, mobile):
    email = (email or '').strip().lower()
    mobile = normalize_digits(mobile)
    return Visitor.query.filter(
        (Visitor.email == email) | (Visitor.mobile == mobile)
    ).first()


def upsert_visitor(email, mobile, full_name=None, cpf=None):
    visitor = find_visitor(email, mobile)
    if visitor:
        return visitor, False

    visitor = Visitor(
        full_name=full_name,
        cpf=normalize_digits(cpf),
        email=(email or '').strip().lower(),
        mobile=normalize_digits(mobile),
        consent_at=datetime.utcnow(),
    )
    db.session.add(visitor)
    db.session.commit()
    return visitor, True


def authorize_session(portal_session, visitor):
    """Autoriza o acesso do visitante via API UniFi.
    Retorna True em caso de sucesso.
    Lanca UnifiAuthError em caso de falha.
    """
    api = UnifiAPI(
        current_app.config.get('UNIFI_BASE_URL', ''),
        current_app.config.get('UNIFI_API_KEY', ''),
    )

    site_id = current_app.config.get('UNIFI_SITE_ID', 'default')
    minutes = current_app.config.get('GUEST_AUTH_MINUTES', 480)

    try:
        client = api.find_client_by_mac(site_id, portal_session.client_mac)
    except Exception as exc:
        logger.error('Erro ao buscar cliente no UniFi: %s', exc)
        _log_error(portal_session, str(exc))
        raise UnifiAuthError(f'Nao foi possivel contactar o controlador UniFi: {exc}') from exc

    if not client:
        msg = f'Cliente MAC {portal_session.client_mac} nao encontrado no UniFi'
        logger.warning(msg)
        _log_error(portal_session, msg)
        raise UnifiAuthError(msg)

    client_id = client.get('id') or client.get('clientId')

    try:
        api.authorize_guest(site_id, client_id, minutes)
    except Exception as exc:
        logger.error('Erro ao autorizar guest no UniFi: %s', exc)
        _log_error(portal_session, str(exc))
        raise UnifiAuthError(f'Falha ao autorizar acesso: {exc}') from exc

    portal_session.visitor_id = visitor.id
    portal_session.client_id = client_id
    portal_session.authorized = True
    portal_session.authorized_at = datetime.utcnow()
    portal_session.expires_at = datetime.utcnow() + timedelta(minutes=minutes)

    db.session.add(AuditLog(
        event_type='authorize_guest',
        status='success',
        payload=portal_session.client_mac,
    ))
    db.session.add(portal_session)
    db.session.commit()
    return True


def _log_error(portal_session, message):
    try:
        db.session.add(AuditLog(
            event_type='authorize_guest',
            status='error',
            payload=getattr(portal_session, 'client_mac', ''),
            error_message=message,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()


class UnifiAuthError(Exception):
    pass
