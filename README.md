# Tupã

Plataforma central de servicos. Inclui Auth Service e Subscription Service sem
Stripe, conforme a Sprint 2.

## Executar localmente

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

A documentacao OpenAPI fica em `http://localhost:8000/docs`.

A interface administrativa fica em `http://localhost:8000/admin/products` e
`http://localhost:8000/admin/plans`.
Ela usa autenticacao Basic com `ADMIN_USERNAME` e `ADMIN_PASSWORD`. Quando
`ADMIN_PASSWORD` nao estiver configurada, o `SERVICE_TOKEN` e usado como senha.

Cada produto possui seu proprio service token, gerado ou rotacionado na pagina
de produtos. O token e exibido uma unica vez; apenas seu hash e a dica dos
ultimos caracteres ficam armazenados. Produtos devem envia-lo no header
`X-Service-Token`. A rotacao invalida imediatamente o token anterior.

Para emitir tokens ausentes em lote depois da migration:

```bash
./publish.sh tokens
```

Os valores sao salvos em `.product-service-tokens` com permissao restrita e o
arquivo e ignorado pelo Git.

## Endpoints

- `POST /tenants`: cria e persiste um tenant.
- `GET /tenants/{id}/plan`: retorna assinatura, plano e limites reais.
- `GET /plans?product_id=x`: lista planos publicos ativos.
- `POST /tenants/{id}/upgrade`: upgrade manual imediato.
- `POST /tenants/{id}/downgrade`: agenda downgrade para o fim do periodo.
- `GET /tenants/{id}/events`: audit log append-only da assinatura.
- `POST /auth/token`: autentica e emite access/refresh tokens RS256.
- `POST /auth/refresh`: rotaciona um refresh token.
- `POST /auth/logout`: revoga globalmente os refresh tokens do usuario.
- `GET /.well-known/jwks`: publica a chave para validacao local.
- `POST /auth/users`: provisiona usuario, protegido por `X-Service-Token`.
- `POST /auth/migrate`: importa usuario legado com hash bcrypt.
- `GET /health`: health check da API.

Em producao, configure `SERVICE_TOKEN`, `JWT_PRIVATE_KEY` e `JWT_PUBLIC_KEY`.
As chaves PEM podem ser informadas com quebras de linha escapadas (`\n`).

`SERVICE_TOKEN` permanece como segredo interno/fallback da senha admin; ele nao
autentica mais chamadas de produtos. Os endpoints internos, mudancas de plano e
audit log exigem o `X-Service-Token` individual do produto. Os
planos Moara (`free`, `starter`, `pro`, `pro-plus`) sao criados pela migration.
Precos pagos permanecem em `0` ate serem definidos comercialmente.

## Testes

```bash
.venv/bin/pytest
```

## Publicacao

O deploy de producao usa Docker Compose apenas para a API e conecta em um
PostgreSQL gerenciado em nuvem.

```bash
chmod +x publish.sh
./publish.sh init
# Edite DATABASE_URL em .env.production com a URL fornecida pelo provedor.
./publish.sh publish
```

O primeiro comando cria `.env.production` com service token, senha admin e
chaves RS256. Configure `DATABASE_URL` com a URL do PostgreSQL em nuvem. URLs
iniciadas por `postgres://` ou `postgresql://` e `sslmode=require` sao
normalizadas automaticamente para o driver asyncpg.

O arquivo e ignorado pelo Git e deve ser armazenado em um cofre de segredos.
O publish testa a conexao aplicando as migrations antes de atualizar a API.
Para acompanhar a publicacao:

```bash
./publish.sh status
./publish.sh logs
```
