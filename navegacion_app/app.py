"""
Sistema de Navegación para Conductores
Recolección de Desechos Sólidos — Puerto Caimito, La Chorrera
Larana, Inc.
"""
import sys
import json
import os
import subprocess
import tempfile
import traceback
import threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot"))
from flask import Flask, render_template, jsonify, request
from notificador import iniciar_sesion, enviar_ruta_asignada, enviar_resumen_diario
from scheduler_previa import notificar_previa
from proximidad import revisar

app = Flask(__name__)

DEPOSITO = {
    "lat": 8.842671764429827,
    "lon": -79.76393584997263,
    "nombre": "Relleno Sanitario El Diamante"
}

BASE = os.path.dirname(os.path.abspath(__file__))
RUTAS_PATH = os.path.join(BASE, "rutas_flask.json")

def cargar_rutas():
    if os.path.exists(RUTAS_PATH):
        with open(RUTAS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}

# ─── GENERADOR DE SCRIPT CVRP ─────────────────────────────────────────────────
def generar_script_cvrp(config: dict) -> str:
    """Genera el código Python del CVRP parametrizado con la config del formulario."""
    return f'''
import os, json, math, random
from collections import defaultdict
import numpy as np
import networkx as nx
import osmnx as ox
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

DEPOSITO_COORDS   = ({config["deposito_lat"]}, {config["deposito_lon"]})
ZONA_CENTRO       = ({config["zona_lat"]}, {config["zona_lon"]})
ARCHIVO_OSM       = r"{config["archivo_osm"]}"
KG_POR_CASA       = {config["kg_por_casa"]}
NUM_CAMIONES      = {config["num_camiones"]}
CAPACIDAD_KG      = {config["capacidad_kg"]}
TIEMPO_LIMITE_S   = {config["tiempo_limite"]}
SEED              = 42
DESCARGAR_DE_OSM  = True
ARCHIVO_GRAFO     = r"{config["archivo_graphml"]}"
ARCHIVO_PARADAS   = r"{config["archivo_paradas"]}"
OUTPUT_JSON       = r"{config["output_json"]}"

BBOX = {{
    "minlat": {config["bbox_minlat"]},
    "maxlat": {config["bbox_maxlat"]},
    "minlon": {config["bbox_minlon"]},
    "maxlon": {config["bbox_maxlon"]},
}}

def en_bbox(lat, lon):
    return (BBOX["minlat"] <= lat <= BBOX["maxlat"] and
            BBOX["minlon"] <= lon <= BBOX["maxlon"])

random.seed(SEED)
np.random.seed(SEED)

print("Leyendo red de calles...")
G = ox.graph_from_xml(ARCHIVO_OSM, simplify=True, retain_all=False)
print(f"  Grafo: {{len(G.nodes)}} nodos, {{len(G.edges)}} aristas")

print("Leyendo casas...")
edif = ox.features_from_xml(ARCHIVO_OSM, tags={{"building": True}})
edif = edif[~edif.geometry.isna()].copy()
print(f"  {{len(edif)}} casas en el archivo")
if len(edif) == 0:
    raise SystemExit("No hay casas en el .osm.")

edif_proj = ox.projection.project_gdf(edif)
cent = edif_proj.centroid.to_crs("EPSG:4326")
xs = np.array([p.x for p in cent])
ys = np.array([p.y for p in cent])

idx_zona = [i for i, (x, y) in enumerate(zip(xs, ys)) if en_bbox(y, x)]
print(f"  Casas en zona: {{len(idx_zona)}} / {{len(edif)}}")

xs_f = xs[idx_zona]
ys_f = ys[idx_zona]
nodos_casa = ox.nearest_nodes(G, xs_f, ys_f)

casas_por_nodo = defaultdict(int)
for nd in np.atleast_1d(nodos_casa):
    casas_por_nodo[int(nd)] += 1

paradas = {{str(k): v * KG_POR_CASA for k, v in casas_por_nodo.items()}}
print(f"  {{len(paradas)}} paradas generadas")

deposito_node = ox.nearest_nodes(G, DEPOSITO_COORDS[1], DEPOSITO_COORDS[0])
dist_desde_dep = nx.single_source_dijkstra_path_length(G, deposito_node, weight="length")

nodos_parada = [
    int(nd) for nd in paradas
    if int(nd) in dist_desde_dep and int(nd) != deposito_node
]
print(f"  {{len(nodos_parada)}} paradas alcanzables")

demanda_de = {{int(k): v for k, v in paradas.items()}}
demandas = [0] + [demanda_de[nd] for nd in nodos_parada]
todos_nodos = [deposito_node] + nodos_parada
n = len(todos_nodos)

print("Calculando matriz de distancias...")
dist_matrix = [[0]*n for _ in range(n)]
for i, origen in enumerate(todos_nodos):
    lengths = nx.single_source_dijkstra_path_length(G, origen, weight="length")
    for j, destino in enumerate(todos_nodos):
        dist_matrix[i][j] = int(lengths.get(destino, 10**9))
print("  Matriz lista")

print("Ejecutando CVRP...")
data = {{
    "distance_matrix": dist_matrix,
    "demands": demandas,
    "vehicle_capacities": [CAPACIDAD_KG]*NUM_CAMIONES,
    "num_vehicles": NUM_CAMIONES,
    "depot": 0,
}}

manager = pywrapcp.RoutingIndexManager(n, NUM_CAMIONES, 0)
routing  = pywrapcp.RoutingModel(manager)

def dist_cb(fi, ti):
    return data["distance_matrix"][manager.IndexToNode(fi)][manager.IndexToNode(ti)]
def dem_cb(fi):
    return data["demands"][manager.IndexToNode(fi)]

tcb = routing.RegisterTransitCallback(dist_cb)
routing.SetArcCostEvaluatorOfAllVehicles(tcb)
dcb = routing.RegisterUnaryTransitCallback(dem_cb)
routing.AddDimensionWithVehicleCapacity(dcb, 0, data["vehicle_capacities"], True, "Capacity")

params = pywrapcp.DefaultRoutingSearchParameters()
params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
params.time_limit.seconds = TIEMPO_LIMITE_S

sol = routing.SolveWithParameters(params)
if not sol:
    raise SystemExit("No se encontró solución CVRP.")
print("  Solucion encontrada!")

COLORES = ["#7B2D8B","#4CAF50","#E67E22","#2980B9","#E74C3C","#1ABC9C"]
rutas_export = {{}}
distancia_total = 0

for v in range(NUM_CAMIONES):
    idx = routing.Start(v)
    ruta_nodos, ruta_dist, ruta_carga = [], 0, 0
    while not routing.IsEnd(idx):
        ni = manager.IndexToNode(idx)
        ruta_nodos.append(todos_nodos[ni])
        ruta_carga += data["demands"][ni]
        sig = sol.Value(routing.NextVar(idx))
        ruta_dist += routing.GetArcCostForVehicle(idx, sig, v)
        idx = sig
    ruta_nodos.append(todos_nodos[manager.IndexToNode(idx)])

    paradas_lista = []
    for k, nodo in enumerate(ruta_nodos[1:-1], 1):
        lat = G.nodes[nodo]["y"]
        lon = G.nodes[nodo]["x"]
        dem = demanda_de.get(nodo, 0)
        paradas_lista.append({{
            "id": k, "lat": lat, "lon": lon,
            "direccion": f"Parada #{{k}} — Sector {{v+1}}",
            "demanda_kg": dem, "completada": False
        }})

    vid = str(v+1)
    rutas_export[vid] = {{
        "camion": v+1,
        "conductor": f"Conductor {{vid}}",
        "placa": f"XX-000{{vid}}",
        "distancia_km": round(ruta_dist/1000, 2),
        "paradas_total": len(ruta_nodos)-2,
        "carga_kg": ruta_carga,
        "capacidad_kg": CAPACIDAD_KG,
        "color": COLORES[v % len(COLORES)],
        "estado": "en_ruta",
        "paradas": paradas_lista
    }}
    distancia_total += ruta_dist
    print(f"  Camion {{v+1}}: {{len(ruta_nodos)-2}} paradas | {{ruta_dist/1000:.2f}} km | {{ruta_carga}} kg")

print(f"Distancia total: {{distancia_total/1000:.2f}} km")

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(rutas_export, f, indent=2, ensure_ascii=False)
print(f"JSON guardado: {{OUTPUT_JSON}}")
'''
lock_residentes = threading.Lock()

