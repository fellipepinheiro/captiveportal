import os
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DEV_MODE = os.getenv('FLASK_ENV') == 'development'
DEFAULT_TIMEOUT = int(os.getenv('UNIFI_TIMEOUT', '20'))


def _build_session(api_key: str) -> requests.Session:
    """Cria sessão com retry automático (3x para erros 5xx/502/503)."""
    session = requests.Session()
    session.headers.update({
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    })
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


class UnifiAPI:
    """Cliente para a API UniFi Network (v1).

    Em modo DEV ou sem base_url configurada, todas as chamadas
    retornam dados mockados para facilitar o desenvolvimento local.
    """

    def __init__(self, base_url: str, api_key: str, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = (base_url or '').rstrip('/')
        self.timeout = timeout
        _placeholder = 'https://seu-unifi.exemplo.com'
        self.mock = DEV_MODE or not self.base_url or self.base_url == _placeholder

        if not self.mock:
            self.session = _build_session(api_key)
        else:
            logger.info('[UniFi] Modo MOCK ativo — nenhuma chamada real será feita.')

    # ------------------------------------------------------------------
    # Sites
    # ------------------------------------------------------------------
    def get_sites(self) -> list:
        if self.mock:
            return [{'id': 'mock-site-id', 'name': 'Mock Site'}]
        try:
            resp = self.session.get(f'{self.base_url}/v1/sites', timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error('[UniFi] get_sites falhou: %s', exc)
            raise

    # ------------------------------------------------------------------
    # Clientes
    # ------------------------------------------------------------------
    def find_client_by_mac(self, site_id: str, mac_address: str) -> dict | None:
        """Retorna o dict do cliente ou None se não encontrado."""
        if self.mock:
            logger.debug('[MOCK UniFi] find_client_by_mac site=%s mac=%s', site_id, mac_address)
            return {'id': f'mock-client-{mac_address}', 'macAddress': (mac_address or '').upper()}

        mac = (mac_address or '').upper()
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
            raise

        if isinstance(data, list):
            return data[0] if data else None
        items = data.get('data') or data.get('items') or []
        return items[0] if items else None

    # ------------------------------------------------------------------
    # Autorização
    # ------------------------------------------------------------------
    def authorize_guest(
        self,
        site_id: str,
        client_id: str,
        minutes: int = 480,
        upload_limit_kbps: int = 0,
        download_limit_kbps: int = 0,
    ) -> dict:
        """Autoriza o acesso do guest por X minutos.

        Args:
            minutes: Duração em minutos (0 = ilimitado).
            upload_limit_kbps: Rate limit de upload em kbps (0 = sem limite).
            download_limit_kbps: Rate limit de download em kbps (0 = sem limite).
        """
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
            raise

    # ------------------------------------------------------------------
    # Revogação (opcional)
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
            raise
