#!/bin/sh
set -e

DB_PATH="${DUCKDB_PATH:-/app/db/globtrade.duckdb}"
DB_DIR="$(dirname "${DB_PATH}")"
mkdir -p "${DB_DIR}" /app/shared/storage

# Bind mounts desde Windows suelen llegar sin permiso de escritura para el contenedor.
chmod -R a+rwx "${DB_DIR}" 2>/dev/null || true
if [ -f "${DB_PATH}" ]; then
  chmod a+rw "${DB_PATH}" 2>/dev/null || true
fi
if [ ! -f "${DB_PATH}" ] && [ -f "/app/db-seed/globtrade.duckdb" ]; then
  echo "[unified] Copiando BD inicial al volumen Docker..."
  cp /app/db-seed/globtrade.duckdb "${DB_PATH}"
  chmod a+rw "${DB_PATH}" 2>/dev/null || true
fi

export PYTHONPATH="/app:/app/apps/admin:/app/apps/portal"
export DUCKDB_PATH="${DB_PATH}"

echo "[unified] Inicializando sistema (idempotente)..."
python /app/shared/database/init_sistema.py || {
  echo "[unified] AVISO: init_sistema falló; se intenta arrancar con la BD existente."
}

echo "[unified] Arrancando admin:8000 y portal:8001..."
exec "$@"
