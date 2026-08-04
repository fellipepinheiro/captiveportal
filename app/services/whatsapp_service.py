"""Envio de WhatsApp para os gatilhos do portal.

Dois provedores, escolhidos no painel (Admin -> WhatsApp):

* **WhatsGW** — gateway brasileiro. Envia texto livre, sem template
  aprovado. Mais simples de comecar.
* **WhatsApp Cloud API** (Meta) — oficial. Fora da janela de 24 h so
  aceita **template aprovado**, e o primeiro contato com um visitante e
  sempre fora dessa janela. Por isso, neste provedor, o gatilho de
  primeira visita usa template — texto livre seria recusado pela Meta.

Tudo e configurado por SiteConfig, entao nao ha segredo em arquivo. O
envio roda em thread separada: mensageria nao pode atrasar nem derrubar a
liberacao do visitante.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import urllib.request

logger = logging.getLogger(__name__)

PROVEDORES = ("whatsgw", "cloud")

#: Placeholders aceitos no texto da mensagem.
VARIAVEIS = {
    "nome": "Nome completo do visitante",
    "primeiro_nome": "Só o primeiro nome",
    "loja": "Nome da loja / unidade",
    "rede": "Nome da rede Wi-Fi (SSID)",
}


def _cfg(chave: str, padrao: str = "") -> str:
    from app.models.site_config import SiteConfig
    return (SiteConfig.get(chave, padrao) or "").strip()


def habilitado() -> bool:
    return _cfg("whatsapp_enabled", "false").lower() == "true"


def so_com_optin() -> bool:
    """Restringe o envio a quem marcou o aceite de comunicacoes."""
    return _cfg("whatsapp_somente_optin", "true").lower() == "true"


def normalizar_telefone(numero: str, ddi_padrao: str = "55") -> str | None:
    """Deixa so digitos e garante o DDI.

    Os telefones chegam do portal como '(11) 98888-7777'. Sem DDI o
    provedor nao entrega, e um numero curto demais e erro de digitacao —
    melhor nao enviar do que mandar para desconhecido.
    """
    digitos = re.sub(r"\D", "", numero or "")
    if not digitos:
        return None
    if len(digitos) <= 11:            # numero nacional sem DDI
        digitos = ddi_padrao + digitos
    return digitos if 12 <= len(digitos) <= 15 else None


def montar_mensagem(texto: str, contexto: dict) -> str:
    """Troca os placeholders pelo conteudo real, sem quebrar se faltar um."""
    saida = texto or ""
    nome = (contexto.get("nome") or "").strip()
    valores = {
        "nome": nome,
        "primeiro_nome": nome.split(" ")[0] if nome else "",
        "loja": contexto.get("loja") or "",
        "rede": contexto.get("rede") or "",
    }
    for chave, valor in valores.items():
        saida = saida.replace("{" + chave + "}", valor)
    return saida.strip()


# ──────────────────────────────────────────────────────────────────────
# Provedores
# ──────────────────────────────────────────────────────────────────────

def _post(url: str, corpo: bytes, headers: dict, timeout: int = 12) -> tuple[bool, str]:
    req = urllib.request.Request(url, data=corpo, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        detalhe = ""
        try:
            detalhe = exc.read().decode()[:300]
        except Exception:
            pass
        return False, f"HTTP {exc.code} {detalhe}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _enviar_whatsgw(destino: str, texto: str) -> tuple[bool, str]:
    apikey = _cfg("whatsapp_whatsgw_apikey")
    remetente = normalizar_telefone(_cfg("whatsapp_whatsgw_remetente"))
    if not apikey:
        return False, "API Key do WhatsGW não configurada."
    if not remetente:
        return False, "Número remetente do WhatsGW não configurado."

    url = _cfg("whatsapp_whatsgw_url") or "https://app.whatsgw.com.br/api/WhatsGw/Send"
    payload = {
        "apikey": apikey,
        "phone_number": remetente,
        "contact_phone_number": destino,
        "message_type": "text",
        "message_body": texto,
    }
    return _post(url, json.dumps(payload).encode(),
                 {"Content-Type": "application/json"})


def _enviar_cloud(destino: str, texto: str, usar_template: bool) -> tuple[bool, str]:
    token = _cfg("whatsapp_cloud_token")
    phone_id = _cfg("whatsapp_cloud_phone_id")
    if not token or not phone_id:
        return False, "Token ou ID do número da Cloud API não configurados."

    versao = _cfg("whatsapp_cloud_versao") or "v20.0"
    url = f"https://graph.facebook.com/{versao}/{phone_id}/messages"

    if usar_template:
        # Primeiro contato: fora da janela de 24 h a Meta so aceita
        # template aprovado. Texto livre voltaria com erro 131047.
        template = _cfg("whatsapp_cloud_template")
        if not template:
            return False, "Nome do template aprovado não configurado."
        corpo = {
            "messaging_product": "whatsapp",
            "to": destino,
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": _cfg("whatsapp_cloud_idioma") or "pt_BR"},
                "components": [{
                    "type": "body",
                    "parameters": [{"type": "text", "text": texto}],
                }],
            },
        }
    else:
        corpo = {"messaging_product": "whatsapp", "to": destino,
                 "type": "text", "text": {"body": texto}}

    return _post(url, json.dumps(corpo).encode(), {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    })


# ──────────────────────────────────────────────────────────────────────
# API do modulo
# ──────────────────────────────────────────────────────────────────────

def enviar(telefone: str, texto: str, primeiro_contato: bool = True) -> tuple[bool, str]:
    """Envia uma mensagem. Sincrono — use `enviar_em_background` no fluxo."""
    destino = normalizar_telefone(telefone)
    if not destino:
        return False, f"Telefone inválido: {telefone!r}"
    if not texto:
        return False, "Mensagem vazia."

    provedor = _cfg("whatsapp_provider", "whatsgw").lower()
    if provedor == "cloud":
        return _enviar_cloud(destino, texto, usar_template=primeiro_contato)
    if provedor == "whatsgw":
        return _enviar_whatsgw(destino, texto)
    return False, f"Provedor desconhecido: {provedor!r}"


def enviar_em_background(telefone: str, texto: str, primeiro_contato: bool = True) -> None:
    def _worker():
        ok, detalhe = enviar(telefone, texto, primeiro_contato)
        if ok:
            logger.info("[whatsapp] enviado para %s — %s", telefone, detalhe)
        else:
            logger.warning("[whatsapp] falha ao enviar para %s — %s", telefone, detalhe)

    threading.Thread(target=_worker, daemon=True).start()


def notificar_primeira_visita(visitor, session, store=None) -> None:
    """Dispara a mensagem de boas-vindas do gatilho de primeira visita.

    Nunca propaga excecao nem bloqueia: o visitante ja esta liberado, e
    falha de mensageria nao pode virar problema de acesso.
    """
    try:
        if not habilitado() or _cfg("whatsapp_gatilho_primeira_visita", "true").lower() != "true":
            return
        if so_com_optin() and not visitor.marketing_optin:
            logger.info("[whatsapp] visitante %s sem opt-in — nada enviado", visitor.id)
            return

        texto = montar_mensagem(_cfg("whatsapp_mensagem_boas_vindas"), {
            "nome": visitor.full_name,
            "loja": store.name if store else "",
            "rede": session.ssid if session else "",
        })
        if not texto:
            logger.info("[whatsapp] mensagem de boas-vindas em branco — nada enviado")
            return
        if not visitor.mobile:
            logger.info("[whatsapp] visitante %s sem telefone — nada enviado", visitor.id)
            return

        enviar_em_background(visitor.mobile, texto, primeiro_contato=True)
    except Exception:
        logger.warning("[whatsapp] erro ao preparar boas-vindas", exc_info=True)
