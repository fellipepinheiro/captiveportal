from datetime import datetime, timezone
from app.extensions import db


class PortalSession(db.Model):
    __tablename__ = "portal_sessions"

    # Índice composto para queries da dashboard (authorized + created_at)
    __table_args__ = (
        db.Index("ix_portal_sessions_auth_created", "authorized", "created_at"),
    )

    id          = db.Column(db.Integer, primary_key=True)
    client_mac  = db.Column(db.String(20), index=True)
    ap_mac      = db.Column(db.String(20))
    ssid        = db.Column(db.String(64))
    redirect_url= db.Column(db.String(512))
    visitor_id  = db.Column(db.Integer, db.ForeignKey("visitors.id"), nullable=True, index=True)

    # Rede / dispositivo
    client_ip   = db.Column(db.String(45))          # suporta IPv6
    user_agent  = db.Column(db.String(300))
    device_type = db.Column(db.String(30))          # mobile | desktop | tablet
    os_hint     = db.Column(db.String(50))          # Android, iOS, Windows…

    # Estado
    authorized      = db.Column(db.Boolean, default=False, index=True)
    authorized_at   = db.Column(db.DateTime(timezone=True))
    expired_at      = db.Column(db.DateTime(timezone=True))  # NULL = ativo
    duration_minutes= db.Column(db.Integer, default=0)       # quanto tempo ficou online
    bytes_up        = db.Column(db.BigInteger, default=0)     # tráfego (se coletado via API)
    bytes_down      = db.Column(db.BigInteger, default=0)

    created_at  = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at  = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc))

    visitor     = db.relationship("Visitor", backref="sessions", lazy="select")

    # ── helpers ────────────────────────────────────────────────────────────
    @property
    def is_active(self):
        return self.authorized and self.expired_at is None

    @classmethod
    def detect_device(cls, ua: str) -> tuple[str, str]:
        """Retorna (device_type, os_hint) a partir do User-Agent."""
        ua_lower = ua.lower()
        os_hint = "Desconhecido"
        if "android" in ua_lower:    os_hint = "Android"
        elif "iphone" in ua_lower:   os_hint = "iOS"
        elif "ipad" in ua_lower:     os_hint = "iOS"
        elif "windows" in ua_lower:  os_hint = "Windows"
        elif "macintosh" in ua_lower or "mac os" in ua_lower: os_hint = "macOS"
        elif "linux" in ua_lower:    os_hint = "Linux"
        elif "chromeos" in ua_lower: os_hint = "ChromeOS"

        if any(x in ua_lower for x in ("mobile", "android", "iphone")):
            device_type = "mobile"
        elif any(x in ua_lower for x in ("tablet", "ipad")):
            device_type = "tablet"
        else:
            device_type = "desktop"

        return device_type, os_hint

    def __repr__(self):
        return f"<PortalSession {self.id} mac={self.client_mac} auth={self.authorized}>"
