from datetime import datetime
from app.extensions import db


class SiteConfig(db.Model):
    """Configuracoes persistidas no banco, editaveis pelo painel admin."""
    __tablename__ = 'site_config'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── Aparência ─────────────────────────────────────────────────────────────
    # portal_title        - Título exibido no portal (ex: Portal Wi-Fi)
    # portal_welcome      - Mensagem de boas-vindas
    # portal_btn_color    - Cor hex do botão (ex: #0f766e)
    # portal_accent       - Cor de destaque
    # portal_bg_from/via/to - Gradiente de fundo
    # logo_title          - Nome exibido ao lado da logo
    # custom_logo_url     - Caminho da logo enviada
    #
    # ── Sessão ────────────────────────────────────────────────────────────────
    # guest_auth_minutes  - Tempo de sessão em minutos
    # allow_revisit       - 'true'/'false' reautorizar visitante recorrente
    #
    # ── UniFi ─────────────────────────────────────────────────────────────────
    # unifi_base_url      - URL do controlador UniFi
    # unifi_api_key       - API Key do UniFi
    # unifi_site_id       - Site ID do UniFi
    #
    # ── Webhook ───────────────────────────────────────────────────────────────
    # webhook_enabled     - 'true' | 'false'
    # webhook_url         - URL destino do POST pós-autorização
    # webhook_secret      - Segredo HMAC-SHA256 (header X-Webhook-Signature)
    #
    # ── LGPD ──────────────────────────────────────────────────────────────────
    # terms_version       - Versão corrente dos termos (ex: 1.1)
    # privacy_policy_url  - URL da política de privacidade

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
