# UniFi Captive Portal com Flask

Captive portal externo integrado ao UniFi Network usando Flask, SQLAlchemy, Alembic, MySQL, Tailwind CSS, Docker Compose e Let's Encrypt.

## Fluxo

1. UniFi redireciona o cliente para `/guest/s/default/?ap=...&id=...&ssid=...&url=...`.
2. O portal pede e-mail e celular.
3. Se o visitante já existir por e-mail ou celular, autoriza o acesso no UniFi.
4. Se não existir, pede nome e CPF, cadastra e depois autoriza.

## Instalação (desenvolvimento)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
flask --app wsgi.py run --debug
```

## Deploy com Docker Compose

```bash
# 1. Configurar variáveis
cp .env.example .env
# editar .env com suas credenciais reais

# 2. Subir serviços
docker compose up -d db migrator web nginx certbot-renew

# 3. Emitir certificado Let's Encrypt
chmod +x scripts/init-letsencrypt.sh
./scripts/init-letsencrypt.sh

# 4. Descomentar bloco HTTPS em nginx/conf.d/portal.conf
# 5. Recarregar Nginx
docker compose restart nginx
```

## Configuração UniFi

- Habilite `Hotspot > Captive Portal` no SSID guest.
- Use `External Portal Server` apontando para a URL pública do Flask.
- Garanta que o host do portal esteja acessível pela rede guest.
- Configure `UNIFI_BASE_URL`, `UNIFI_API_KEY` e `UNIFI_SITE_ID` no `.env`.

## Renovação SSL

A renovação do certificado é **totalmente automática**:
- `certbot-renew`: verifica a cada 12h e renova quando faltam < 30 dias.
- `--deploy-hook`: envia sinal HUP ao Nginx apenas quando o certificado é efetivamente renovado.

## Próximos passos recomendados

- Validar CPF, e-mail e telefone com feedback visual.
- Adicionar tela de termos/LGPD.
- Criar painel administrativo para consultas e exportações.
- Implementar testes unitários e tratamento de exceções da API UniFi.
- Substituir Tailwind Play CDN por build local/CLI em produção.
