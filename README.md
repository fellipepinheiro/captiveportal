# 🌐 Captive Portal — Wi-Fi Visitantes

Portal de autenticação de visitantes para redes Wi-Fi corporativas, integrado ao **UniFi Network** via API oficial. Construído com Flask, MySQL e implantado via Docker Compose com HTTPS automático (Let's Encrypt).

---

## ✨ Funcionalidades

### Portal público (visitante)
- **Campos definidos pelo administrador** — quais dados pedir no login e no
  cadastro é configurável, com lista pronta (CPF, celular, e-mail, nome, CEP,
  data de nascimento…) e campos livres. O admin escolhe qual campo é a
  **chave** que identifica o visitante recorrente
- Validação por tipo: CPF com dígitos verificadores, celular no formato BR,
  e-mail; busca aceita com ou sem máscara
- **Erros no campo que os causou**, sem apagar o que já foi preenchido
- Aceite de **Termos de Uso** com registro de versão (LGPD)
- Opt-in de comunicações de marketing
- Coleta de **localização aproximada** mediante consentimento (junto do aceite
  dos termos), para saber de onde vêm os clientes
- Tela de sucesso autônoma (HTML e CSS embutidos, sem dependência externa) com
  **contador que devolve o visitante à página que ele tentava abrir**, ou ao
  destino configurado na loja quando não há página de origem

### Painel administrativo (`/admin`)
- **Dashboard** com KPIs em tempo real (total de visitantes, sessões, taxa de
  autorização) e botão para derrubar a sessão de cada dispositivo
- **Relatórios de BI** com filtros por loja, período e cliente: volume de
  acessos, visitantes novos × recorrentes, pico por dia e hora, tempo médio de
  conexão, download/upload por período, distribuição por dispositivo e sistema
  operacional, ranking de pontos de acesso e **origem geográfica** dos
  visitantes (distância até a loja). Exportação CSV
- **Relatório de autenticação e saúde** — taxa de sucesso, motivos de falha
  (CPF inválido, termos recusados, falha no controlador…) e tentativas negadas
- **Inventário de pontos de acesso** — quais APs atenderam visitantes e quanto
- **Auditoria e consentimento (LGPD)** — trilha de ações administrativas,
  histórico de consentimento por versão dos termos e tentativas de login
- **Gestão de visitantes** — busca, bloqueio/desbloqueio com motivo (derruba as
  conexões ativas junto), exclusão de cadastro (LGPD) e exportação CSV
- **Extrato por visitante** — conexões e desconexões em um período, com duração
  e exportação CSV
- **Lojas** — cadastro de várias controladoras UDM Pro, uma por loja, com teste
  de conexão, endereço/coordenadas, conexões ativas no controlador e botões
  para derrubar uma ou **todas** as conexões
- **Campos do formulário** — define o que o portal pede no login e no cadastro
- **Gestão de usuários** admin — criar, ativar/desativar, redefinir senha, excluir
- **Perfil pessoal** — nome, e-mail, telefone, foto de perfil (compressão automática via Pillow) e **alteração de senha com verificação da senha atual**
- **Aparência do portal** — título, mensagem de boas-vindas, cores e logo customizáveis
- **Integrações** — Webhook com HMAC-SHA256 e botão de teste
  (as credenciais do UniFi ficam em **Lojas**, por controlador)

### WhatsApp (`/admin/whatsapp`)
Tela para cadastrar o provedor e a mensagem de boas-vindas, sem mexer em
webhook. Dois provedores:

- **WhatsGW** — gateway brasileiro, texto livre, mais rápido de começar
- **WhatsApp Cloud API** (Meta) — oficial; o primeiro contato acontece fora da
  janela de 24 h, então **exige template aprovado**, e a tela pede o nome dele

Editor com variáveis clicáveis (`{primeiro_nome}`, `{loja}`, `{rede}`), prévia
ao vivo no estilo da conversa e botão que **envia um teste real** para o número
que você digitar. A chave fica guardada no banco e nunca é reexibida na tela.

Há um interruptor **"só para quem aceitou receber comunicações"**, ligado por
padrão: saudação institucional é uma coisa, oferta comercial é outra (LGPD
Art. 7º).

### IP real do visitante
O endereço que o Flask enxerga é o do último salto até o container. Com o
portal publicado por Docker, a NAT troca a origem e **todo visitante aparece
como o gateway** — `192.168.65.1` no Docker Desktop. Atrás do nginx o
`X-Forwarded-For` resolve (já configurado, via `ProxyFix`), mas publicando a
porta direto não há proxy nenhum.

Por isso o IP vem do **controlador**, que conhece o endereço real na VLAN de
visitantes: é gravado na autorização (o cliente já é consultado ali) e
mantido pelo serviço `session_sync`, que também corrige sessões antigas.

`TRUST_PROXY_HOPS` controla a leitura do `X-Forwarded-For`: `1` (padrão) é o
correto atrás do nginx; use `0` quando o portal for publicado direto, senão
qualquer cliente pode mandar o header e escolher que IP fica registrado.

### Diagnóstico (`/admin/diagnostico`)
Mostra se o portal está falando com os controladores **de verdade** ou apenas
simulando, loja por loja: motivo da simulação, se o controlador responde, URL,
Site ID e se há API Key. Tem botão para verificar na hora.

Quando alguma loja ativa está em simulação, um **selo aparece no topo de toda
tela do painel** — vermelho quando é involuntária (loja sem endereço de
controlador, caso em que o visitante vê "acesso liberado" e segue sem
internet) e amarelo quando foi ligada de propósito. O selo consulta só a
configuração, sem chamar a rede, para não deixar o painel lento.

### Gatilho de primeira visita
Quando alguém entra na rede pela **primeira vez**, o sistema registra o evento
`PRIMEIRA_VISITA` na auditoria e dispara um webhook próprio (`first_visit`),
separado do `guest_authorized`. É a base para acolher quem chega: no varejo,
a primeira oferta; na igreja, o aviso de visitante novo para quem faz
integração.

O payload leva `visitor_mobile` — o canal, tipicamente WhatsApp — e
`marketing_optin`, que diz se houve consentimento para comunicação
promocional. **Quem recebe precisa respeitar esse campo:** mensagem de
boas-vindas é uma coisa, oferta é outra.

A detecção usa o histórico de sessões autorizadas, não o contador
`visit_count` — o contador serve para relatório, mas não é confiável como
gatilho: ele avança em `touch()` e antes disso já vinha inflado pelo cadastro.

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
- Proteção **CSRF** em todos os formulários do painel (Flask-WTF). As rotas do
  portal são isentas por necessidade: quem chega ainda não tem sessão e o
  fluxo é iniciado por um redirect do controlador
- **Rate limiting** por rota (Flask-Limiter) — login 10/min, derrubar todas
  6/min, cadastro 5/min
- **Tentativas de login malsucedidas registradas na auditoria**, com usuário
  tentado e IP (a senha nunca é gravada)
- Headers de segurança em todas as respostas: CSP, `X-Frame-Options: DENY`,
  `nosniff`, HSTS (fora de debug), `Referrer-Policy`, `Permissions-Policy`
- Cookie de sessão `HttpOnly` + `SameSite=Lax`, expira em 1 h
- Upload restrito a imagens (`png/jpg/jpeg/webp`), nome saneado com
  `secure_filename`, limite de 20 MB
- Webhook assinado com **HMAC-SHA256** (`X-Webhook-Signature`)
- Registro de **audit log** e **consent events** (LGPD)
- Consultas via ORM — não há SQL montado por concatenação
- Templates com autoescape do Jinja e **sem nenhum uso de `|safe`**

> Pendências conhecidas estão em [Segurança — pontos em aberto](#-segurança--pontos-em-aberto).

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
│   │   ├── visitor.py            # Visitante (dados + consentimento)
│   │   ├── portal_session.py     # Sessão de acesso (MAC, AP, SSID, device, GPS)
│   │   ├── store.py              # Loja + credenciais do seu UDM Pro
│   │   ├── form_field.py         # Campos configuráveis do login/cadastro
│   │   ├── admin_user.py         # Usuário admin (bcrypt, avatar, perfil)
│   │   ├── site_config.py        # Configurações dinâmicas (key-value)
│   │   ├── audit_log.py          # Log de auditoria
│   │   ├── consent_event.py      # Eventos de consentimento LGPD
│   │   ├── consent_record.py     # ⚠️ órfão — não registrado nem usado
│   │   └── data_subject_request.py  # ⚠️ órfão — não registrado nem usado
│   ├── routes/
│   │   ├── portal.py         # Fluxo público: entry → identify → register → success
│   │   ├── admin.py          # Painel admin completo
│   │   └── health.py         # GET /health (healthcheck Docker)
│   ├── services/
│   │   ├── portal_service.py    # Lógica de sessão, autorização e revogação
│   │   ├── unifi_api.py         # Cliente UniFi REST API (por loja)
│   │   ├── session_sync.py      # Encerra sessões de quem saiu + coleta tráfego
│   │   ├── analytics.py         # Agregações dos relatórios de BI
│   │   ├── form_service.py      # Campos dinâmicos: validação e coleta
│   │   ├── datetime_fmt.py      # Conversão UTC → fuso local (TIMEZONE)
│   │   ├── webhook_service.py   # Envio de webhooks com assinatura HMAC
│   │   └── validator.py         # Validação CPF e telefone BR
│   ├── templates/
│   │   ├── portal/           # start, register, success, _campo (campo dinâmico)
│   │   └── admin/            # base, dashboard, visitors, reports, stores, form_fields, etc.
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

### O que está implementado

| Recurso | Onde |
|---|---|
| **Consentimento versionado** — aceite obrigatório a cada acesso, com a versão dos termos gravada no visitante (`terms_version`, `terms_accepted_at`) | `portal_service.record_consent` |
| **Histórico de consentimento** append-only, com IP, user-agent, canal e opt-in de marketing | `ConsentEvent` (tabela `consent_events`) |
| **Reaceite quando os termos mudam** — quem se cadastrou numa versão antiga tem o consentimento atualizado ao aceitar a nova | `portal_service.refresh_consent` |
| **Direito de acesso e portabilidade** (Art. 18, II e V) — exportação CSV por visitante e da base inteira | `/admin/visitantes/<id>/exportar`, `/admin/visitantes/export` |
| **Direito de exclusão** (Art. 18, VI) — apaga o cadastro e os consentimentos; os registros de conexão são **desvinculados**, não apagados | `/admin/visitantes/<id>/excluir` |
| **Retenção de logs de conexão por 1 ano**, como exige o Marco Civil (Lei 12.965/2014, Art. 15) | `flask cleanup-sessions --expired-ttl 365` |
| **Descarte de sessões abandonadas** que nunca se autenticaram | serviço `cleanup` |
| **Minimização** — o administrador escolhe quais campos coletar; nada é pedido por padrão além do necessário | Campos do formulário |
| **Transparência sobre a localização** — o item 3 dos termos explica que a localização aproximada é registrada e para quê | `portal/start.html` |
| **Trilha de auditoria** de ações administrativas e de tentativas de acesso | `AuditLog` (tabela `audit_logs`) |

**Exclusão e Marco Civil convivem assim:** apagar o visitante remove nome, CPF,
telefone, e-mail e consentimentos. As linhas de `portal_sessions` continuam,
mas com `visitor_id` nulo — viram registro de conexão anônimo, que é o que a
lei manda guardar. O registro da própria exclusão na auditoria guarda **apenas
o id**, nunca o nome: manter o nome ali esvaziaria o direito exercido.

### Pontos em aberto

- ⚠️ **A Política de Privacidade não existe.** `PRIVACY_POLICY_URL` aponta para
  `/politica-de-privacidade`, que responde **404** — o portal exibe um link
  quebrado no momento do consentimento. É a pendência mais relevante aqui:
  consentimento informado pressupõe que o titular consiga ler a política.
  Publique o documento e ajuste a variável, ou aponte para uma URL externa.
- ⚠️ **Sem tela de solicitações do titular.** Os pedidos de acesso, correção ou
  exclusão chegam por fora do sistema e são atendidos manualmente pelo painel.
  Existem os arquivos `models/consent_record.py` e
  `models/data_subject_request.py`, mas **não estão em uso** — são restos de
  uma implementação que não foi concluída e não devem ser tomados como
  controles ativos.
- **Dados pessoais em texto puro no banco.** CPF, telefone e e-mail não são
  cifrados. `FERNET_KEY` existe na configuração mas **não é usada em lugar
  nenhum**. A LGPD não exige criptografia, mas ela é a salvaguarda esperada
  para CPF em caso de vazamento (Art. 46).
- **Sem anonimização automática por prazo.** Passado 1 ano os registros de
  conexão são purgados, mas o cadastro do visitante permanece indefinidamente
  enquanto ninguém o excluir.

---

## 🛡️ Segurança — pontos em aberto

Levantados em auditoria do código. Nenhum é exploração conhecida; são
decisões e lacunas que valem revisão antes de expor o painel fora da LAN.

| Ponto | Situação | Observação |
|---|---|---|
| **Cookie de sessão sem `Secure`** | `SESSION_COOKIE_SECURE = False`, inclusive em produção | É deliberado: o portal cativo é servido em HTTP puro pelo IP interno, e `Secure=True` bloquearia o cookie e quebraria o fluxo. O efeito colateral é que o **mesmo cookie do painel** trafega sem TLS. Corrigir de verdade exige separar o cookie do admin do cookie do portal |
| **API Key do UniFi em texto puro** | Gravada assim na tabela `stores` | Quem lê o banco autoriza visitantes e derruba conexões no controlador. `FERNET_KEY` já existe na configuração, sem uso |
| **CSP com `unsafe-inline`** | `script-src 'self' 'unsafe-inline' cdn.jsdelivr.net` | Enfraquece a defesa contra XSS. O risco hoje é baixo (autoescape ativo, nenhum `\|safe`), mas some a rede de proteção. O `cdn.jsdelivr.net` serve o ECharts dos relatórios — o painel precisa de internet |
| **CSRF desativado em desenvolvimento** | `DevelopmentConfig.WTF_CSRF_ENABLED = False` | Só afeta `FLASK_ENV=development`. Atenção ao rodar assim numa máquina com a porta 80 publicada na LAN, como no cenário de teste com o UDM Pro |
| **Sem bloqueio de conta** | Apenas rate limit de 10/min no login | Suficiente contra força bruta simples; não impede tentativa lenta e distribuída. As tentativas agora ficam registradas na auditoria |
| **Sem política de senha** | `create-admin` e a troca de senha aceitam qualquer string | Nenhuma exigência de tamanho ou complexidade |

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
| GET | `/guest/s/<slug>/` | Entrada do portal — o slug identifica a loja/controlador |
| GET | `/guest/` | Alias da entrada (cai na loja `default`) |
| POST | `/guest/identify` | Identificação do visitante |
| GET/POST | `/guest/cadastro` | Cadastro de novo visitante |
| POST | `/guest/localizacao` | Recebe a localização aproximada (após o aceite) |
| GET | `/admin` | Dashboard |
| GET/POST | `/admin/login` | Login admin |
| GET | `/admin/visitantes` | Lista de visitantes |
| GET | `/admin/visitantes/<id>` | Extrato de conexões do visitante |
| GET | `/admin/relatorios` | Relatórios de BI com filtros |
| GET | `/admin/auditoria` | Auditoria e consentimento (LGPD) |
| GET | `/admin/lojas` | Lojas e controladoras UDM Pro |
| POST | `/admin/lojas/<id>/derrubar` | Derruba uma conexão pelo MAC |
| POST | `/admin/lojas/<id>/derrubar-todos` | Derruba todas as conexões da loja |
| GET | `/admin/formulario` | Campos do login e do cadastro |
| GET | `/admin/usuarios` | Gestão de usuários admin |
| GET | `/admin/aparencia` | Customização do portal |
| GET | `/admin/integracoes` | Webhook |
| GET | `/admin/perfil` | Perfil do usuário logado |
| GET | `/health` | Healthcheck Docker |

> O mapa acima lista as telas principais. `flask routes` mostra as **61 rotas**
> registradas, incluindo as ações POST de cada tela.