# ─── Recibe la posición del camión y dispara los avisos ───

@app.route("/api/gps", methods=["POST"])
def api_gps():
    body = request.get_json(silent=True) or {}
    camion_id = body.get("camion_id")
    lat = body.get("lat")
    lon = body.get("lon")
    if camion_id is None or lat is None or lon is None:
        return jsonify({"ok": False, "error": "Faltan camion_id, lat o lon"}), 400
    try:
        with lock_residentes:
            avisados = revisar(camion_id, float(lat), float(lon))
        return jsonify({"ok": True, "avisados": avisados})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── Pantalla del conductor (la abre en su celular) ───
@app.route("/conductor/<camion_id>")
def conductor(camion_id):
    return render_template("conductor.html", camion_id=camion_id)

# ─── Endpoint que dispara la previa (NIVEL DE MÓDULO, antes de app.run) ───
@app.route("/api/notificar-previa", methods=["POST"])
def api_notificar_previa():
    try:
        # el front puede mandar {"camion_id": 1} para avisar solo a ese camión,
        # o nada / {} para avisar a todos
        body = request.get_json(silent=True) or {}
        camion_id = body.get("camion_id")        # None = todos
        enviados = notificar_previa(camion_id)
        return jsonify({"ok": True, "enviados": enviados})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500   

