from datetime import datetime
from app.extensions import db


class DataSubjectRequest(db.Model):
    """
    Solicitações dos titulares de dados — LGPD Art. 18.

    Tipos de solicitação (request_type):
        ACCESS      — titular solicita acesso aos seus dados
        CORRECT     — titular solicita retificação de dados
        DELETE      — titular solicita exclusão dos dados
        EXPORT      — titular solicita portabilidade/exportação
        OPT_OUT     — titular revoga consentimento de marketing
        RESTRICT    — titular solicita restrição de tratamento

    Status:
        PENDING     — aguardando análise
        IN_PROGRESS — em tratamento
        DONE        — concluído
        REJECTED    — rejeitado com justificativa
    """
    __tablename__ = 'data_subject_requests'

    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(
        db.Integer, db.ForeignKey('visitors.id', ondelete='SET NULL'),
        nullable=True, index=True
    )

    request_type = db.Column(db.String(30), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='PENDING', index=True)
    notes = db.Column(db.Text, nullable=True)                  # observações internas
    rejection_reason = db.Column(db.Text, nullable=True)       # justificativa se REJECTED

    # Canal de origem da solicitação
    channel = db.Column(db.String(50), nullable=True)          # "portal", "email", "admin"
    requester_email = db.Column(db.String(150), nullable=True) # e-mail fornecido pelo solicitante
    requester_ip = db.Column(db.String(45), nullable=True)

    # Timestamps de ciclo de vida
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.String(100), nullable=True)     # ex: "admin:3"

    visitor = db.relationship('Visitor', back_populates='data_requests')

    def __repr__(self):
        return (
            f'<DataSubjectRequest id={self.id} visitor_id={self.visitor_id} '
            f'type={self.request_type} status={self.status}>'
        )
