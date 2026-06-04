"""
CVRP - Optimización de rutas de recolección de desechos sólidos
Puerto Caimito, La Chorrera
Depósito: Relleno Sanitario El Diamante
2 camiones, 8 toneladas c/u

CÓMO FUNCIONA:
  - Lee la red de calles Y las casas desde tu archivo .osm LOCAL (sin tocar el
    servidor de OSM). Así usa todo lo que dibujaste en JOSM aunque no lo hayas
    podido subir.
  - Las PARADAS se derivan de las CASAS reales (building footprints): cada casa
    se "engancha" (snap) al nodo de calle más cercano y se agregan. Un nodo con
    casas = 1 parada, con demanda = #casas * KG_POR_CASA.
  - Las intersecciones, rotondas y entradas SIN casas NO son paradas; el camión
    solo transita por ellas.

USO:
  1. Asegúrate de que tu .osm (calles + casas) esté en la misma carpeta.
  2. python cvrp_don_juan.py
  3. Abre cvrp_don_juan.html para ver el mapa.
  4. Para iterar rápido luego (sin re-leer el .osm), pon DESCARGAR_DE_OSM = False.
"""

import os
import json
import math
import random
from collections import defaultdict

import numpy as np
import networkx as nx
import osmnx as ox
import folium
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
DEPOSITO_COORDS = (8.842671764429827, -79.76393584997263)   # El Diamante
ZONA_CENTRO     = (8.873469020957439, -79.71761518423519)   # Barriada Puerto Caimito

ARCHIVO_OSM     = "puertocaimito.osm"   # tu archivo local con calles + casas
KG_POR_CASA     = 5           # kg de basura por casa por recolección  ← AJUSTA a tu realidad
NUM_CAMIONES    = 2
CAPACIDAD_KG    = 8000        # 8 toneladas por camión
TIEMPO_LIMITE_S = 30          # segundos de cómputo de OR-Tools
SEED            = 42

DESCARGAR_DE_OSM = True        # True = reconstruye desde el .osm. False = reusa lo guardado.
ARCHIVO_GRAFO    = "grafo_Puerto_Caimito.graphml"
ARCHIVO_PARADAS  = "paradas_recoleccion.json"

COLORES = ["#7B2D8B", "#4CAF50"]   # morado y verde

from bot.siroca_bot import (
    iniciar_sesion,
    enviar_ruta_asignada,
    enviar_resumen_diario
)

# ─── Bounding Box para Puerto Caimito ────────────────────────────────────
BBOX_PUERTO_CAIMITO = {
    'minlat': 8.863337,   # Sur
    'maxlat': 8.882626,   # Norte  
    'minlon': -79.740533,   # Oeste
    'maxlon': -79.707834    # Este
}
 
def esta_en_puerto_caimito(lat, lon):
    """Verifica si una coordenada está dentro del bbox de Puerto Caimito"""
    return (BBOX_PUERTO_CAIMITO['minlat'] <= lat <= BBOX_PUERTO_CAIMITO['maxlat'] and
            BBOX_PUERTO_CAIMITO['minlon'] <= lon <= BBOX_PUERTO_CAIMITO['maxlon'])

random.seed(SEED)
np.random.seed(SEED)

if __name__ == "__main__":
    # Iniciar SIROCA
    iniciar_sesion()

# ─── ① GRAFO + CASAS (desde el .osm local) ────────────────────────────────────
necesita_reconstruir = DESCARGAR_DE_OSM or not (
    os.path.exists(ARCHIVO_GRAFO) and os.path.exists(ARCHIVO_PARADAS)
)

