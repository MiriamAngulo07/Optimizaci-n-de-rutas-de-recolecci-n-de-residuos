"""
CVRP - Optimización de rutas de recolección de desechos sólidos
Puerto Caimito, La Chorrera
Depósito: Relleno Sanitario El Diamante
2 camiones, 8 toneladas c/u

INSTRUCCIONES:
  1. Reemplaza la sección "CARGAR TU GRAFO" con tu propio grafo de OSMnx
  2. Corre el script: python cvrp_don_juan.py
  3. Abre cvrp_don_juan.html para ver el mapa
"""
import pandas as pd
import osmnx as ox
import folium
import numpy as np
import random
import json
import networkx as nx
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
DEPOSITO_COORDS = (8.842671764429827, -79.76393584997263)  # El Diamante
ZONA_CENTRO     = (8.873469020957439, -79.71761518423519)   # Puerto Caimito
NUM_PUNTOS      = 300
NUM_CAMIONES    = 2
CAPACIDAD_KG    = 8000                 # 8 toneladas por camión
SEED            = 42

COLORES = ["#7B2D8B", "#4CAF50"]       # morado y verde

random.seed(SEED)
np.random.seed(SEED)

G = ox.load_graphml("grafo_Puerto_Caimito.graphml")
print(f"   ✓ Grafo: {len(G.nodes)} nodos, {len(G.edges)} aristas")

# ─── ② NODO DEL DEPÓSITO ──────────────────────────────────────────────────────
# Con grafo real de OSMnx usa:
#   deposito_node = ox.nearest_nodes(G, DEPOSITO_COORDS[1], DEPOSITO_COORDS[0])
# Con grafo sintético usamos el nodo más cercano manualmente:
def nodo_mas_cercano(G, lat, lon):
    mejor, mejor_d = None, float("inf")
    for n, d in G.nodes(data=True):
        dist = ((d["y"] - lat)**2 + (d["x"] - lon)**2) ** 0.5
        if dist < mejor_d:
            mejor_d = dist
            mejor = n
    return mejor

deposito_node = nodo_mas_cercano(G, DEPOSITO_COORDS[0], DEPOSITO_COORDS[1])
print(f"   ✓ Depósito → nodo {deposito_node}")

# ─── ③ PUNTOS DE RECOLECCIÓN (nodos del grafo) ────────────────────────────────
print("\n📍 Generando puntos de recolección desde el grafo...")

todos_nodos = [n for n in G.nodes if n != deposito_node]
nodos_recoleccion = random.sample(todos_nodos, min(NUM_PUNTOS, len(todos_nodos)))

demandas = [0] + [random.randint(3, 8) for _ in nodos_recoleccion]
todos_nodos_ruta = [deposito_node] + nodos_recoleccion

print(f"   ✓ {len(nodos_recoleccion)} puntos | demanda total: {sum(demandas)} kg")

# ─── ④ MATRIZ DE DISTANCIAS ───────────────────────────────────────────────────
print("\n🔢 Calculando matriz de distancias...")
n = len(todos_nodos_ruta)
dist_matrix = [[0] * n for _ in range(n)]

for i, origen in enumerate(todos_nodos_ruta):
    lengths = nx.single_source_dijkstra_path_length(G, origen, weight="length")
    for j, destino in enumerate(todos_nodos_ruta):
        dist_matrix[i][j] = int(lengths.get(destino, 999999))

print("   ✓ Matriz lista")

# ─── ⑤ CVRP CON OR-TOOLS ─────────────────────────────────────────────────────
print("\n🚛 Ejecutando CVRP con OR-Tools...")

data = {
    "distance_matrix": dist_matrix,
    "demands": demandas,
    "vehicle_capacities": [CAPACIDAD_KG] * NUM_CAMIONES,
    "num_vehicles": NUM_CAMIONES,
    "depot": 0,
}

manager = pywrapcp.RoutingIndexManager(n, NUM_CAMIONES, data["depot"])
routing = pywrapcp.RoutingModel(manager)

def distancia_callback(from_idx, to_idx):
    return data["distance_matrix"][manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]

transit_cb = routing.RegisterTransitCallback(distancia_callback)
routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

def demanda_callback(from_idx):
    return data["demands"][manager.IndexToNode(from_idx)]

demand_cb = routing.RegisterUnaryTransitCallback(demanda_callback)
routing.AddDimensionWithVehicleCapacity(demand_cb, 0, data["vehicle_capacities"], True, "Capacity")

params = pywrapcp.DefaultRoutingSearchParameters()
params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
params.time_limit.seconds = 20

solucion = routing.SolveWithParameters(params)

if not solucion:
    print("❌ No se encontró solución.")
    exit()

print("   ✓ ¡Solución encontrada!")

# ─── ⑥ EXTRAER RUTAS ──────────────────────────────────────────────────────────
rutas = []
distancia_total = 0

for vehiculo in range(NUM_CAMIONES):
    idx = routing.Start(vehiculo)
    ruta_nodos, ruta_dist, ruta_carga = [], 0, 0

    while not routing.IsEnd(idx):
        node_idx = manager.IndexToNode(idx)
        ruta_nodos.append(todos_nodos_ruta[node_idx])
        ruta_carga += data["demands"][node_idx]
        sig = solucion.Value(routing.NextVar(idx))
        ruta_dist += routing.GetArcCostForVehicle(idx, sig, vehiculo)
        idx = sig

    ruta_nodos.append(todos_nodos_ruta[manager.IndexToNode(idx)])
    rutas.append({"vehiculo": vehiculo+1, "nodos": ruta_nodos,
                  "distancia_m": ruta_dist, "carga_kg": ruta_carga,
                  "paradas": len(ruta_nodos) - 2})
    distancia_total += ruta_dist
    print(f"   Camión {vehiculo+1}: {len(ruta_nodos)-2} paradas | {ruta_dist/1000:.2f} km | {ruta_carga} kg")

