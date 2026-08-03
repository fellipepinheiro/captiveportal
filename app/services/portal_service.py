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

    # "pt-BR,pt;q=0.9,en;q=0.8" -> "pt-BR": so a preferencia principal
    idioma = flask_request.headers.get("Accept-Language", "").split(",")[0].strip()[:20]

    ps = PortalSession(
        client_mac   = client_mac,
        ap_mac       = ap_mac,
        ssid         = ssid,
        redirect_url = redirect_url,
        client_ip    = client_ip,
        user_agent   = ua,
        device_type  = device_type,
        os_hint      = os_hint,
        language     = idioma or None,
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

        # A autorizacao no controlador ja foi feita acima, antes de marcar a
        # sessao como autorizada. Nao ha uma segunda chamada aqui: a versao
        # que existia usava POST /v1/sites/<site>/guests, endpoint que o
        # controlador nao expoe (responde 404 "No endpoint POST ..."), entao
        # falhava silenciosamente a cada acesso.

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
        portal_session.close()
        db.session.commit()
        return True, msg
    except Exception:
        db.session.rollback()
        return False, 'Dispositivo desconectado, mas falhou ao atualizar a sessao.'


#: Motivos pelos quais um acesso nao se concretiza. Ficam no audit_logs
#: para alimentar a taxa de sucesso/erro e para investigar reclamacao de
#: visitante que "nao conseguiu conectar" — sem isso a tentativa some.
MOTIVOS = {
    'CPF_INVALIDO':      'CPF inválido',
    'TELEFONE_INVALIDO': 'Telefone inválido',
    'CAMPOS_VAZIOS':     'Campos obrigatórios em branco',
    'TERMOS_RECUSADOS':  'Não aceitou os termos',
    'VISITANTE_BLOQUEADO': 'Visitante bloqueado',
    'SESSAO_EXPIRADA':   'Sessão do portal expirada',
    'UNIFI_FALHOU':      'Falha ao autorizar no controlador',
    'NOME_INVALIDO':     'Nome incompleto',
    'EMAIL_INVALIDO':    'E-mail inválido',
    'ERRO_CADASTRO':     'Erro ao gravar o cadastro',
}


def log_acesso(evento: str, motivo: str = None, portal_session=None,
               visitor=None, detalhe: str = None):
    """Registra o desfecho de uma tentativa de acesso ao portal.

    Nunca propaga excecao: auditoria que derruba o fluxo do visitante seria
    pior que a ausencia do registro.
    """
    try:
        from app.models import AuditLog
        db.session.add(AuditLog(
            event_type=evento,
            status='SUCCESS' if evento == 'ACESSO_LIBERADO' else 'FAILURE',
            payload=MOTIVOS.get(motivo, motivo) if motivo else None,
            error_message=detalhe,
            visitor_id=visitor.id if visitor else None,
            session_id=portal_session.id if portal_session else None,
            ip_address=flask_request.remote_addr,
            actor='portal',
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.warning('[audit] falha ao registrar %s/%s', evento, motivo, exc_info=True)


def record_consent(visitor: Visitor, marketing_optin: bool = False, version: str = "1.0"):
    visitor.terms_accepted_at = datetime.now(timezone.utc)
    visitor.terms_version     = version
    visitor.marketing_optin   = marketing_optin


def refresh_consent(visitor: Visitor, version: str) -> bool:
    """Atualiza o aceite quando o visitante ja cadastrado marca os termos.

    O portal exige o aceite a cada acesso, mas so o cadastro novo gravava a
    versao — quem se cadastrou antes ficava para sempre com a versao antiga,
    ainda que estivesse aceitando a atual. Isso importa quando o texto muda:
    sem atualizar, o registro diria que a pessoa consentiu com uma clausula
    que ela nunca viu.
    """
    if visitor.terms_version == version:
        return False

    visitor.terms_accepted_at = datetime.now(timezone.utc)
    visitor.terms_version     = version
    try:
        from app.models import ConsentEvent
        db.session.add(ConsentEvent(
            visitor_id=visitor.id,
            event_type='UPDATE',
            terms_version=version,
            ip_address=flask_request.remote_addr,
            user_agent=flask_request.headers.get('User-Agent', '')[:300],
            channel='portal',
            marketing_opt_in=visitor.marketing_optin,
        ))
    except Exception:
        logger.warning('[consent] falha ao registrar evento de atualizacao', exc_info=True)
    db.session.commit()
    return True
