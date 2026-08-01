# Captive Portal WiFi — UniFi

Portal de acesso WiFi para redes UniFi, desenvolvido com **Flask, MySQL, Alembic e Tailwind CSS**.

## Funcionalidades

- Redirecionamento do UniFi para o portal externo
- Identificacao de visitantes por **CPF + celular** (CPF validado pelo algoritmo)
- Cadastro de novos visitantes com **nome completo** e e-mail opcional
- **Multi-loja**: cada loja tem seu proprio controlador UDM Pro e credenciais UniFi
- Consentimento LGPD com versionamento de termos
- Autorizacao automatica via **API UniFi** (AUTHORIZE_GUEST_ACCESS)
- Painel administrativo com dashboard, cadastro de lojas e exportacao CSV
- Rate limiting, CSRF, login seguro com bcrypt
- Pronto para Docker + Nginx

## Estrutura

```
app/
  models/        # Visitor, PortalSession, Store, ConsentRecord, AdminUser
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

## Configuracao multi-loja (um UDM Pro por loja)

Cada loja e identificada por um **slug** na URL do portal. Como o Hotspot Manager
do UDM Pro tem um unico campo de "External Portal Server", e essa URL que diz ao
portal de qual loja veio o visitante — e portanto quais credenciais UniFi usar
para autorizar o acesso.

1. No painel admin, acesse **Lojas > Nova loja** e cadastre nome, slug,
   URL do controlador, API Key e Site ID daquela unidade.
2. No UniFi Network **daquela loja**:
   - Hotspot > **Captive Portal** > habilitar
   - Tipo de autenticacao: **External Portal Server**
   - URL do portal externo: `http://<seu-servidor>/guest/s/<slug-da-loja>/`
   - Gere a **API Key** em Settings > API > Add API Key e cadastre-a na loja
3. Use **Testar conexao** na tela de edicao da loja para validar as credenciais.

As variaveis `UNIFI_*` do `.env` sao usadas apenas para semear a loja `default`
na primeira migracao e como fallback caso a loja nao seja identificada.

## Rotas

| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/guest/s/<slug>/` | Entrada do portal da loja (redirect UniFi) |
| POST | `/guest/identify` | Identificacao por CPF + celular |
| GET/POST | `/guest/cadastro` | Formulario de cadastro |
| GET | `/admin/` | Dashboard |
| GET | `/admin/lojas` | Lista de lojas |
| GET/POST | `/admin/lojas/nova` | Cadastro de loja |
| GET/POST | `/admin/lojas/<id>/editar` | Edicao de loja |
| GET | `/admin/visitantes` | Lista de visitantes |
| GET | `/admin/visitantes/export` | Export CSV |
| GET | `/health` | Health check |

## Seguranca e LGPD

- Consentimento versionado com IP e user-agent
- Rate limiting por IP nas rotas criticas
- CSRF em todos os formularios
- Sessoes seguras (Secure + HttpOnly + SameSite em producao)
