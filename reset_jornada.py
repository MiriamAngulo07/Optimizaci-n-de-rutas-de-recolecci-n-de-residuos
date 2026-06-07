import json, os
RUTAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "navegacion_app", "rutas_flask.json")
data = json.load(open(RUTAS, encoding="utf-8"))
for cid in data:
    for p in data[cid]["paradas"]:
        p["completada"] = False
json.dump(data, open(RUTAS, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("Jornada reseteada: todas las paradas sin completar.")