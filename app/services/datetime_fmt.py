"""Exibicao de datas no fuso local.

Todos os timestamps sao gravados em UTC (datetime.now(timezone.utc)), que e
o correto. Estes helpers convertem para o fuso configurado em TIMEZONE na
hora de exibir — sem eles o painel mostra o horario UTC.
"""
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TZ = "America/Sao_Paulo"


def get_tz() -> ZoneInfo:
    name = os.getenv("TIMEZONE", DEFAULT_TZ) or DEFAULT_TZ
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def to_local(dt: datetime | None) -> datetime | None:
    """Converte um datetime UTC para o fuso local.

    Valores vindos do MySQL chegam naive (o driver nao devolve tzinfo);
    nesse caso assume-se UTC, que e como foram gravados.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(get_tz())


def fmt_datetime(dt: datetime | None, fmt: str = "%d/%m/%Y %H:%M") -> str:
    local = to_local(dt)
    return local.strftime(fmt) if local else "—"


def fmt_short(dt: datetime | None) -> str:
    """Formato compacto usado nas listagens: 03/08 10:11."""
    return fmt_datetime(dt, "%d/%m %H:%M")


def fmt_date(dt: datetime | None) -> str:
    return fmt_datetime(dt, "%d/%m/%Y")
