# Captive Portal WiFi — UniFi

Portal de acesso WiFi para redes UniFi, desenvolvido com **Flask, MySQL, Alembic e Tailwind CSS**.

## Funcionalidades

- Redirecionamento do UniFi para o portal externo
- Identificacao de visitantes por **e-mail + celular**
- Cadastro de novos visitantes com **nome + CPF** (validado pelo algoritmo)
- Consentimento LGPD com versionamento de termos
- CPF armazenado apenas como **hash SHA-256** (privacidade by design)
- Autorizacao automatica via **API UniFi** (AUTHORIZE_GUEST_ACCESS)
- Painel administrativo com dashboard e exportacao CSV
- Rate limiting, CSRF, login seguro com bcrypt
- Pronto para Docker + Nginx

## Estrutura

```
app/
  models/        # Visitor, PortalSession, ConsentRecord, AdminUser
  services/      # unifi_api.py, portal_service.py, validator.py
  routes/        # portal.py, admin.py, health.py
  templates/     # portal/ e admin/ (Jinja2 + Tailwind CDN)
migrations/      # Alembic
```

## Inicio rapido

```bash
# 1. Copie o .env
cp .env.example .env
# edite DATABASE_URL, SECRET_KEY, UNIFI_BASE_URL, UNIFI_API_KEY

# 2. Docker Compose
docker compose up -d

# 3. Migrate
docker compose exec app flask db upgrade

# 4. Criar admin
docker compose exec app flask create-admin admin@empresa.com
```

## Configuracao UniFi

No UniFi Network:
1. Hotspot > **Captive Portal** > habilitar
2. Tipo de autenticacao: **External Portal Server**
3. URL do portal externo: `http://<seu-servidor>/guest/s/default/`
4. Gere uma **API Key** em Settings > API > Add API Key
5. Configure `UNIFI_API_KEY` no `.env`

## Rotas

| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/guest/s/default/` | Entrada do portal (redirect UniFi) |
| POST | `/guest/check` | Verifica visitante existente |
| GET/POST | `/guest/cadastro` | Formulario de cadastro |
| GET | `/admin/` | Dashboard |
| GET | `/admin/visitantes` | Lista de visitantes |
| GET | `/admin/visitantes/export` | Export CSV |
| GET | `/health` | Health check |

## Seguranca e LGPD

- CPF nunca e armazenado em texto claro — apenas SHA-256
- Consentimento versionado com IP e user-agent
- Rate limiting por IP nas rotas criticas
- CSRF em todos os formularios
- Sessoes seguras (Secure + HttpOnly + SameSite em producao)
