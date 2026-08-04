# 🌐 Captive Portal — Wi-Fi Visitantes

Portal de autenticação de visitantes para redes Wi-Fi corporativas, integrado ao **UniFi Network** via API oficial. Construído com Flask, MySQL e implantado via Docker Compose com HTTPS automático (Let's Encrypt).

---

## ✨ Funcionalidades

### Portal público (visitante)
- Tela de identificação por **CPF** e **celular** (formato BR)
- Cadastro com **nome completo** e **e-mail opcional**
- Validação de CPF (dígitos verificadores); busca aceita com ou sem máscara
- Aceite de **Termos de Uso** e **Política de Privacidade** com registro de versão (LGPD)
- Opt-in de comunicações de marketing
- Redirecionamento automático pós-autorização

### Painel administrativo (`/admin`)
- **Dashboard** com KPIs em tempo real (total de visitantes, sessões, taxa de autorização)
- **Relatórios** com gráficos interativos por período, distribuição por dispositivo e sistema operacional
- **Gestão de visitantes** — busca por nome/CPF/celular/e-mail, bloqueio/desbloqueio com motivo, exclusão de cadastro (LGPD) e exportação CSV
- **Extrato por visitante** — conexões e desconexões em um período, com duração e exportação CSV
- **Lojas** — cadastro de várias controladoras UDM Pro, uma por loja, com teste de conexão
- **Gestão de usuários** admin — criar, ativar/desativar, redefinir senha, excluir
- **Perfil pessoal** — nome, e-mail, telefone, foto de perfil (compressão automática via Pillow) e **alteração de senha com verificação da senha atual**
- **Aparência do portal** — título, mensagem de boas-vindas, cores e logo customizáveis
- **Integrações** — Webhook com HMAC-SHA256 e botão de teste
  (as credenciais do UniFi ficam em **Lojas**, por controlador)

### Integração UniFi
- Autorização via API REST de integração, autenticando por header `X-API-KEY`
- Credenciais **por loja**: cada UDM Pro tem URL, API Key, Site ID e duração próprios
- Encerramento automático das sessões de quem sai do Wi-Fi (serviço `session_sync`)
- Descarte automático das sessões que abriram o portal e nunca se autenticaram
  (serviço `cleanup`: varre a cada `CLEANUP_INTERVAL` segundos e remove o que
  está parado há mais de `PENDING_SESSION_TTL` minutos)
- Suporte a certificados auto-assinados (por loja)

### Segurança
- Senhas com hash **bcrypt**
- Proteção **CSRF** em todos os formulários (Flask-WTF)
- **Rate limiting** por rota (Flask-Limiter)
- Webhook assinado com **HMAC-SHA256** (`X-Webhook-Signature`)
- Criptografia de dados PII com **Fernet** (opcional)
- Registro de **audit log** e **consent events** (LGPD)

---

## 🏗️ Arquitetura

```
captiveportal/
├── app/
│   ├── __init__.py           # Application factory (Flask)
│   ├── config.py             # Configurações por ambiente
│   ├── extensions.py         # db, limiter, csrf, login_manager
│   ├── security.py           # Headers de segurança HTTP
│   ├── cli.py                # Comandos Flask CLI
│   ├── models/
│   │   ├── visitor.py            # Visitante (dados + CPF + consentimento)
│   │   ├── portal_session.py     # Sessão de acesso (MAC, AP, SSID, device)
│   │   ├── admin_user.py         # Usuário admin (bcrypt, avatar, perfil)
│   │   ├── site_config.py        # Configurações dinâmicas (key-value)
│   │   ├── audit_log.py          # Log de auditoria
│   │   ├── consent_event.py      # Eventos de consentimento LGPD
│   │   ├── consent_record.py     # Registro de aceite de termos
│   │   └── data_subject_request.py  # Solicitações de titulares LGPD
│   ├── routes/
│   │   ├── portal.py         # Fluxo público: entry → identify → register → success
│   │   ├── admin.py          # Painel admin completo
│   │   └── health.py         # GET /health (healthcheck Docker)
│   ├── services/
│   │   ├── portal_service.py    # Lógica de sessão e autorização
│   │   ├── unifi_api.py         # Cliente UniFi REST API
│   │   ├── webhook_service.py   # Envio de webhooks com assinatura HMAC
│   │   └── validator.py         # Validação CPF e telefone BR
│   ├── templates/
│   │   ├── portal/           # start.html, register.html, success.html
│   │   └── admin/            # base, dashboard, visitors, reports, users, profile, etc.
│   └── static/
│       └── uploads/          # Logo e avatars (volume Docker persistente)
├── migrations/               # Alembic migrations
├── nginx/
│   └── conf.d/
│       ├── portal.conf               # Config Nginx (HTTP → HTTPS + proxy)
│       └── portal.conf.template      # Template com variável ${DOMAIN}
├── scripts/
│   └── migrate.sh            # Script executado pelo container migrator
├── Dockerfile
├── docker-compose.yml
├── wsgi.py
├── requirements.txt
└── .env.example
```

---

## 🐳 Stack & Dependências

| Componente | Tecnologia |
|---|---|
| Framework web | Flask 3.x + Gunicorn |
| Banco de dados | MySQL 8.4 |
| ORM / Migrations | SQLAlchemy 2.x + Alembic (Flask-Migrate) |
| Autenticação | Flask-Login + bcrypt |
| Segurança | Flask-WTF (CSRF) + Flask-Limiter |
| Processamento de imagens | Pillow (resize/compress avatars 256×256 JPEG) |
| Validação | phonenumbers (telefone BR), validação CPF nativa |
| HTTP client | requests (UniFi API + webhooks) |
| Proxy reverso | Nginx 1.27-alpine |
| TLS | Let's Encrypt via Certbot (renovação automática a cada 12h) |
| Contêineres | Docker Compose |

---

## 🚀 Deploy

### Pré-requisitos

- Docker e Docker Compose instalados no servidor
- Domínio apontando para o IP do servidor (necessário para HTTPS)
- Portas **80** e **443** abertas no firewall

### 1. Clonar o repositório

```bash
git clone https://github.com/fellipepinheiro/captiveportal.git
cd captiveportal
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Edite o `.env` com seus valores reais:

```env
# Flask
SECRET_KEY=uma-chave-longa-e-aleatoria-aqui

# Domínio e certificado TLS
DOMAIN=portal.suaempresa.com.br
CERTBOT_EMAIL=admin@suaempresa.com.br

# Banco de dados
MYSQL_ROOT_PASSWORD=senharoot
MYSQL_DATABASE=unifi_portal
MYSQL_USER=portal
MYSQL_PASSWORD=senhadb
DATABASE_URL=mysql+pymysql://portal:senhadb@db:3306/unifi_portal

# UniFi (pode ser configurado também via painel admin)
UNIFI_BASE_URL=https://192.168.1.1/proxy/network/integration
UNIFI_API_KEY=sua-api-key
UNIFI_SITE_ID=default
UNIFI_SESSION_MINUTES=480
UNIFI_VERIFY_SSL=false

# LGPD
TERMS_VERSION=1.0
PRIVACY_POLICY_URL=/politica-de-privacidade
```

### 3. Subir os containers

```bash
docker compose up -d
```

A sequência de inicialização é gerenciada pelo Docker Compose:

1. **db** — MySQL 8.4 sobe e aguarda healthcheck
2. **migrator** — executa `alembic upgrade head` e cria o usuário admin padrão
3. **web** — Gunicorn inicia na porta interna 5000
4. **nginx** — proxy reverso nas portas 80 e 443
5. **certbot-init** — emite o certificado TLS (roda uma vez)
6. **certbot-renew** — loop de renovação automática a cada 12 horas

### 4. Primeiro acesso

```
https://seu-dominio.com.br/admin
```

| Campo | Valor padrão |
|---|---|
| Usuário | `admin` |
| Senha | `admin123!@#` |

> ⚠️ **Troque a senha imediatamente** em `Perfil → Alterar senha`.

---

## 🔄 Fluxo do visitante

```
[UniFi AP]
    │  redireciona para /guest/s/default/?id={MAC}&ap={AP}&ssid={SSID}&url={URL}
    ▼
[Entry] ── visitante informa CPF + celular + aceite de termos
    │
    ├── já cadastrado? ──► [Autorização UniFi] ──► [Sucesso + redirect]
    │
    └── novo visitante? ──► [Cadastro: nome + e-mail opcional] ──► [Autorização UniFi] ──► [Sucesso + redirect]
```

O portal cria um `PortalSession` com o MAC do cliente ao receber o redirect do AP. Após identificação/cadastro, a função `authorize_visitor` chama a UniFi API para liberar o acesso na rede.

---

## 🔗 Integração UniFi

A integração usa a **API REST moderna do UniFi Network** (não a API legada via cookie de sessão).

Configure em `Admin → Lojas`, uma entrada por controlador:

| Campo | Descrição |
|---|---|
| Slug | Identifica a loja na URL do portal (`/guest/s/<slug>/`) |
| URL do controlador | Inclui o caminho da API: `https://192.168.1.1/proxy/network/integration` |
| API Key | Gerada em **Settings → Control Plane → Integrations** no UniFi |
| Site ID | O **UUID** do site, não o nome. O botão *Testar conexão* mostra qual usar |
| Duração da sessão | Minutos de acesso; em branco usa o padrão global |

No Hotspot Manager de cada UDM Pro, aponte o *External Portal Server* para o
IP do servidor. O controlador monta `http://<ip>/guest/s/<site>/` sozinho —
por isso o portal precisa responder na **porta 80**.

Use **Testar conexão** para validar a chave e descobrir o Site ID.

---

## 🪝 Webhook

O portal envia um `POST` JSON para o endpoint configurado a cada nova autorização.

**Payload de exemplo:**

```json
{
  "event": "visitor_authorized",
  "visitor": {
    "id": 42,
    "full_name": "João Silva",
    "email": "joao@email.com",
    "mobile": "+5547999991234"
  },
  "session": {
    "mac": "aa:bb:cc:dd:ee:ff",
    "ssid": "WiFi-Empresa",
    "authorized_at": "2026-05-27T10:00:00Z"
  }
}
```

**Validar a assinatura** no header `X-Webhook-Signature`:

```python
import hmac, hashlib

def verify(payload: bytes, secret: str, signature: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

---

## 🔒 LGPD

O sistema registra automaticamente todos os eventos exigidos pela legislação brasileira:

| Modelo | Conteúdo |
|---|---|
| `ConsentRecord` | Aceite dos termos por visitante (versão, IP, timestamp) |
| `ConsentEvent` | Histórico de opt-in/opt-out de marketing |
| `DataSubjectRequest` | Solicitações de acesso, exclusão e portabilidade de dados |
| `AuditLog` | Ações administrativas rastreadas |

---

## 🛠️ Comandos úteis

```bash
# Acompanhar logs em tempo real
docker compose logs -f web

# Criar novo usuário admin via CLI
docker compose exec web flask create-admin --username operador --password SenhaSegura123!

# Executar migrations manualmente
docker compose exec web flask db upgrade

# Acessar o banco de dados
docker compose exec db mysql -u portal -p unifi_portal

# Rebuild após alterações de código
docker compose up -d --build web

# Verificar status dos containers
docker compose ps

# Ver quem está com acesso liberado no controlador
docker compose exec web flask guests

# Derrubar o acesso para voltar a ver a tela de login num aparelho de teste
docker compose exec web flask guests --all
docker compose exec web flask guests --revoke 4a:cb:7c:0b:13:3d
```

> **Por que `flask guests` existe:** o UniFi não manda ao portal quem já tem
> autorização válida, e ela dura horas. Esquecer a rede no celular não resolve —
> o aparelho costuma manter o mesmo MAC privado por SSID e reencontra a própria
> autorização. Derrubar o acesso é o que faz a tela de login aparecer de novo.

---

## 📁 Volumes persistentes

| Volume | Conteúdo |
|---|---|
| `db_data` | Dados MySQL |
| `uploads_data` | Logo customizada e avatars dos usuários admin |

---

## 🌐 Mapa de rotas

| Método | URL | Descrição |
|---|---|---|
| GET | `/guest/s/default/` | Entrada do portal (redirect do AP UniFi) |
| GET | `/guest/` | Alias da entrada |
| POST | `/guest/identify` | Identificação do visitante |
| GET/POST | `/guest/cadastro` | Cadastro de novo visitante |
| GET | `/admin` | Dashboard |
| GET/POST | `/admin/login` | Login admin |
| GET | `/admin/visitantes` | Lista de visitantes |
| GET | `/admin/relatorios` | Relatórios e gráficos |
| GET | `/admin/usuarios` | Gestão de usuários admin |
| GET | `/admin/aparencia` | Customização do portal |
| GET | `/admin/integracoes` | UniFi e Webhook |
| GET | `/admin/perfil` | Perfil do usuário logado |
| GET | `/health` | Healthcheck Docker |