if necesita_reconstruir:
    print(f"📂 Leyendo red de calles desde {ARCHIVO_OSM} ...")
    G = ox.graph_from_xml(ARCHIVO_OSM, simplify=True, retain_all=False)
    print(f"   ✓ Grafo: {len(G.nodes)} nodos, {len(G.edges)} aristas")

    # Casas (building footprints) leídas del MISMO archivo .osm (sin servidor)
    print("🏠 Leyendo casas (building footprints) del .osm ...")
    edif = ox.features_from_xml(ARCHIVO_OSM, tags={"building": True})
    edif = edif[~edif.geometry.isna()].copy()
    print(f"   ✓ {len(edif)} casas en el archivo")
    if len(edif) == 0:
        raise SystemExit(
            "❌ No hay casas en el .osm. Dibuja edificios en JOSM y vuelve a guardarlo."
        )

    # Centroide de cada casa (proyectar a metros para que el centroide sea correcto)
    edif_proj = ox.projection.project_gdf(edif)
    cent = edif_proj.centroid.to_crs("EPSG:4326")
    xs = np.array([p.x for p in cent])   # longitudes
    ys = np.array([p.y for p in cent])   # latitudes

    print("\n📍 Filtrando casas por zona (Puerto Caimito)...")
    casas_en_zona = []
    for idx, (x, y) in enumerate(zip(xs, ys)):
        if esta_en_puerto_caimito(y, x):  # lat, lon
            casas_en_zona.append(idx)
    
    casas_excluidas = len(edif) - len(casas_en_zona)
    print(f"   ✓ Casas en Puerto Caimito: {len(casas_en_zona)}")
    print(f"   ⚠️  Casas excluidas (camino/otras zonas): {casas_excluidas}")
    
    # Usar solo las casas en la zona
    xs_filtrados = xs[casas_en_zona]
    ys_filtrados = ys[casas_en_zona]

    # SNAP: cada casa → nodo de calle más cercano (vectorizado)
    nodos_casa = ox.nearest_nodes(G, xs_filtrados, ys_filtrados)

    # AGREGAR: un nodo con casas = una parada real; demanda = #casas * kg
    casas_por_nodo = defaultdict(int)
    for nodo in np.atleast_1d(nodos_casa):
        casas_por_nodo[int(nodo)] += 1

    paradas = {str(k): v * KG_POR_CASA for k, v in casas_por_nodo.items()}

    ox.save_graphml(G, ARCHIVO_GRAFO)
    with open(ARCHIVO_PARADAS, "w", encoding="utf-8") as f:
        json.dump(paradas, f)
    print(f"   ✓ Guardado: {ARCHIVO_GRAFO}  y  {ARCHIVO_PARADAS}")
    print(f"   ✓ {len(edif)} casas → {len(paradas)} paradas (de {len(G.nodes)} nodos)")
else:
    print("📂 Cargando grafo y paradas guardados...")
    G = ox.load_graphml(ARCHIVO_GRAFO)
    with open(ARCHIVO_PARADAS, "r", encoding="utf-8") as f:
        paradas = json.load(f)
    print(f"   ✓ Grafo: {len(G.nodes)} nodos | {len(paradas)} paradas")

# ─── ② NODOS PARA EL RUTEO ────────────────────────────────────────────────────
deposito_node = ox.nearest_nodes(G, DEPOSITO_COORDS[1], DEPOSITO_COORDS[0])
print(f"\n   ✓ Depósito → nodo {deposito_node}")

# Aviso si el .osm no cubre el depósito El Diamante (~5 km de la barriada)
d_dep = math.hypot(G.nodes[deposito_node]["y"] - DEPOSITO_COORDS[0],
                   G.nodes[deposito_node]["x"] - DEPOSITO_COORDS[1]) * 111000
if d_dep > 500:
    print(f"   ⚠ El nodo del depósito quedó a ~{d_dep:.0f} m de El Diamante. "
          f"Tu .osm probablemente no incluye el depósito ni la vía que lo conecta; "
          f"las distancias de salida/regreso saldrán mal.")

# Conservar solo paradas alcanzables desde el depósito (descarta islas)
dist_desde_dep = nx.single_source_dijkstra_path_length(G, deposito_node, weight="length")
nodos_parada = [
    int(nd) for nd in paradas
    if int(nd) in dist_desde_dep and int(nd) != deposito_node
]
descartadas = len(paradas) - len(nodos_parada)
if descartadas:
    print(f"   ⚠ {descartadas} paradas inalcanzables descartadas")

demanda_de       = {int(k): v for k, v in paradas.items()}
demandas         = [0] + [demanda_de[nd] for nd in nodos_parada]
todos_nodos_ruta = [deposito_node] + nodos_parada
n                = len(todos_nodos_ruta)

demanda_total   = sum(demandas)
capacidad_total = CAPACIDAD_KG * NUM_CAMIONES
print(f"   ✓ {len(nodos_parada)} paradas | demanda total: {demanda_total} kg "
      f"| capacidad flota: {capacidad_total} kg")
if demanda_total > capacidad_total:
    print("   ⚠ La demanda supera la capacidad de la flota: el CVRP será infactible. "
          "Sube NUM_CAMIONES o baja KG_POR_CASA.")

# ─── ③ MATRIZ DE DISTANCIAS ───────────────────────────────────────────────────
print("\n🔢 Calculando matriz de distancias (sobre la red completa)...")
dist_matrix = [[0] * n for _ in range(n)]
for i, origen in enumerate(todos_nodos_ruta):
    lengths = nx.single_source_dijkstra_path_length(G, origen, weight="length")
    for j, destino in enumerate(todos_nodos_ruta):
        dist_matrix[i][j] = int(lengths.get(destino, 10**9))
print("   ✓ Matriz lista")

# ─── ④ CVRP CON OR-TOOLS ──────────────────────────────────────────────────────
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
params.time_limit.seconds = TIEMPO_LIMITE_S

solucion = routing.SolveWithParameters(params)
if not solucion:
    print("❌ No se encontró solución.")
    raise SystemExit

print("   ✓ ¡Solución encontrada!")

