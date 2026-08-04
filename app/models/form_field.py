from datetime import datetime, timezone
from app.extensions import db

#: Campos que o sistema conhece e sabe validar. Os quatro primeiros tem
#: coluna propria em visitors; os demais vao para extra_data (JSON), assim
#: acrescentar campo novo nao exige migration.
CAMPOS_CONHECIDOS = {
    'cpf':       {'label': 'CPF',              'tipo': 'cpf',   'coluna': 'cpf'},
    'mobile':    {'label': 'Celular',          'tipo': 'phone', 'coluna': 'mobile'},
    'email':     {'label': 'E-mail',           'tipo': 'email', 'coluna': 'email'},
    'full_name': {'label': 'Nome completo',    'tipo': 'name',  'coluna': 'full_name'},
    'birthdate': {'label': 'Data de nascimento', 'tipo': 'date',  'coluna': None},
    'gender':    {'label': 'Gênero',           'tipo': 'select', 'coluna': None,
                  'opcoes': 'Feminino\nMasculino\nPrefiro não informar'},
    'zipcode':   {'label': 'CEP',              'tipo': 'zipcode', 'coluna': None},
}

#: Apenas estes podem ser chave: precisam identificar uma pessoa de forma
#: estavel e serem unicos. Nome nao serve (homonimos), data de nascimento
#: muito menos.
CHAVES_POSSIVEIS = ('cpf', 'mobile', 'email')

TIPOS = {
    'text':    'Texto livre',
    'cpf':     'CPF',
    'phone':   'Celular',
    'email':   'E-mail',
    'name':    'Nome completo',
    'date':    'Data',
    'number':  'Número',
    'select':  'Lista de opções',
    'zipcode': 'CEP',
}


class FormField(db.Model):
    """Um campo do formulário do portal, configurável pelo admin.

    `stage` separa o que e pedido na identificacao (login) do que e pedido
    no cadastro de quem ainda nao tem ficha (signup).
    """
    __tablename__ = 'form_fields'
    __table_args__ = (
        db.UniqueConstraint('key', 'stage', name='uq_form_fields_key_stage'),
    )

    id       = db.Column(db.Integer, primary_key=True)
    key      = db.Column(db.String(40), nullable=False)
    stage    = db.Column(db.String(10), nullable=False, index=True)  # login | signup
    label    = db.Column(db.String(80), nullable=False)
    field_type = db.Column(db.String(20), nullable=False, default='text')

    enabled  = db.Column(db.Boolean, nullable=False, default=True)
    required = db.Column(db.Boolean, nullable=False, default=False)
    # Identifica o visitante recorrente. So um campo em 'login' pode te-lo.
    is_key   = db.Column(db.Boolean, nullable=False, default=False)

    order       = db.Column(db.Integer, nullable=False, default=0)
    placeholder = db.Column(db.String(120))
    help_text   = db.Column(db.String(200))
    options     = db.Column(db.Text)   # uma opcao por linha, para field_type=select

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    @property
    def coluna(self):
        """Coluna de Visitor onde o valor e gravado, ou None para extra_data."""
        return (CAMPOS_CONHECIDOS.get(self.key) or {}).get('coluna')

    @property
    def e_conhecido(self):
        return self.key in CAMPOS_CONHECIDOS

    @property
    def lista_opcoes(self):
        return [o.strip() for o in (self.options or '').splitlines() if o.strip()]

    def __repr__(self):
        return f"<FormField {self.stage}.{self.key}>"
