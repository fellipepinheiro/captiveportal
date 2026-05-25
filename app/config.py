import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'change-me')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///portal.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UNIFI_BASE_URL = os.getenv('UNIFI_BASE_URL', '')
    UNIFI_API_KEY = os.getenv('UNIFI_API_KEY', '')
    UNIFI_SITE_ID = os.getenv('UNIFI_SITE_ID', 'default')
    GUEST_AUTH_MINUTES = int(os.getenv('GUEST_AUTH_MINUTES', '480'))

    WTF_CSRF_ENABLED = os.getenv('WTF_CSRF_ENABLED', 'true').lower() == 'true'
