import requests
import structlog
from tenacity import (
    retry, stop_after_attempt, wait_exponential, retry_if_exception_type,
    RetryError,
)
from flask import current_app

logger = structlog.get_logger(__name__)


class UnifiAPIError(Exception):
    pass


class UnifiAPI:
    def __init__(self, base_url: str, api_key: str, verify_ssl: bool = False):
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })
        if not verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=False,  # deixa o RetryError ser levantado; convertemos abaixo
    )
    def _request_inner(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        resp = self._session.request(
            method, url, verify=self.verify_ssl, timeout=8, **kwargs
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        try:
            return self._request_inner(method, path, **kwargs)
        except RetryError as e:
            # tenacity esgotou as tentativas; a causa raiz e uma requests.RequestException
            cause = e.last_attempt.exception()
            logger.error("unifi_request_error", url=url, error=str(cause))
            raise UnifiAPIError(f"UniFi unreachable: {cause}") from cause
        except requests.HTTPError as e:
            logger.error("unifi_http_error", status=e.response.status_code, url=url)
            raise UnifiAPIError(f"UniFi API HTTP {e.response.status_code}") from e
        except requests.RequestException as e:
            # captura qualquer erro de conexao que nao passou pelo retry
            logger.error("unifi_request_error", url=url, error=str(e))
            raise UnifiAPIError(f"UniFi request error: {e}") from e

    def get_sites(self) -> list:
        return self._request("GET", "/v1/sites")

    def find_client_by_mac(self, site_id: str, mac: str):
        mac_upper = mac.upper()
        try:
            data = self._request(
                "GET",
                f"/v1/sites/{site_id}/clients",
                params={"filter": f"macAddress.eq('{mac_upper}')"},
            )
            return data[0] if isinstance(data, list) and data else None
        except UnifiAPIError:
            return None

    def authorize_guest(self, site_id: str, client_id: str, minutes: int = 480) -> dict:
        payload = {"action": "AUTHORIZE_GUEST_ACCESS", "timeLimitMinutes": minutes}
        return self._request(
            "POST",
            f"/v1/sites/{site_id}/clients/{client_id}/actions",
            json=payload,
        )


def get_unifi() -> UnifiAPI:
    return UnifiAPI(
        base_url=current_app.config["UNIFI_BASE_URL"],
        api_key=current_app.config["UNIFI_API_KEY"],
        verify_ssl=current_app.config["UNIFI_VERIFY_SSL"],
    )
