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
    store_id    = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True, index=True)

    # Rede / dispositivo
    client_ip   = db.Column(db.String(45))          # suporta IPv6
    user_agent  = db.Column(db.String(300))
    device_type = db.Column(db.String(30))          # mobile | desktop | tablet
    os_hint     = db.Column(db.String(50))          # Android, iOS, Windows…

    # Geolocalizacao (informada pelo navegador, mediante consentimento)
    latitude          = db.Column(db.Numeric(10, 7))
    longitude         = db.Column(db.Numeric(10, 7))
    location_accuracy = db.Column(db.Integer)   # raio de incerteza em metros
    location_at       = db.Column(db.DateTime(timezone=True))

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
    store       = db.relationship("Store", backref="sessions", lazy="select")

    # ── helpers ────────────────────────────────────────────────────────────
    @property
    def is_active(self):
        return self.authorized and self.expired_at is None

    @property
    def started_at(self):
        """Inicio efetivo do acesso: quando foi autorizado.

        Cai para created_at nas sessoes que nunca chegaram a ser
        autorizadas (o visitante abriu o portal e desistiu).
        """
        return self.authorized_at or self.created_at

    @property
    def duration(self):
        """Minutos de conexao, calculados dos timestamps.

        Nao usa duration_minutes como fonte: sessoes encerradas antes de o
        calculo existir ficaram com o campo zerado, ainda que authorized_at
        e expired_at registrem corretamente o intervalo. Os timestamps sao
        a fonte confiavel; o campo serve de fallback.

        Retorna None enquanto a sessao nao terminou.
        """
        inicio, fim = self.started_at, self.expired_at
        if not (inicio and fim):
            return None

        if inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=timezone.utc)
        if fim.tzinfo is None:
            fim = fim.replace(tzinfo=timezone.utc)

        minutos = max(0, int((fim - inicio).total_seconds() // 60))
        # Mesmo teto aplicado no encerramento: ninguem fica conectado alem
        # do tempo de autorizacao concedido pela loja.
        limite = self.store.session_minutes if self.store else None
        if limite:
            minutos = min(minutos, limite)
        return minutos

    def close(self, when: datetime = None, max_minutes: int = None):
        """Encerra a sessao e calcula quanto tempo durou.

        Centralizado aqui porque o encerramento acontece em dois caminhos —
        o botao "derrubar" do painel e a sincronizacao periodica — e a
        duracao precisa ser gravada igual nos dois.

        `max_minutes` limita a duracao ao tempo de autorizacao concedido.
        A saida do visitante so e percebida na verificacao seguinte, entao
        se a sincronizacao ficar parada (manutencao, controlador fora do ar)
        a diferenca bruta viraria dias — mas a autorizacao do UniFi expira
        sozinha em `max_minutes`, logo ninguem ficou conectado alem disso.
        """
        when = when or datetime.now(timezone.utc)
        self.authorized = False
        self.expired_at = when

        inicio = self.started_at
        if inicio:
            if inicio.tzinfo is None:
                inicio = inicio.replace(tzinfo=timezone.utc)
            minutos = max(0, int((when - inicio).total_seconds() // 60))
            if max_minutes:
                minutos = min(minutos, max_minutes)
            self.duration_minutes = minutos

    @property
    def distancia_da_loja(self):
        """Distancia em km entre o visitante e a loja, ou None.

        Formula de haversine — precisao mais que suficiente para as
        distancias envolvidas (raio de influencia de uma loja).
        """
        if self.latitude is None or self.longitude is None:
            return None
        loja = self.store
        if not loja or loja.latitude is None or loja.longitude is None:
            return None

        from math import radians, sin, cos, asin, sqrt
        lat1, lon1 = radians(float(self.latitude)), radians(float(self.longitude))
        lat2, lon2 = radians(float(loja.latitude)), radians(float(loja.longitude))
        a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
        return round(6371 * 2 * asin(sqrt(a)), 2)

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
