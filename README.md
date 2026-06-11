# Tupã

Stub da plataforma central de servicos, implementando o Sprint 0 definido no
documento de requisitos.

## Executar localmente

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

A documentacao OpenAPI fica em `http://localhost:8000/docs`.

## Endpoints

- `POST /tenants`: cria e persiste um tenant.
- `GET /tenants/{id}/plan`: retorna o plano free stub com limites ilimitados.
- `GET /health`: health check da API.

## Testes

```bash
.venv/bin/pytest
```
