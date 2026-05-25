import hashlib
import re
from datetime import datetime, timezone
from app.extensions import db


def _hash_cpf(cpf: str) -> str:
    normalized = re.sub(r"\D", "", cpf)
    return hashlib.sha256(normalized.encode()).hexdigest()


def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)


class Visitor(db.Model):
    __tablename__ = "visitors"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=False, index=True)
    cpf_hash = db.Column(db.String(64), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    sessions = db.relationship("PortalSession", back_populates="visitor", lazy="dynamic")
    consents = db.relationship("ConsentRecord", back_populates="visitor", lazy="dynamic")

    @classmethod
    def find_by_email_or_phone(cls, email: str, phone: str):
        norm_phone = _normalize_phone(phone)
        return cls.query.filter(
            (cls.email == email.lower()) | (cls.phone == norm_phone)
        ).first()

    @classmethod
    def create(cls, name: str, email: str, phone: str, cpf: str) -> "Visitor":
        v = cls(
            name=name.strip(),
            email=email.lower().strip(),
            phone=_normalize_phone(phone),
            cpf_hash=_hash_cpf(cpf),
        )
        db.session.add(v)
        return v

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