# ─── RUTAS FLASK ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    rutas = cargar_rutas()
    return render_template("index.html", rutas=rutas)

@app.route("/camion/<camion_id>")
def navegacion(camion_id):
    rutas = cargar_rutas()
    if camion_id not in rutas:
        return "Camión no encontrado", 404
    return render_template("navegacion.html", ruta=rutas[camion_id],
                           deposito=DEPOSITO, camion_id=camion_id)

@app.route("/dashboard")
def dashboard():
    rutas = cargar_rutas()
    return render_template("dashboard.html", rutas=rutas)

@app.route("/baseline")
def baseline():
    rutas = cargar_rutas()
    return render_template("baseline.html", rutas=rutas)

@app.route("/api/ruta/<camion_id>")
def api_ruta(camion_id):
    rutas = cargar_rutas()
    if camion_id not in rutas:
        return jsonify({"error": "no encontrado"}), 404
    return jsonify(rutas[camion_id])

@app.route("/api/completar/<camion_id>/<int:parada_id>", methods=["POST"])
def completar_parada(camion_id, parada_id):
    rutas = cargar_rutas()
    if camion_id not in rutas:
        return jsonify({"error": "no encontrado"}), 404
    for p in rutas[camion_id]["paradas"]:
        if p["id"] == parada_id:
            p["completada"] = True
            with open(RUTAS_PATH, "w", encoding="utf-8") as f:
                json.dump(rutas, f, indent=2, ensure_ascii=False)

            try:
                with lock_residentes:
                    avisados = revisar(camion_id, p["lat"], p["lon"])
            except Exception as e:
                print("Error proximidad:", e)
                avisados = 0

            completadas = sum(1 for x in rutas[camion_id]["paradas"] if x["completada"])
            return jsonify({"ok": True, "completadas": completadas, "avisados": avisados})
    return jsonify({"error": "parada no encontrada"}), 404

