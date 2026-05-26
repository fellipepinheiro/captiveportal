"""
Security helpers — registra headers HTTP de segurança e
configura proteções globais da aplicação Flask.
"""
from flask import Flask, request


CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' cdn.tailwindcss.com cdn.jsdelivr.net unpkg.com; "
    "style-src 'self' 'unsafe-inline' fonts.googleapis.com cdn.tailwindcss.com cdn.jsdelivr.net; "
    "font-src 'self' fonts.gstatic.com data:; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
)


def register_security_headers(app: Flask) -> None:
    """Adiciona headers de segurança a todas as respostas."""

    @app.after_request
    def _add_security_headers(response):
        # Evita clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Evita MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Força HTTPS nos browsers (apenas em produção)
        if not app.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains"
            )

        # Política de conteúdo
        response.headers["Content-Security-Policy"] = CSP_POLICY

        # Não expõe o referrer completo ao sair do site
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Desativa FLoC / Topics API
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )

        # Remove header que revela a stack
        response.headers.pop("Server", None)
        response.headers.pop("X-Powered-By", None)

        return response
