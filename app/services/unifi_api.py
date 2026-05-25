import requests


class UnifiAPI:
    def __init__(self, base_url, api_key):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        })

    def get_sites(self):
        response = self.session.get(f'{self.base_url}/v1/sites', timeout=20)
        response.raise_for_status()
        return response.json()

    def find_client_by_mac(self, site_id, mac_address):
        response = self.session.get(
            f'{self.base_url}/v1/sites/{site_id}/clients',
            params={'filter': f"macAddress.eq('{mac_address.upper()}')"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            return data[0] if data else None

        items = data.get('data', []) if isinstance(data, dict) else []
        return items[0] if items else None

    def authorize_guest(self, site_id, client_id, minutes=480):
        payload = {
            'action': 'AUTHORIZE_GUEST_ACCESS',
            'timeLimitMinutes': minutes,
        }
        response = self.session.post(
            f'{self.base_url}/v1/sites/{site_id}/clients/{client_id}/actions',
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        return response.json() if response.content else {'ok': True}
