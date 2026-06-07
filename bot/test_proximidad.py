"""
Simulador de proximidad — SIROCA  (NO envía nada real a Telegram)
Recorre la ruta del camión indicado parada por parada y muestra qué avisos saldrían.
Uso:  python test_proximidad.py        (camión 1)
      python test_proximidad.py 2
"""
import sys, json
import proximidad

CAMION = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].isdigit() else "1"

raw = json.load(open(proximidad.RUTAS_FILE, encoding="utf-8"))
if CAMION not in raw:
    print(f"No existe el camión {CAMION} en {proximidad.RUTAS_FILE}"); sys.exit(1)

ruta = [{"lat": float(p["lat"]), "lon": float(p["lon"]), "completada": False}
        for p in raw[CAMION]["paradas"]]
N = len(ruta)

# vecinos de prueba colocados en paradas reales de la ruta
indices = [i for i in (5, 20, 50, N - 3) if 0 <= i < N]
residentes = [{"chat_id": 1000 + i, "nombre": f"Vecino_parada_{i}",
               "lat": ruta[i]["lat"], "lon": ruta[i]["lon"], "camion_id": CAMION,
               "notificado_previa": None, "notificado_proximidad": None} for i in indices]
fake = {"residentes": residentes}

estado = {"paso": 0}
def fake_enviar(chat_id, mensaje, **kw):
    nom = next((r["nombre"] for r in residentes if r["chat_id"] == chat_id), chat_id)
    print(f"   📨 parada {estado['paso']:>3} -> {nom}: {mensaje.splitlines()[-1].strip()}")
    return {"ok": True}

# stubs: ni Telegram ni residentes.json real
proximidad.enviar = fake_enviar
proximidad.cargar_residentes = lambda: fake
proximidad.guardar_residentes = lambda d: None
proximidad._cargar_rutas = lambda: {CAMION: ruta}

print(f"Camión {CAMION}: {N} paradas. Vecinos de prueba en {indices}\n")
for k in range(N):
    for j in range(N):
        ruta[j]["completada"] = (j < k)          # ya pasó las anteriores, va hacia k
    estado["paso"] = k
    proximidad.revisar(CAMION, ruta[k]["lat"], ruta[k]["lon"])
print("\n✅ Simulación terminada. Cada vecino debió recibir UN solo aviso.")