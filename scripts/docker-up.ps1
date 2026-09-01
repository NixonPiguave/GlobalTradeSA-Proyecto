# Levanta el stack Docker completo (apps + ClickHouse + Airflow).
# Detén antes python run.py local — DuckDB no admite dos procesos en el mismo archivo.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$lock = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($lock) {
    Write-Host "Puerto 8000 en uso. Detén 'python run.py' u otro proceso antes de usar Docker." -ForegroundColor Yellow
    Write-Host "  Get-Process python | Stop-Process -Force" -ForegroundColor DarkGray
    exit 1
}

Write-Host "Arrancando stack: docker compose -f docker-compose.full.yml up --build -d" -ForegroundColor Cyan
docker compose -f docker-compose.full.yml up --build -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Servicios:" -ForegroundColor Green
Write-Host "  Admin ERP   -> http://localhost:8000"
Write-Host "  Portal B2B  -> http://localhost:8001"
Write-Host "  Airflow     -> http://localhost:8080  (globtrade_admin / 12345678)"
Write-Host "  ClickHouse  -> http://localhost:8123"
Write-Host ""
Write-Host "Primera vez: el volumen duckdb_data se inicializa solo (init_sistema)."
Write-Host "Para copiar tu BD local al volumen (con servicios parados):"
Write-Host "  docker compose -f docker-compose.full.yml stop globaltrade-apps"
Write-Host "  docker run --rm -v globaltradesa_proyecto_duckdb_data:/data -v `"${Root}/db:/seed:ro`" alpine cp /seed/globtrade.duckdb /data/globtrade.duckdb"
Write-Host "  docker compose -f docker-compose.full.yml up -d globaltrade-apps"
