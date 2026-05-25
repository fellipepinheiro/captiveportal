import re
from datetime import datetime, timezone
from app.extensions import db


def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)


class Visitor(db.Model):
    __tablename__ = "visitors"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    cpf = db.Column(db.String(11), unique=True, nullable=False, index=True)
    email = db.Column(db.String(150), nullable=False, index=True)
    mobile = db.Column(db.String(20), nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    consent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    sessions = db.relationship("PortalSession", back_populates="visitor", lazy="dynamic")
    consents = db.relationship("ConsentRecord", back_populates="visitor", lazy="dynamic")

    @classmethod
    def find_by_email_or_mobile(cls, email: str, mobile: str):
        norm = _normalize_phone(mobile)
        return cls.query.filter(
            (cls.email == email.lower()) | (cls.mobile == norm)
        ).first()

    @classmethod
    def create(cls, full_name: str, email: str, mobile: str, cpf: str) -> "Visitor":
        norm_cpf = re.sub(r"\D", "", cpf)
        v = cls(
            full_name=full_name.strip(),
            email=email.lower().strip(),
            mobile=_normalize_phone(mobile),
            cpf=norm_cpf,
        )
        db.session.add(v)
        return v

    def to_dict(self):
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "mobile": self.mobile,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
