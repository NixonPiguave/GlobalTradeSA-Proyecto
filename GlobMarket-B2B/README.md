# GlobMarket B2B

API y frontend del marketplace B2B entre empresas.

## Arranque

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn gmbackend.main:app --reload
```

## Docker (solo este sistema)

```powershell
cd GlobMarket-B2B
docker compose up --build
```

Abre: http://localhost:8001

Cada sistema tiene su propio volumen DuckDB (ver `../README-DOCKER.md`). Puedes correr Sistema 1 y Sistema 2 en paralelo sin bloqueos.

## Datos y panel admin

- Dataset compartido: [`../data/`](../data/)
- Panel administrativo: [`../GlobalTradeSA-duckdb/`](../GlobalTradeSA-duckdb/)
