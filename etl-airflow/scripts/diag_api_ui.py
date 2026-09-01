"""Diagnóstico 3: flujo real como navegador — login por formulario + API /dags."""
import http.cookiejar
import json
import urllib.parse
import urllib.request

BASE = "http://localhost:8080"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

# 1) POST /login como navegador (csrf + username/password)
csfr_req = urllib.request.Request(BASE + "/login/")
with opener.open(csfr_req, timeout=15) as resp:
    html = resp.read().decode()
import re
m = re.search(r'name="csrf_token" value="([^"]+)"', html)
csrf = m.group(1) if m else ""
print("csrf_token obtenido:", bool(csrf))

form = urllib.parse.urlencode({
    "username": "globtrade_admin",
    "password": "12345678",
    "remember": "y",
}).encode()
login_req = urllib.request.Request(BASE + "/login/", data=form,
                                   headers={"Content-Type": "application/x-www-form-urlencoded"})
resp = opener.open(login_req, timeout=15)
print("POST /login ->", resp.geturl(), resp.status)

# 2) GET /api/v1/dags con la sesión
resp = opener.open(BASE + "/api/v1/dags?limit=20", timeout=15)
data = json.loads(resp.read().decode())
dags = data.get("dags", [])
print(f"DAGs según la API con sesión: {len(dags)}")
for d in dags:
    print(f"  - {d['dag_id']}  paused={d['is_paused']}")
if not dags:
    print("RESPUESTA CRUDA:", json.dumps(data)[:400])