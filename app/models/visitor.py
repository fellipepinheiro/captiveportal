from datetime import datetime, timezone
from app.extensions import db


class Visitor(db.Model):
    __tablename__ = "visitors"

    id          = db.Column(db.Integer, primary_key=True)
    full_name   = db.Column(db.String(120))
    email       = db.Column(db.String(120), unique=True, index=True)
    mobile      = db.Column(db.String(20),  unique=True, index=True)
    cpf         = db.Column(db.String(14),  unique=True, index=True)
    is_active   = db.Column(db.Boolean, default=True)
    is_blocked  = db.Column(db.Boolean, default=False, index=True)  # banimento
    block_reason= db.Column(db.String(200))

    # Estatísticas
    visit_count = db.Column(db.Integer, default=0)   # quantas vezes se conectou
    last_seen   = db.Column(db.DateTime(timezone=True))

    # Datas
    created_at  = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at  = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc))

    # Consentimento LGPD
    terms_accepted_at   = db.Column(db.DateTime(timezone=True))
    terms_version       = db.Column(db.String(10))
    marketing_optin     = db.Column(db.Boolean, default=False)

    @classmethod
    def create(cls, full_name, email, mobile, cpf,
               terms_version=None, marketing_optin=False):
        v = cls(
            full_name=full_name,
            email=email,
            mobile=mobile,
            cpf=cpf,
            terms_accepted_at=datetime.now(timezone.utc),
            terms_version=terms_version,
            marketing_optin=marketing_optin,
            visit_count=1,
            last_seen=datetime.now(timezone.utc),
        )
        return v

    @classmethod
    def find_by_email_or_mobile(cls, email: str, mobile: str):
        return cls.query.filter(
            (cls.email == email) | (cls.mobile == mobile)
        ).first()

    def touch(self):
        """Atualiza contadores de visita."""
        self.visit_count = (self.visit_count or 0) + 1
        self.last_seen   = datetime.now(timezone.utc)

    def __repr__(self):
        return f"<Visitor {self.id} {self.email}>"
