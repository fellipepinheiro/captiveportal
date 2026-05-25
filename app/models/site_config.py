from datetime import datetime
from app.extensions import db


class SiteConfig(db.Model):
    """Configuracoes persistidas no banco, editaveis pelo painel admin."""
    __tablename__ = 'site_config'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Chaves utilizadas:
    # portal_title        - Titulo exibido no portal (ex: Portal Wi-Fi)
    # portal_welcome      - Mensagem de boas-vindas
    # portal_btn_color    - Cor hex do botao (ex: #0f766e)
    # guest_auth_minutes  - Tempo de sessao em minutos
    # unifi_base_url      - URL do controlador UniFi
    # unifi_api_key       - API Key do UniFi
    # unifi_site_id       - Site ID do UniFi
    # allow_revisit       - 'true'/'false' reautorizar visitante recorrente

    @classmethod
    def get(cls, key: str, default=None):
        row = cls.query.filter_by(key=key).first()
        return row.value if row else default

    @classmethod
    def set(cls, key: str, value):
        row = cls.query.filter_by(key=key).first()
        if row:
            row.value = str(value) if value is not None else None
            row.updated_at = datetime.utcnow()
        else:
            row = cls(key=key, value=str(value) if value is not None else None)
            db.session.add(row)
        db.session.flush()
        return row
