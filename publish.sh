#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.production}"
COMPOSE_FILE="$ROOT_DIR/compose.production.yml"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

log() {
  printf '[tupa] %s\n' "$*"
}

fail() {
  printf '[tupa] erro: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "comando obrigatorio nao encontrado: $1"
}

escape_pem() {
  awk 'BEGIN { ORS="\\n" } { print }' "$1"
}

init_env() {
  require_command openssl

  if [[ -f "$ENV_FILE" ]]; then
    fail "$ENV_FILE ja existe; remova-o explicitamente para gerar novos segredos"
  fi

  local temp_dir service_token admin_password private_key public_key
  temp_dir="$(mktemp -d)"
  trap 'rm -rf "$temp_dir"' RETURN

  service_token="$(openssl rand -hex 32)"
  admin_password="$(openssl rand -base64 24 | tr -d '\n')"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
    -out "$temp_dir/private.pem" >/dev/null 2>&1
  openssl pkey -in "$temp_dir/private.pem" -pubout \
    -out "$temp_dir/public.pem" >/dev/null 2>&1
  private_key="$(escape_pem "$temp_dir/private.pem")"
  public_key="$(escape_pem "$temp_dir/public.pem")"

  umask 077
  {
    printf 'APP_NAME=Tupã\n'
    printf 'ENVIRONMENT=production\n'
    printf 'DATABASE_URL=CHANGE_ME_CLOUD_POSTGRESQL_URL\n'
    printf 'SERVICE_TOKEN=%s\n' "$service_token"
    printf 'ADMIN_USERNAME=admin\n'
    printf 'ADMIN_PASSWORD=%s\n' "$admin_password"
    printf 'JWT_PRIVATE_KEY=%s\n' "$private_key"
    printf 'JWT_PUBLIC_KEY=%s\n' "$public_key"
    printf 'JWT_KEY_ID=tupa-production-1\n'
    printf 'JWT_ISSUER=tupa\n'
    printf 'ACCESS_TOKEN_MINUTES=15\n'
    printf 'REFRESH_TOKEN_DAYS=7\n'
    printf 'LOGIN_RATE_LIMIT=10\n'
    printf 'LOGIN_RATE_WINDOW_SECONDS=60\n'
    printf 'TUPA_PORT=8000\n'
  } >"$ENV_FILE"

  log "arquivo criado com permissao restrita: $ENV_FILE"
  log "configure DATABASE_URL com a URL do PostgreSQL em nuvem antes de publicar"
}

validate_env() {
  [[ -f "$ENV_FILE" ]] || fail "$ENV_FILE nao existe; execute ./publish.sh init"
  if grep -Eq '(^|=)CHANGE_ME' "$ENV_FILE"; then
    fail "$ENV_FILE ainda possui valores CHANGE_ME"
  fi

  local required
  for required in DATABASE_URL SERVICE_TOKEN JWT_PRIVATE_KEY JWT_PUBLIC_KEY; do
    grep -q "^${required}=." "$ENV_FILE" || fail "variavel ausente: $required"
  done
  if grep -q '^ADMIN_PASSWORD=.' "$ENV_FILE" &&
    ! grep -q '^ADMIN_USERNAME=.' "$ENV_FILE"; then
    fail "ADMIN_USERNAME e obrigatorio quando ADMIN_PASSWORD estiver configurada"
  fi
  grep -q '^ENVIRONMENT=production$' "$ENV_FILE" ||
    fail "ENVIRONMENT deve ser production"
  if grep -Eq '^DATABASE_URL=.*@(db|localhost|127\.0\.0\.1)(:|/)' "$ENV_FILE"; then
    fail "DATABASE_URL deve apontar para um PostgreSQL em nuvem, nao para o Compose local"
  fi
  grep -q '^JWT_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----' "$ENV_FILE" ||
    fail "JWT_PRIVATE_KEY nao contem uma chave PEM valida"
  grep -q '^JWT_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----' "$ENV_FILE" ||
    fail "JWT_PUBLIC_KEY nao contem uma chave PEM valida"
}

publish() {
  require_command docker
  validate_env

  log "validando configuracao"
  "${COMPOSE[@]}" config --quiet

  log "construindo imagem"
  "${COMPOSE[@]}" build api

  log "testando conexao e aplicando migrations no PostgreSQL em nuvem"
  "${COMPOSE[@]}" run --rm api alembic upgrade head

  log "publicando API"
  "${COMPOSE[@]}" up -d api

  log "aguardando health check"
  local attempt status
  for attempt in {1..30}; do
    status="$("${COMPOSE[@]}" ps --format json api 2>/dev/null || true)"
    if grep -q '"Health":"healthy"' <<<"$status"; then
      log "publicacao concluida"
      "${COMPOSE[@]}" ps
      return
    fi
    sleep 2
  done

  "${COMPOSE[@]}" logs --tail=100 api
  fail "API nao ficou saudavel no tempo esperado"
}

usage() {
  cat <<'EOF'
Uso: ./publish.sh [comando]

  init      gera .env.production com segredos e chaves RS256
  publish   build, migrations e publicacao dos servicos (padrao)
  tokens    gera tokens ausentes e salva em .product-service-tokens
  status    mostra o estado dos servicos
  logs      acompanha os logs da API
  stop      para a API sem alterar o banco em nuvem
EOF
}

command="${1:-publish}"
case "$command" in
  init)
    init_env
    ;;
  publish)
    publish
    ;;
  tokens)
    require_command docker
    validate_env
    token_file="$ROOT_DIR/.product-service-tokens"
    [[ ! -f "$token_file" ]] ||
      fail "$token_file ja existe; mova ou remova o arquivo antes de gerar novamente"
    umask 077
    "${COMPOSE[@]}" run --rm api python -m scripts.issue_product_tokens >"$token_file"
    if [[ ! -s "$token_file" ]]; then
      rm "$token_file"
      log "todos os produtos ja possuem token"
    else
      log "tokens gerados e salvos com permissao restrita: $token_file"
    fi
    ;;
  status)
    validate_env
    "${COMPOSE[@]}" ps
    ;;
  logs)
    validate_env
    "${COMPOSE[@]}" logs -f api
    ;;
  stop)
    validate_env
    "${COMPOSE[@]}" down
    ;;
  help | -h | --help)
    usage
    ;;
  *)
    usage
    fail "comando desconhecido: $command"
    ;;
esac
