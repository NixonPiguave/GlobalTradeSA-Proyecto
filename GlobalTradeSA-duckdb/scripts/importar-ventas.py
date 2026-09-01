import pandas as pd
import requests
import time

POCKETBASE_URL = "http://127.0.0.1:8090"
EMAIL = "npiguavem@uteq.edu.ec"
PASSWORD = "12345678"  # pon tu contraseña

# Crear sesión persistente (reutiliza conexiones)
session = requests.Session()

# Autenticarse
auth = session.post(f"{POCKETBASE_URL}/api/collections/_superusers/auth-with-password", json={
    "identity": EMAIL,
    "password": PASSWORD
})
token = auth.json()["token"]
session.headers.update({"Authorization": f"Bearer {token}"})
print("✅ Autenticado")

# Leer CSV
df = pd.read_csv("ventas.csv")
df.columns = [c.lower().replace(" ", "_") for c in df.columns]
total = len(df)

errores = 0
for i, row in df.iterrows():
    data = {
        "region": str(row["region"]),
        "country": str(row["country"]),
        "item_type": str(row["item_type"]),
        "sales_channel": str(row["sales_channel"]),
        "order_priority": str(row["order_priority"]),
        "order_date": str(row["order_date"]),
        "order_id": int(row["order_id"]),
        "ship_date": str(row["ship_date"]),
        "units_sold": int(row["units_sold"]),
        "unit_price": float(row["unit_price"]),
        "unit_cost": float(row["unit_cost"]),
        "total_revenue": float(row["total_revenue"]),
        "total_cost": float(row["total_cost"]),
        "total_profit": float(row["total_profit"]),
    }
    try:
        session.post(f"{POCKETBASE_URL}/api/collections/ventas/records", json=data)
    except Exception as e:
        errores += 1
        time.sleep(2)  # espera 2 segundos si hay error y continúa
        continue

    if i % 500 == 0:
        print(f"Progreso: {i}/{total} | Errores: {errores}")

print(f"✅ Listo. Total errores: {errores}")