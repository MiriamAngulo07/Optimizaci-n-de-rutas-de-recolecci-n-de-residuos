"""
Gestión de residentes — SIROCA
Guarda a los vecinos y los asocia al camión cuya ruta pasa más cerca de su casa.
"""
import os
import json
from math import radians, sin, cos, asin, sqrt

# Raíz del proyecto (sube desde bot/). Así el bot y la app de Flask
# leen/escriben SIEMPRE los mismos archivos, sin importar desde dónde se ejecuten.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESIDENTES_FILE = os.path.join(BASE_DIR, "residentes.json")
RUTAS_FILE = os.path.join(BASE_DIR, "navegacion_app", "rutas_flask.json")  # ← la viva


def haversine(lat1, lon1, lat2, lon2):
    """Distancia en METROS entre dos puntos (lat/lon en grados)."""
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def cargar_residentes():
    if not os.path.exists(RESIDENTES_FILE):
        return {"residentes": []}
    with open(RESIDENTES_FILE, encoding="utf-8") as f:
        return json.load(f)


def guardar_residentes(data):
    with open(RESIDENTES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _camion_mas_cercano(lat, lon):
    """camion_id (str) cuya parada esté más cerca del residente; None si no hay rutas."""
    if not os.path.exists(RUTAS_FILE):
        return None
    with open(RUTAS_FILE, encoding="utf-8") as f:
        rutas = json.load(f)
    mejor_cid, mejor_d = None, float("inf")
    for cid, info in rutas.items():
        for p in info.get("paradas", []):
            d = haversine(lat, lon, p["lat"], p["lon"])
            if d < mejor_d:
                mejor_d, mejor_cid = d, str(cid)
    return mejor_cid


def registrar_residente(chat_id, nombre, lat, lon):
    """Crea o actualiza un residente (por chat_id) y lo asigna al camión más cercano."""
    data = cargar_residentes()
    camion_id = _camion_mas_cercano(lat, lon)

    for r in data["residentes"]:               # ¿ya existe? → actualizar
        if str(r["chat_id"]) == str(chat_id):
            r.update({"nombre": nombre, "lat": lat, "lon": lon, "camion_id": camion_id})
            guardar_residentes(data)
            return r

    nuevo = {
        "chat_id": chat_id,
        "nombre": nombre,
        "lat": lat,
        "lon": lon,
        "camion_id": camion_id,
        "notificado_previa": None,
        "notificado_proximidad": None,
    }
    data["residentes"].append(nuevo)
    guardar_residentes(data)
    return nuevo