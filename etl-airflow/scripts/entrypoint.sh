#!/usr/bin/env bash
# entrypoint.sh — inicia Airflow y crea el usuario admin en el primer arranque.
set -e

export AIRFLOW__CORE__AIRFLOW_HOME="${AIRFLOW_HOME:-/opt/airflow}"

rol="$1"

if [ "$rol" = "webserver" ]; then
  airflow db migrate
  if ! airflow users list | grep -q globtrade_admin; then
    airflow users create \
      --username globtrade_admin \
      --firstname "Admin" \
      --lastname "GlobalTrade" \
      --role Admin \
      --email admin@globtrade.sa \
      --password "12345678"
  fi
fi

exec airflow "$rol"