print(f"   📊 Distancia total: {distancia_total/1000:.2f} km")

# ─── ⑦ MAPA FOLIUM ────────────────────────────────────────────────────────────
print("\n🗺️  Generando mapa interactivo...")

mapa = folium.Map(location=ZONA_CENTRO, zoom_start=14, tiles="CartoDB positron")

# Depósito
folium.Marker(
    location=DEPOSITO_COORDS,
    popup="🏭 Relleno Sanitario El Diamante",
    tooltip="Depósito",
    icon=folium.Icon(color="black", icon="home", prefix="fa"),
).add_to(mapa)

nodo_a_idx = {n: i for i, n in enumerate(todos_nodos_ruta)}

for r in rutas:
    color = COLORES[r["vehiculo"] - 1]
    grupo = folium.FeatureGroup(
        name=f"🚛 Camión {r['vehiculo']} — {r['paradas']} paradas | {r['distancia_m']/1000:.1f} km | {r['carga_kg']} kg"
    )

    # Trazar ruta por segmentos reales
    for k in range(len(r["nodos"]) - 1):
        try:
            camino = nx.shortest_path(G, r["nodos"][k], r["nodos"][k+1], weight="length")
            coords = [(G.nodes[nd]["y"], G.nodes[nd]["x"]) for nd in camino]
            folium.PolyLine(coords, color=color, weight=4, opacity=0.85).add_to(grupo)
        except Exception:
            pass

    # Puntos de parada
    for stop_n, nodo in enumerate(r["nodos"][1:-1], 1):
        lat = G.nodes[nodo]["y"]
        lon = G.nodes[nodo]["x"]
        dem = demandas[nodo_a_idx[nodo]]
        folium.CircleMarker(
            location=(lat, lon), radius=5, color=color,
            fill=True, fill_opacity=0.85,
            popup=f"<b>Parada #{stop_n}</b> — Camión {r['vehiculo']}<br>Demanda: {dem} kg",
            tooltip=f"C{r['vehiculo']} - #{stop_n} ({dem} kg)",
        ).add_to(grupo)

    grupo.add_to(mapa)

folium.LayerControl(collapsed=False).add_to(mapa)

# Panel de resumen
filas_camiones = "".join([
    f"<tr><td>🚛 Camión {r['vehiculo']}</td>"
    f"<td style='color:{COLORES[r['vehiculo']-1]}'>{r['paradas']}</td>"
    f"<td>{r['distancia_m']/1000:.1f} km</td>"
    f"<td>{r['carga_kg']} kg</td></tr>"
    for r in rutas
])

panel_html = f"""
<div style="position:fixed;bottom:25px;left:25px;z-index:1000;background:white;
            padding:14px 18px;border-radius:10px;
            box-shadow:0 2px 12px rgba(0,0,0,0.25);
            font-family:Arial,sans-serif;font-size:13px;">
  <b style="color:#7B2D8B;font-size:14px;">🗑️ CVRP — Don Juan, Puerto Caimito</b>
  <hr style="margin:6px 0;border-color:#eee">
  <table style="border-collapse:collapse;width:100%">
    <tr style="color:#888;font-size:11px">
      <th align="left">Vehículo</th><th>Paradas</th><th>Distancia</th><th>Carga</th>
    </tr>
    {filas_camiones}
    <tr style="border-top:1px solid #eee;font-weight:bold">
      <td>TOTAL</td><td>{sum(r['paradas'] for r in rutas)}</td>
      <td>{distancia_total/1000:.1f} km</td>
      <td>{sum(r['carga_kg'] for r in rutas)} kg</td>
    </tr>
  </table>
</div>
"""
mapa.get_root().html.add_child(folium.Element(panel_html))

output_html = "cvrp_don_juan.html"
mapa.save(output_html)
print(f"   ✓ Mapa guardado: {output_html}")

# ─── ⑧ MÉTRICAS JSON ──────────────────────────────────────────────────────────
metricas = {
    "zona": "Don Juan, Puerto Caimito, La Chorrera",
    "deposito": "Relleno Sanitario El Diamante",
    "coordenadas_deposito": DEPOSITO_COORDS,
    "num_camiones": NUM_CAMIONES,
    "capacidad_kg": CAPACIDAD_KG,
    "total_puntos": len(nodos_recoleccion),
    "distancia_total_km": round(distancia_total / 1000, 2),
    "rutas": [
        {
            "camion": r["vehiculo"],
            "paradas": r["paradas"],
            "distancia_km": round(r["distancia_m"] / 1000, 2),
            "carga_kg": r["carga_kg"],
            "utilizacion_pct": round(r["carga_kg"] / CAPACIDAD_KG * 100, 1),
        }
        for r in rutas
    ],
}

with open("metricas_cvrp.json", "w", encoding="utf-8") as f:
    json.dump(metricas, f, indent=2, ensure_ascii=False)

print("   ✓ Métricas guardadas: metricas_cvrp.json")

print("\n✅ ¡Todo listo!")
print(f"   → Abre '{output_html}' en tu navegador para ver el mapa")
print(f"   → 'metricas_cvrp.json' tiene los datos para el dashboard")
print(f"\n📊 RESUMEN:")
print(f"   Distancia total: {distancia_total/1000:.2f} km")
for r in rutas:
    util = r['carga_kg'] / CAPACIDAD_KG * 100
    print(f"   Camión {r['vehiculo']}: {r['paradas']} paradas | {r['distancia_m']/1000:.2f} km | {r['carga_kg']} kg ({util:.0f}% capacidad)")