# ─── ⑤ EXTRAER RUTAS ──────────────────────────────────────────────────────────
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
    rutas.append({"vehiculo": vehiculo + 1, "nodos": ruta_nodos,
                  "distancia_m": ruta_dist, "carga_kg": ruta_carga,
                  "paradas": len(ruta_nodos) - 2})
    distancia_total += ruta_dist
    print(f"   Camión {vehiculo+1}: {len(ruta_nodos)-2} paradas | "
          f"{ruta_dist/1000:.2f} km | {ruta_carga} kg")

print(f"   📊 Distancia total: {distancia_total/1000:.2f} km")

# ─── ⑥ MAPA FOLIUM ────────────────────────────────────────────────────────────
print("\n🗺️  Generando mapa interactivo...")
mapa = folium.Map(location=ZONA_CENTRO, zoom_start=15, tiles="CartoDB positron")

folium.Marker(
    location=DEPOSITO_COORDS,
    popup="🏭 Relleno Sanitario El Diamante",
    tooltip="Depósito",
    icon=folium.Icon(color="black", icon="home", prefix="fa"),
).add_to(mapa)

for r in rutas:
    color = COLORES[(r["vehiculo"] - 1) % len(COLORES)]
    grupo = folium.FeatureGroup(
        name=f"🚛 Camión {r['vehiculo']} — {r['paradas']} paradas | "
             f"{r['distancia_m']/1000:.1f} km | {r['carga_kg']} kg"
    )

    # Trazar la ruta por los segmentos reales de calle
    for k in range(len(r["nodos"]) - 1):
        try:
            camino = nx.shortest_path(G, r["nodos"][k], r["nodos"][k + 1], weight="length")
            coords = [(G.nodes[nd]["y"], G.nodes[nd]["x"]) for nd in camino]
            folium.PolyLine(coords, color=color, weight=4, opacity=0.85).add_to(grupo)
        except Exception:
            pass

    # Marcar las paradas (cada una representa el grupo de casas de ese tramo)
    for stop_n, nodo in enumerate(r["nodos"][1:-1], 1):
        lat = G.nodes[nodo]["y"]
        lon = G.nodes[nodo]["x"]
        dem = demanda_de.get(nodo, 0)
        casas = dem // KG_POR_CASA if KG_POR_CASA else dem
        folium.CircleMarker(
            location=(lat, lon), radius=5, color=color,
            fill=True, fill_opacity=0.85,
            popup=f"<b>Parada #{stop_n}</b> — Camión {r['vehiculo']}<br>"
                  f"~{casas} casas · {dem} kg",
            tooltip=f"C{r['vehiculo']} · #{stop_n} ({dem} kg)",
        ).add_to(grupo)

    grupo.add_to(mapa)

folium.LayerControl(collapsed=False).add_to(mapa)

# Panel de resumen
filas_camiones = "".join([
    f"<tr><td>🚛 Camión {r['vehiculo']}</td>"
    f"<td style='color:{COLORES[(r['vehiculo']-1) % len(COLORES)]}'>{r['paradas']}</td>"
    f"<td>{r['distancia_m']/1000:.1f} km</td>"
    f"<td>{r['carga_kg']} kg</td></tr>"
    for r in rutas
])

panel_html = f"""
<div style="position:fixed;bottom:25px;left:25px;z-index:1000;background:white;
            padding:14px 18px;border-radius:10px;
            box-shadow:0 2px 12px rgba(0,0,0,0.25);
            font-family:Arial,sans-serif;font-size:13px;">
  <b style="color:#7B2D8B;font-size:14px;">🗑️ CVRP — Puerto Caimito</b>
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

# ─── ⑦ MÉTRICAS JSON ──────────────────────────────────────────────────────────
metricas = {
    "zona": "Barriada Puerto Caimito, La Chorrera",
    "deposito": "Relleno Sanitario El Diamante",
    "coordenadas_deposito": DEPOSITO_COORDS,
    "num_camiones": NUM_CAMIONES,
    "capacidad_kg": CAPACIDAD_KG,
    "kg_por_casa": KG_POR_CASA,
    "total_paradas": len(nodos_parada),
    "demanda_total_kg": demanda_total,
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
print(f"\n📊 RESUMEN:")
print(f"   Distancia total: {distancia_total/1000:.2f} km")
for r in rutas:
    util = r["carga_kg"] / CAPACIDAD_KG * 100
    print(f"   Camión {r['vehiculo']}: {r['paradas']} paradas | "
          f"{r['distancia_m']/1000:.2f} km | {r['carga_kg']} kg ({util:.0f}% capacidad)")
    
    # Notificar cada ruta
    for i, ruta in enumerate(rutas_optimizadas, 1):
        enviar_ruta_asignada(
            numero_vehiculo=i,
            trabajador=f"Operador {i}",
            paradas=len(ruta),
            distancia_km=round(distancia_total[i], 1)
        )
    
    # Resumen final
    enviar_resumen_diario(
        total_vehiculos=len(rutas_optimizadas),
        total_paradas=sum(len(r) for r in rutas_optimizadas),
        distancia_total=sum(distancia_total),
        eficiencia=92
    )