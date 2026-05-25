from datetime import datetime, timezone
from app.extensions import db


class DataSubjectRequest(db.Model):
    """Solicitacoes dos titulares — LGPD Art. 18 (tabela data_subject_requests — migration 0003)."""
    __tablename__ = "data_subject_requests"

    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(
        db.Integer, db.ForeignKey("visitors.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    request_type = db.Column(db.String(30), nullable=False)  # ACCESS, DELETE, PORTABILITY...
    status = db.Column(db.String(20), nullable=False, default="PENDING", server_default="PENDING")
    notes = db.Column(db.Text, nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    channel = db.Column(db.String(50), nullable=True)
    requester_email = db.Column(db.String(150), nullable=True)
    requester_ip = db.Column(db.String(45), nullable=True)
    requested_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc),
        nullable=False, index=True
    )
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.String(100), nullable=True)

    visitor = db.relationship("Visitor", back_populates="data_requests")
