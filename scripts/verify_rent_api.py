import json
import urllib.request

# login
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/auth/login",
    data=json.dumps({"email": "admin@globmarket.com", "password": "12345678"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=15) as r:
    token = json.load(r)["access_token"]

url = "http://127.0.0.1:8000/api/rentabilidad?dimension=producto&page=1&page_size=50"
req2 = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
with urllib.request.urlopen(req2, timeout=30) as r:
    data = json.load(r)

helado = [x for x in data["data"] if "Helado" in x.get("dimension", "")]
print("helado en API:", helado)
print("summary:", data.get("summary"))
