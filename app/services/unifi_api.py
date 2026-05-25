import os
import requests

DEV_MODE = os.getenv('FLASK_ENV') == 'development'


class UnifiAPI:
    def __init__(self, base_url, api_key):
        self.base_url = (base_url or '').rstrip('/')
        self.mock = DEV_MODE or not self.base_url or self.base_url in ('', 'https://seu-unifi.exemplo.com')
        if not self.mock:
            self.session = requests.Session()
            self.session.headers.update({
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            })

    def get_sites(self):
        if self.mock:
            return [{'id': 'mock-site', 'name': 'Mock Site'}]
        response = self.session.get(f'{self.base_url}/v1/sites', timeout=20)
        response.raise_for_status()
        return response.json()

    def find_client_by_mac(self, site_id, mac_address):
        if self.mock:
            print(f'[MOCK UniFi] find_client_by_mac site={site_id} mac={mac_address}')
            return {'id': f'mock-client-{mac_address}', 'macAddress': mac_address}

        response = self.session.get(
            f'{self.base_url}/v1/sites/{site_id}/clients',
            params={'filter': f"macAddress.eq('{(mac_address or '').upper()}')"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data[0] if data else None
        items = data.get('data', []) if isinstance(data, dict) else []
        return items[0] if items else None

    def authorize_guest(self, site_id, client_id, minutes=480):
        if self.mock:
            print(f'[MOCK UniFi] authorize_guest site={site_id} client={client_id} minutes={minutes}')
            return {'ok': True, 'mock': True}

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
