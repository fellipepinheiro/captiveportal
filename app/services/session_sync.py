"""Sincroniza as sessoes do portal com o estado real do controlador.

A Integration API do UniFi nao emite eventos nem webhooks de desconexao —
nao ha como o controlador avisar o portal quando alguem sai do wifi. A
unica forma de saber e consultando: um cliente que saiu da rede desaparece
da lista de clientes do site, e uma autorizacao que expirou passa a vir
com access.authorized = false.

Este modulo compara as sessoes marcadas como ativas no banco com o que o
controlador reporta e encerra as que ja nao valem, gravando quanto tempo
duraram. Sem isso o painel mostra como "Autorizado" quem ja foi embora.
"""
import logging
from datetime import datetime, timezone

from flask import current_app
from sqlalchemy import or_

from app.extensions import db
from app.models import PortalSession, Store
from app.services.unifi_api import get_unifi_for_store, UnifiAPIError

logger = logging.getLogger(__name__)


def _clientes_ativos(store: Store) -> set[str] | None:
    """MACs com autorizacao de guest ativa no controlador da loja.

    Retorna None se o controlador nao pode ser consultado — nesse caso
    nenhuma sessao e encerrada, para nao marcar todo mundo como desconectado
    so porque a rede falhou.
    """
    try:
        unifi = get_unifi_for_store(store)
    except Exception as exc:
        logger.warning('[sync] loja %s: nao foi possivel criar o cliente UniFi: %s', store.slug, exc)
        return None

    if unifi.mock:
        return None

    site_id = store.unifi_site_id or 'default'
    try:
        clientes = unifi.list_clients(site_id)
    except UnifiAPIError as exc:
        logger.warning('[sync] loja %s: falha ao listar clientes: %s', store.slug, exc)
        return None

    ativos = set()
    for c in clientes:
        mac = (c.get('macAddress') or '').lower()
        if not mac:
            continue
        acesso = c.get('access') or {}
        # Presenca na lista = conectado ao wifi.
        # authorized=False = ainda conectado, mas sem acesso liberado.
        if acesso.get('authorized') is True:
            ativos.add(mac)

    # Trafego vem da API classica e e complementar: se falhar, segue sem ele.
    trafego = unifi.get_client_traffic(unifi.site_name_from_id(site_id))
    return ativos, trafego


def sync_store(store: Store, incluir_sem_loja: bool = False) -> tuple[int, str]:
    """Encerra as sessoes da loja cujos dispositivos ja nao estao ativos.

    `incluir_sem_loja` faz a loja assumir tambem as sessoes com store_id
    nulo — sessoes criadas antes do suporte a multiplas lojas, que de outro
    modo nunca seriam encerradas. E o mesmo criterio de fallback que o
    portal usa para slug desconhecido.

    Retorna (quantidade_encerrada, motivo_se_pulou).
    """
    filtro = PortalSession.store_id == store.id
    if incluir_sem_loja:
        filtro = or_(filtro, PortalSession.store_id.is_(None))

    abertas = (
        PortalSession.query
        .filter(filtro, PortalSession.authorized.is_(True))
        .filter(PortalSession.expired_at.is_(None))
        .all()
    )
    if not abertas:
        return 0, 'nenhuma sessao aberta'

    resultado = _clientes_ativos(store)
    if resultado is None:
        return 0, 'controlador indisponivel (ou modo mock) — nada encerrado'
    ativos, trafego = resultado

    agora = datetime.now(timezone.utc)
    limite = store.session_minutes or current_app.config.get('UNIFI_SESSION_MINUTES', 480)
    encerradas = 0
    for ps in abertas:
        mac = (ps.client_mac or '').lower()

        # Grava o trafego antes de decidir: quem esta saindo tambem precisa
        # ter o consumo registrado, senao a sessao fecha zerada.
        uso = trafego.get(mac)
        if uso:
            ps.bytes_down = uso['rx']
            ps.bytes_up   = uso['tx']

        if mac in ativos:
            continue

        ps.close(agora, max_minutes=limite)
        encerradas += 1

    # commit mesmo sem encerramentos: o trafego das sessoes ativas mudou
    db.session.commit()
    if encerradas:
        logger.info('[sync] loja %s: %d sessao(oes) encerrada(s)', store.slug, encerradas)
    return encerradas, ''


def sync_all() -> dict:
    """Roda a sincronizacao em todas as lojas ativas."""
    resultado = {}
    for store in Store.query.filter_by(is_active=True).all():
        try:
            # A loja 'default' assume tambem as sessoes sem loja definida
            n, motivo = sync_store(store, incluir_sem_loja=(store.slug == 'default'))
            resultado[store.slug] = motivo or f'{n} encerrada(s)'
        except Exception as exc:
            db.session.rollback()
            logger.error('[sync] loja %s falhou: %s', store.slug, exc)
            resultado[store.slug] = f'erro: {exc}'
    return resultado
