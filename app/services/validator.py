import re
import phonenumbers


def validate_cpf(cpf: str) -> bool:
    """Valida CPF pelo algoritmo de digito verificador."""
    digits = re.sub(r"\D", "", cpf)
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for i in range(2):
        total = sum(int(digits[j]) * (10 + i - j) for j in range(9 + i))
        expected = (total * 10 % 11) % 10
        if int(digits[9 + i]) != expected:
            return False
    return True


def validate_phone(phone: str, region: str = "BR") -> bool:
    try:
        parsed = phonenumbers.parse(phone, region)
        return phonenumbers.is_valid_number(parsed)
    except phonenumbers.NumberParseException:
        digits = re.sub(r"\D", "", phone)
        return 10 <= len(digits) <= 11


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def normalize_cpf(cpf: str) -> str:
    """Somente dígitos — a coluna visitors.cpf é VARCHAR(11)."""
    return re.sub(r"\D", "", cpf)


def format_cpf(cpf: str) -> str:
    """39053344705 → 390.533.447-05 (para exibição)."""
    d = normalize_cpf(cpf or "")
    if len(d) != 11:
        return cpf or ""
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def format_phone(phone: str) -> str:
    """47988776655 → (47) 98877-6655 (para exibição)."""
    d = normalize_phone(phone or "")
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return phone or ""


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def validate_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))
