import re
from datetime import datetime, timezone
from app.extensions import db

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class Store(db.Model):
    """Uma loja/unidade física, com seu próprio controlador UniFi (UDM Pro).

    Identificada na URL do portal por `slug` — cada UDM Pro deve apontar seu
    'External Portal Server' (Hotspot Manager) para /guest/s/<slug>/.
    """
    __tablename__ = "stores"

    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)

    # ── UniFi ─────────────────────────────────────────────────────
    unifi_base_url   = db.Column(db.String(255))
    unifi_api_key    = db.Column(db.String(255))
    unifi_site_id    = db.Column(db.String(80), default="default")
    unifi_verify_ssl = db.Column(db.Boolean, default=False)
    session_minutes  = db.Column(db.Integer, nullable=True)  # None = usa o default global

    is_active  = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    @staticmethod
    def slugify(name: str) -> str:
        slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
        return slug[:80] or "loja"

    def __repr__(self):
        return f"<Store {self.id} {self.slug}>"
