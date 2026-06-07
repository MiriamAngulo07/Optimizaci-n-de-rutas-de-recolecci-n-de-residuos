"""
Notificación EN TIEMPO REAL — SIROCA  (opción B)
app.py llama a revisar() cada vez que el camión reporta su posición GPS.

ETA por POSICIÓN EN RUTA:
- el progreso se toma del campo 'completada' (primera parada no completada = a donde va),
- el GPS vivo afina la distancia al siguiente punto,
- avisa solo si la parada del residente está ADELANTE y el ETA <= UMBRAL_MIN,
- una sola vez por día por residente.
Si no encuentra la ruta del camión, cae al método viejo (haversine).
"""
import os
import json
from datetime import date
from notificador import enviar
from residentes import cargar_residentes, guardar_residentes, haversine

UMBRAL_MIN = 8            # avisa cuando el ETA sea <= 8 min
UMBRAL_M = 300            # umbral del fallback (línea recta)
VELOCIDAD_M_MIN = 250     # ~15 km/h efectivos entre paradas
SEGUNDOS_POR_PARADA = 30  # tiempo aprox. en cada parada intermedia
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTAS_FILE = os.path.join(BASE_DIR, "navegacion_app", "rutas_flask.json")  # ← la viva

_cache = {"mtime": None, "rutas": {}}


def _cargar_rutas():
    """Devuelve {camion_id(str): [{lat, lon, completada}, ...]} en orden de visita."""
    try:
        mtime = os.path.getmtime(RUTAS_FILE)
    except OSError:
        return {}
    if _cache["mtime"] == mtime:
        return _cache["rutas"]

    with open(RUTAS_FILE, encoding="utf-8") as f:
        raw = json.load(f)

    rutas = {}
    for cid, info in raw.items():            # {"1": {...,"paradas":[...]}, "2": {...}}
        paradas = []
        for p in info.get("paradas", []):
            paradas.append({
                "lat": float(p["lat"]),
                "lon": float(p["lon"]),
                "completada": bool(p.get("completada", False)),
            })
        if paradas:
            rutas[str(cid)] = paradas

    _cache["mtime"] = mtime
    _cache["rutas"] = rutas
    return rutas


def _acumuladas(paradas):
    """Distancia acumulada (m) a lo largo de la ruta en cada parada."""
    acc = [0.0]
    for i in range(1, len(paradas)):
        a, b = paradas[i - 1], paradas[i]
        acc.append(acc[-1] + haversine(a["lat"], a["lon"], b["lat"], b["lon"]))
    return acc


def _indice_mas_cercano(paradas, lat, lon):
    best_i, best_d = 0, float("inf")
    for i, p in enumerate(paradas):
        d = haversine(lat, lon, p["lat"], p["lon"])
        if d < best_d:
            best_i, best_d = i, d
    return best_i, best_d


def revisar(camion_id, lat, lon):
    """Notifica a los residentes de ese camión según ETA por ruta."""
    rutas = _cargar_rutas()
    paradas = rutas.get(str(camion_id))
    if not paradas or len(paradas) < 2:
        return _revisar_haversine(camion_id, lat, lon)   # fallback seguro

    acc = _acumuladas(paradas)

    # progreso: primera parada NO completada = a donde va el camión
    idx_actual = next((i for i, p in enumerate(paradas) if not p["completada"]), len(paradas))
    if idx_actual >= len(paradas):
        return 0   # ruta terminada, nada que avisar

    sig = paradas[idx_actual]
    dist_a_siguiente = haversine(lat, lon, sig["lat"], sig["lon"])  # GPS vivo → siguiente parada

    data = cargar_residentes()
    hoy = date.today().isoformat()
    avisados = 0
    for r in data["residentes"]:
        if str(r.get("camion_id")) != str(camion_id):
            continue
        if r.get("notificado_proximidad") == hoy:
            continue
        res_i, _ = _indice_mas_cercano(paradas, r["lat"], r["lon"])
        if res_i < idx_actual:
            continue   # el camión ya pasó su parada
        restante_m = dist_a_siguiente + (acc[res_i] - acc[idx_actual])
        paradas_entre = res_i - idx_actual
        eta_min = restante_m / VELOCIDAD_M_MIN + (paradas_entre * SEGUNDOS_POR_PARADA) / 60
        eta_min = max(1, round(eta_min))
        if eta_min <= UMBRAL_MIN:
            res = enviar(
                r["chat_id"],
                f"🚛 <b>¡El camión está cerca!</b>\n\n"
                f"{r['nombre']}, llega en ~{eta_min} min. Saca tu basura ahora. 🗑️",
            )
            if res.get("ok"):
                r["notificado_proximidad"] = hoy
                avisados += 1
    if avisados:
        guardar_residentes(data)
    return avisados


def _revisar_haversine(camion_id, lat, lon):
    """Fallback: línea recta, si no hay ruta cargada para ese camión."""
    data = cargar_residentes()
    hoy = date.today().isoformat()
    avisados = 0
    for r in data["residentes"]:
        if str(r.get("camion_id")) != str(camion_id):
            continue
        if r.get("notificado_proximidad") == hoy:
            continue
        d = haversine(lat, lon, r["lat"], r["lon"])
        if d <= UMBRAL_M:
            mins = max(1, round(d / VELOCIDAD_M_MIN))
            res = enviar(
                r["chat_id"],
                f"🚛 <b>¡El camión está cerca!</b>\n\n"
                f"{r['nombre']}, llega en ~{mins} min. Saca tu basura ahora. 🗑️",
            )
            if res.get("ok"):
                r["notificado_proximidad"] = hoy
                avisados += 1
    if avisados:
        guardar_residentes(data)
    return avisados