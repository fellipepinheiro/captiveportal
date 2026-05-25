from datetime import datetime, timedelta
from flask import current_app, request
from app.extensions import db
from app.models import PortalSession, Visitor, AuditLog
from app.services.unifi_api import UnifiAPI


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
    api = UnifiAPI(
        current_app.config['UNIFI_BASE_URL'],
        current_app.config['UNIFI_API_KEY'],
    )

    site_id = current_app.config['UNIFI_SITE_ID']
    client = api.find_client_by_mac(site_id, portal_session.client_mac)

    if not client:
        db.session.add(AuditLog(
            event_type='authorize_guest',
            status='error',
            payload=portal_session.client_mac,
            error_message='Cliente nao encontrado no UniFi',
        ))
        db.session.commit()
        raise ValueError('Cliente nao encontrado no UniFi')

    client_id = client.get('id') or client.get('clientId')
    api.authorize_guest(site_id, client_id, current_app.config['GUEST_AUTH_MINUTES'])

    portal_session.visitor_id = visitor.id
    portal_session.client_id = client_id
    portal_session.authorized = True
    portal_session.authorized_at = datetime.utcnow()
    portal_session.expires_at = datetime.utcnow() + timedelta(
        minutes=current_app.config['GUEST_AUTH_MINUTES']
    )

    db.session.add(AuditLog(
        event_type='authorize_guest',
        status='success',
        payload=portal_session.client_mac,
    ))
    db.session.add(portal_session)
    db.session.commit()
    return portal_session
