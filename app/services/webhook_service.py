"""
Webhook pós-autorização.

Dispara um HTTP POST (background thread) para a URL configurada em
  SiteConfig.get('webhook_url')

Payload JSON (compatível com UniFi, OPNsense e integrações genéricas):
  {
    "event":        "guest_authorized",
    "session_id":   <int>,
    "visitor_id":   <int>,
    "visitor_name": <str>,
    "visitor_email": <str>,
    "client_mac":   <str>,
    "client_ip":    <str>,
    "ap_mac":       <str>,
    "ssid":         <str>,
    "device_type":  <str>,
    "os_hint":      <str>,
    "authorized_at": <ISO-8601>,
    "secret":       <str>   # HMAC-SHA256 hex do payload sem este campo
  }

Configuração via SiteConfig (admin → Integrações):
  webhook_url     – URL destino (ex: https://n8n.empresa.com/webhook/captiveportal)
  webhook_secret  – segredo HMAC para o receptor validar a origem
  webhook_enabled – 'true' | 'false'
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
from datetime import timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.portal_session import PortalSession
    from app.models.visitor import Visitor

logger = logging.getLogger(__name__)


def _send(url: str, payload: dict, secret: str) -> None:
    """Executa o POST em background thread. Não propaga exceções."""
    try:
        import urllib.request
        body = json.dumps(payload, default=str).encode()
        # HMAC-SHA256
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": f"sha256={sig}",
                "X-Webhook-Event": "guest_authorized",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            logger.info("[webhook] POST %s → %s", url, resp.status)
    except Exception as exc:
        logger.warning("[webhook] falha ao enviar para %s: %s", url, exc)


def fire_authorized(session: "PortalSession", visitor: "Visitor") -> None:
    """
    Lê a configuração do banco e, se habilitado, dispara o webhook
    em uma thread separada para não bloquear a resposta HTTP.
    """
    try:
        from app.models.site_config import SiteConfig
        if SiteConfig.get("webhook_enabled", "false").lower() != "true":
            return
        url = SiteConfig.get("webhook_url", "").strip()
        if not url:
            return
        secret = SiteConfig.get("webhook_secret", "changeme")

        authorized_at = (
            session.authorized_at.replace(tzinfo=timezone.utc).isoformat()
            if session.authorized_at
            else None
        )
        payload = {
            "event":         "guest_authorized",
            "session_id":    session.id,
            "visitor_id":    visitor.id,
            "visitor_name":  visitor.full_name,
            "visitor_email": visitor.email,
            "client_mac":    session.client_mac,
            "client_ip":     session.client_ip,
            "ap_mac":        session.ap_mac,
            "ssid":          session.ssid,
            "device_type":   session.device_type,
            "os_hint":       session.os_hint,
            "authorized_at": authorized_at,
        }
        t = threading.Thread(target=_send, args=(url, payload, secret), daemon=True)
        t.start()
    except Exception as exc:
        logger.warning("[webhook] erro ao preparar disparo: %s", exc)
