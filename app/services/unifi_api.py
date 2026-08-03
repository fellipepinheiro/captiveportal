import os
import logging
import requests
from flask import current_app
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DEV_MODE = os.getenv('FLASK_ENV') == 'development'
DEFAULT_TIMEOUT = int(os.getenv('UNIFI_TIMEOUT', '20'))


def _mock_override():
    """UNIFI_MOCK sobrepoe a deteccao automatica de modo mock.

    Sem essa variavel, rodar em FLASK_ENV=development forcaria mock e
    impediria testar contra um controlador real. Retorna None quando a
    variavel nao esta definida (mantem o comportamento automatico).
    """
    raw = os.getenv('UNIFI_MOCK')
    if raw is None or raw.strip() == '':
        return None
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


class UnifiAPIError(Exception):
    """Excecao base para erros da API UniFi."""
    pass


def _build_session(api_key: str, verify_ssl: bool) -> requests.Session:
    """Cria sessao com retry automatico (3x para erros 5xx/502/503)."""
    session = requests.Session()
    session.headers.update({
        # A UniFi Network Integration API autentica por X-API-KEY.
        # 'Authorization: Bearer' e recusado com 401.
        'X-API-KEY': api_key,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    })
    session.verify = verify_ssl
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=['GET', 'POST'],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


def get_unifi_for_store(store=None) -> 'UnifiAPI':
    """Factory que cria um UnifiAPI a partir das credenciais de uma Store.

    Se `store` for None (loja não identificada), cai para as configs
    globais da app (compatibilidade com instalacoes de loja unica).
    """
    if store is not None:
        return UnifiAPI(
            base_url=store.unifi_base_url or '',
            api_key=store.unifi_api_key or '',
            verify_ssl=bool(store.unifi_verify_ssl),
            timeout=int(current_app.config.get('UNIFI_TIMEOUT', DEFAULT_TIMEOUT)),
        )
    return UnifiAPI(
        base_url=current_app.config.get('UNIFI_BASE_URL', ''),
        api_key=current_app.config.get('UNIFI_API_KEY', ''),
        verify_ssl=bool(current_app.config.get('UNIFI_VERIFY_SSL', False)),
        timeout=int(current_app.config.get('UNIFI_TIMEOUT', DEFAULT_TIMEOUT)),
    )


class UnifiAPI:
    """Cliente para a API UniFi Network (v1).

    Em modo DEV ou sem base_url configurada, todas as chamadas
    retornam dados mockados para facilitar o desenvolvimento local.
    """

    def __init__(self, base_url: str, api_key: str, timeout: int = DEFAULT_TIMEOUT, verify_ssl: bool = True):
        self.base_url = (base_url or '').rstrip('/')
        self.timeout = timeout
        _placeholder = 'https://seu-unifi.exemplo.com'

        override = _mock_override()
        if override is None:
            self.mock = DEV_MODE or not self.base_url or self.base_url == _placeholder
        else:
            # Sem base_url nao ha o que chamar — mock continua obrigatorio.
            self.mock = override or not self.base_url or self.base_url == _placeholder

        if not self.mock:
            self.session = _build_session(api_key, verify_ssl)
        else:
            logger.info('[UniFi] Modo MOCK ativo — nenhuma chamada real sera feita.')

    # ------------------------------------------------------------------
    # Sites
    # ------------------------------------------------------------------
    def get_sites(self) -> list:
        if self.mock:
            return [{'id': 'mock-site-id', 'name': 'Mock Site'}]
        try:
            resp = self.session.get(f'{self.base_url}/v1/sites', timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error('[UniFi] get_sites falhou: %s', exc)
            raise UnifiAPIError(str(exc)) from exc

        # A API v1 responde paginado: {"offset":..,"count":..,"data":[...]}
        if isinstance(data, list):
            return data
        return data.get('data') or data.get('items') or []

    # ------------------------------------------------------------------
    # Clientes
    # ------------------------------------------------------------------
    def find_client_by_mac(self, site_id: str, mac_address: str) -> dict | None:
        """Retorna o dict do cliente ou None se nao encontrado."""
        if self.mock:
            logger.debug('[MOCK UniFi] find_client_by_mac site=%s mac=%s', site_id, mac_address)
            return {'id': f'mock-client-{mac_address}', 'macAddress': (mac_address or '').lower()}

        # O filtro da API e case-sensitive e os MACs sao guardados em
        # minusculas — enviar em maiusculas devolve lista vazia.
        mac = (mac_address or '').lower()
        try:
            resp = self.session.get(
                f'{self.base_url}/v1/sites/{site_id}/clients',
                params={'filter': f"macAddress.eq('{mac}')"},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error('[UniFi] find_client_by_mac falhou (mac=%s): %s', mac, exc)
            raise UnifiAPIError(str(exc)) from exc

        if isinstance(data, list):
            return data[0] if data else None
        items = data.get('data') or data.get('items') or []
        return items[0] if items else None

    # ------------------------------------------------------------------
    # Autorizacao
    # ------------------------------------------------------------------
    def authorize_guest(
        self,
        site_id: str,
        client_id: str,
        minutes: int = 480,
        upload_limit_kbps: int = 0,
        download_limit_kbps: int = 0,
    ) -> dict:
        """Autoriza o acesso do guest por X minutos."""
        if self.mock:
            logger.debug(
                '[MOCK UniFi] authorize_guest site=%s client=%s minutes=%s',
                site_id, client_id, minutes,
            )
            return {'ok': True, 'mock': True}

        payload: dict = {
            'action': 'AUTHORIZE_GUEST_ACCESS',
            'timeLimitMinutes': minutes,
        }
        if upload_limit_kbps > 0:
            payload['uploadLimitKbps'] = upload_limit_kbps
        if download_limit_kbps > 0:
            payload['downloadLimitKbps'] = download_limit_kbps

        try:
            resp = self.session.post(
                f'{self.base_url}/v1/sites/{site_id}/clients/{client_id}/actions',
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            logger.info('[UniFi] Guest autorizado: site=%s client=%s minutes=%s', site_id, client_id, minutes)
            return resp.json() if resp.content else {'ok': True}
        except Exception as exc:
            logger.error('[UniFi] authorize_guest falhou (client=%s): %s', client_id, exc)
            raise UnifiAPIError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Revogacao (opcional)
    # ------------------------------------------------------------------
    def revoke_guest(self, site_id: str, client_id: str) -> dict:
        """Revoga o acesso de um guest autorizado."""
        if self.mock:
            logger.debug('[MOCK UniFi] revoke_guest client=%s', client_id)
            return {'ok': True, 'mock': True}

        try:
            resp = self.session.post(
                f'{self.base_url}/v1/sites/{site_id}/clients/{client_id}/actions',
                json={'action': 'UNAUTHORIZE_GUEST_ACCESS'},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            logger.info('[UniFi] Guest revogado: site=%s client=%s', site_id, client_id)
            return resp.json() if resp.content else {'ok': True}
        except Exception as exc:
            logger.error('[UniFi] revoke_guest falhou (client=%s): %s', client_id, exc)
            raise UnifiAPIError(str(exc)) from exc