def _resolver_ruta(ruta: str) -> str:
    """Si la ruta ya es absoluta la devuelve tal cual.
    Si es solo un nombre de archivo, la resuelve relativa al directorio de app.py."""
    if os.path.isabs(ruta):
        return ruta
    return os.path.abspath(os.path.join(BASE, ruta))

@app.route("/api/generar-cvrp", methods=["POST"])
def generar_cvrp():
    """
    Recibe la configuración del formulario, genera el script CVRP,
    lo ejecuta y devuelve el JSON resultante.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No se recibieron datos"}), 400

        # ── Parámetros que ingresa el usuario ──
        kg_por_casa  = int(data.get("kg_por_casa",  5))
        num_camiones = int(data.get("num_camiones", 2))
        capacidad_kg = int(data.get("capacidad_kg", 8000))
        tiempo_limite = int(data.get("tiempo_limite", 30))

        # ── Todo lo demás fijo ──────────────────
        OSM_DIR = r"C:\Users\sanch\Documents\Universidad\CUARTO AÑO\JIC\Optimizaci-n-de-rutas-de-recolecci-n-de-residuos"

        config = {
            "deposito_lat":  8.842671764429827,
            "deposito_lon":  -79.76393584997263,
            "zona_lat":      8.873469020957439,
            "zona_lon":      -79.71761518423519,
            "archivo_osm":     os.path.join(OSM_DIR, "puertocaimito.osm"),
            "archivo_graphml": os.path.join(OSM_DIR, "grafo_Puerto_Caimito.graphml"),
            "archivo_paradas": os.path.join(BASE,    "paradas_recoleccion.json"),
            "kg_por_casa":   kg_por_casa,
            "num_camiones":  num_camiones,
            "capacidad_kg":  capacidad_kg,
            "tiempo_limite": tiempo_limite,
            "bbox_minlat":   8.863337,
            "bbox_maxlat":   8.882626,
            "bbox_minlon":   -79.740533,
            "bbox_maxlon":   -79.707834,
            "output_json":   RUTAS_PATH,
        }

        # Generar script temporal
        script = generar_script_cvrp(config)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(script)
            script_path = tmp.name

        # Ejecutar script
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True, text=True, timeout=300,
            cwd=BASE
        )

        os.unlink(script_path)

        if result.returncode != 0:
            return jsonify({
                "error": "Error al ejecutar el CVRP",
                "detalle": result.stderr[-3000:] if result.stderr else "Sin detalles",
                "stdout": result.stdout[-2000:] if result.stdout else ""
            }), 500

        # Leer JSON generado
        if not os.path.exists(RUTAS_PATH):
            return jsonify({"error": "El script no generó rutas_flask.json"}), 500

        with open(RUTAS_PATH, encoding="utf-8") as f:
            rutas = json.load(f)

        return jsonify({
            "ok": True,
            "rutas": rutas,
            "log": result.stdout[-3000:] if result.stdout else "",
            "num_rutas": len(rutas),
            "resumen": {
                vid: {
                    "paradas": r["paradas_total"],
                    "distancia_km": r["distancia_km"],
                    "carga_kg": r["carga_kg"],
                }
                for vid, r in rutas.items()
            }
        })

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Tiempo de ejecución agotado (>5 min)"}), 504
    except Exception as e:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
 
if __name__ == "__main__":
    # OJO: esto se dispara CADA vez que arrancas el server.
    # Si no lo quieres en cada reinicio, muévelo a donde generas las rutas.
    iniciar_sesion()

    for i, ruta in enumerate(rutas_optimizadas, 1):
        enviar_ruta_asignada(
            numero_vehiculo=i,
            trabajador=f"Operador {i}",
            paradas=len(ruta),
            distancia_km=round(distancia_total[i - 1], 1),   # ⬅ ver nota
        )

    enviar_resumen_diario(
        total_vehiculos=len(rutas_optimizadas),
        total_paradas=sum(len(r) for r in rutas_optimizadas),
        distancia_total=round(sum(distancia_total), 1),
        eficiencia=92,
    )

    app.run(debug=True, host="0.0.0.0", port=5000)
    