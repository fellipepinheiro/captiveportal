import logging
from datetime import datetime, timezone
from flask import request as flask_request, current_app
from app.extensions import db
from app.models import Visitor, PortalSession, Store
from app.models.portal_session import PortalSession as PS
from app.services.unifi_api import get_unifi_for_store, UnifiAPIError

logger = logging.getLogger(__name__)


def create_pending_session(client_mac, ap_mac, ssid, redirect_url, store: Store = None) -> PortalSession:
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
        store_id     = store.id if store else None,
    )
    db.session.add(ps)
    db.session.commit()
    return ps


def authorize_visitor(portal_session: PortalSession, visitor: Visitor, store: Store = None) -> bool:
    site_id = (store.unifi_site_id if store and store.unifi_site_id
               else current_app.config.get('UNIFI_SITE_ID', 'default'))
    minutes = (store.session_minutes if store and store.session_minutes
               else current_app.config.get('UNIFI_SESSION_MINUTES', 480))

    try:
        unifi = get_unifi_for_store(store)
        client = unifi.find_client_by_mac(site_id, portal_session.client_mac)
        if not client or not client.get('id'):
            logger.warning(
                '[UniFi] cliente nao encontrado no controlador (site=%s mac=%s loja=%s)',
                site_id, portal_session.client_mac, store.slug if store else None,
            )
            return False
        unifi.authorize_guest(site_id, client['id'], minutes=minutes)
    except UnifiAPIError as exc:
        logger.error('[UniFi] falha ao autorizar guest (loja=%s): %s', store.slug if store else None, exc)
        return False

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


def revoke_session(portal_session: PortalSession, store: Store = None) -> tuple[bool, str]:
    """Desautoriza o dispositivo no controlador e encerra a sessao.

    Retorna (ok, mensagem). A sessao e encerrada localmente mesmo que o
    cliente ja nao esteja no controlador (desconectou por conta propria),
    porque nesse caso ele tambem nao tem mais acesso.
    """
    site_id = (store.unifi_site_id if store and store.unifi_site_id
               else current_app.config.get('UNIFI_SITE_ID', 'default'))

    # A API responde 422 com este codigo quando o cliente ja nao tem
    # autorizacao ativa. Para quem clicou em "derrubar" o objetivo ja esta
    # cumprido, entao isso nao e erro — so faltava sincronizar a sessao.
    JA_SEM_ACESSO = 'api.client.no-active-guest-authorization'

    try:
        unifi = get_unifi_for_store(store)
        client = unifi.find_client_by_mac(site_id, portal_session.client_mac)
        if client and client.get('id'):
            try:
                unifi.revoke_guest(site_id, client['id'])
                msg = 'Dispositivo desconectado.'
            except UnifiAPIError as exc:
                if exc.code != JA_SEM_ACESSO:
                    raise
                logger.info(
                    '[UniFi] cliente %s ja estava sem autorizacao — sincronizando sessao',
                    portal_session.client_mac,
                )
                msg = 'O dispositivo ja estava sem acesso; sessao encerrada.'
        else:
            logger.info(
                '[UniFi] cliente %s nao esta mais no controlador — encerrando so localmente',
                portal_session.client_mac,
            )
            msg = 'Dispositivo ja nao estava conectado; sessao encerrada.'
    except UnifiAPIError as exc:
        logger.error('[UniFi] falha ao revogar guest (mac=%s): %s', portal_session.client_mac, exc)
        return False, f'Nao foi possivel desconectar no controlador: {exc}'

    try:
        portal_session.authorized = False
        portal_session.expired_at = datetime.now(timezone.utc)
        db.session.commit()
        return True, msg
    except Exception:
        db.session.rollback()
        return False, 'Dispositivo desconectado, mas falhou ao atualizar a sessao.'


def record_consent(visitor: Visitor, marketing_optin: bool = False, version: str = "1.0"):
    visitor.terms_accepted_at = datetime.now(timezone.utc)
    visitor.terms_version     = version
    visitor.marketing_optin   = marketing_optin
