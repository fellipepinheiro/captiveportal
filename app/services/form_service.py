"""Formulario do portal montado a partir da configuracao do admin.

O portal deixa de ter campos fixos: quais perguntas aparecem na
identificacao e no cadastro, quais sao obrigatorias e qual delas identifica
o visitante recorrente sao decisoes do administrador.

Tudo o que valida entrada do visitante passa por aqui, para que a tela e o
servidor nunca discordem sobre o que e exigido.
"""
import re
from datetime import date, datetime

from app.models import FormField
from app.models.form_field import CAMPOS_CONHECIDOS, CHAVES_POSSIVEIS
from app.services.validator import (
    validate_cpf, validate_phone, validate_email,
    normalize_cpf, normalize_phone,
)

#: Fallback usado enquanto a configuracao nao existir (instalacao nova antes
#: do seed, ou alguem apagando tudo pelo painel). Reproduz o comportamento
#: historico para o portal nunca ficar sem formulario.
PADRAO_LOGIN = [
    dict(key='cpf', label='CPF', field_type='cpf', required=True, is_key=True,
         order=10, placeholder='000.000.000-00', help_text=None, options=None),
    dict(key='mobile', label='Celular / WhatsApp', field_type='phone', required=True,
         is_key=False, order=20, placeholder='(47) 99999-9999', help_text=None, options=None),
]
PADRAO_SIGNUP = [
    dict(key='full_name', label='Nome completo', field_type='name', required=True,
         is_key=False, order=10, placeholder='Seu nome completo', help_text=None, options=None),
]


class _CampoPadrao:
    """Objeto com a mesma interface de FormField, para os fallbacks."""
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.enabled = True
        self.stage = kw.get('stage')

    @property
    def coluna(self):
        return (CAMPOS_CONHECIDOS.get(self.key) or {}).get('coluna')

    @property
    def e_conhecido(self):
        return self.key in CAMPOS_CONHECIDOS

    @property
    def lista_opcoes(self):
        return [o.strip() for o in (self.options or '').splitlines() if o.strip()]


def campos(stage: str) -> list:
    """Campos habilitados de uma etapa, na ordem definida pelo admin."""
    achados = (FormField.query
               .filter_by(stage=stage, enabled=True)
               .order_by(FormField.order, FormField.id).all())
    if achados:
        return achados
    padrao = PADRAO_LOGIN if stage == 'login' else PADRAO_SIGNUP
    return [_CampoPadrao(stage=stage, **d) for d in padrao]


def campo_chave():
    """Campo que identifica o visitante recorrente.

    Sem chave nao ha como reconhecer quem ja tem cadastro, entao ha dois
    niveis de seguranca: um campo de login marcado como chave; se nao
    houver, o primeiro campo de login que sirva como chave; e por fim o CPF.
    """
    for c in campos('login'):
        if getattr(c, 'is_key', False) and c.key in CHAVES_POSSIVEIS:
            return c
    for c in campos('login'):
        if c.key in CHAVES_POSSIVEIS:
            return c
    return _CampoPadrao(stage='login', **PADRAO_LOGIN[0])


# ── validacao por tipo ───────────────────────────────────────────────────

def _valida(campo, valor: str):
    """Retorna (valor_normalizado, erro). Valor vazio ja foi tratado antes."""
    tipo = campo.field_type

    if tipo == 'cpf':
        digitos = re.sub(r'\D', '', valor)
        if len(digitos) != 11:
            return None, f'{campo.label} deve ter 11 dígitos (faltam {11 - len(digitos)}).' \
                if len(digitos) < 11 else f'{campo.label} deve ter 11 dígitos.'
        if not validate_cpf(valor):
            return None, f'{campo.label} não confere. Verifique os dígitos.'
        return normalize_cpf(valor), None

    if tipo == 'phone':
        digitos = re.sub(r'\D', '', valor)
        if len(digitos) < 10:
            return None, f'{campo.label} incompleto. Informe DDD + número.'
        if len(digitos) > 11:
            return None, f'{campo.label} tem dígitos demais.'
        if not validate_phone(valor):
            return None, f'{campo.label} não parece um número válido. Confira o DDD.'
        return normalize_phone(valor), None

    if tipo == 'email':
        if '@' not in valor:
            return None, f'Falta o @ no {campo.label.lower()}.'
        if not validate_email(valor):
            return None, f'{campo.label} incompleto. Exemplo: nome@provedor.com'
        return valor.lower(), None

    if tipo == 'name':
        if len(valor.split()) < 2:
            return None, 'Informe nome e sobrenome.'
        return valor, None

    if tipo == 'date':
        try:
            d = date.fromisoformat(valor)
        except ValueError:
            return None, f'{campo.label} inválida.'
        if d > date.today():
            return None, f'{campo.label} não pode estar no futuro.'
        return d.isoformat(), None

    if tipo == 'number':
        try:
            return str(int(re.sub(r'\D', '', valor))), None
        except ValueError:
            return None, f'{campo.label} deve ser um número.'

    if tipo == 'zipcode':
        digitos = re.sub(r'\D', '', valor)
        if len(digitos) != 8:
            return None, f'{campo.label} deve ter 8 dígitos.'
        return digitos, None

    if tipo == 'select':
        opcoes = campo.lista_opcoes
        if opcoes and valor not in opcoes:
            return None, f'Escolha uma opção válida para {campo.label}.'
        return valor, None

    return valor[:200], None


def coletar(stage: str, form) -> tuple[dict, dict]:
    """Le e valida os campos da etapa.

    Retorna (valores_validados, erros_por_campo). Valida tudo antes de
    devolver, em vez de parar no primeiro problema: quem errou dois campos
    prefere ver os dois de uma vez a descobrir um por vez a cada tentativa.

    Os erros vem indexados pela chave do campo para que a tela consiga
    apontar exatamente onde esta o problema.
    """
    valores, erros = {}, {}
    for campo in campos(stage):
        bruto = (form.get(campo.key) or '').strip()

        if not bruto:
            if campo.required:
                erros[campo.key] = f'{campo.label} é obrigatório.'
            continue

        valor, erro = _valida(campo, bruto)
        if erro:
            erros[campo.key] = erro
        else:
            valores[campo.key] = valor
    return valores, erros


def aplicar(visitor, valores: dict, stage: str):
    """Grava os valores no visitante: coluna propria ou extra_data."""
    extras = visitor.extras
    for campo in campos(stage):
        if campo.key not in valores:
            continue
        coluna = campo.coluna
        if coluna:
            setattr(visitor, coluna, valores[campo.key])
        else:
            extras[campo.key] = valores[campo.key]
    visitor.set_extras(extras)


def rotulos_extras() -> dict:
    """Rotulo de cada campo sem coluna propria, para exibir no painel."""
    return {
        c.key: c.label
        for c in FormField.query.filter_by(enabled=True).all()
        if not c.coluna
    }
