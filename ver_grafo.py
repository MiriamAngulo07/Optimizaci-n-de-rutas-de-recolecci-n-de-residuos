import osmnx as ox
import matplotlib.pyplot as plt

G = ox.load_graphml("grafo_Puerto_Caimito.graphml")
edif = ox.features_from_xml("puertocaimito.osm", tags={"building": True})

# Recortar al bbox de Puerto Caimito
G = ox.truncate.truncate_graph_bbox(
    G,
    bbox=(8.882626, 8.863337, -79.707834, -79.740533)  # norte, sur, este, oeste
)

fig, ax = ox.plot_graph(
    G,
    figsize=(14, 14),
    node_size=3,
    node_color="#005F02",
    edge_color="#427A43",
    edge_linewidth=0.6,
    bgcolor="#e6eec9",
    show=False,
    close=False
)

edif.plot(ax=ax, color="#a03030", alpha=0.6, edgecolor="#7a0000", linewidth=0.5)

ax.set_xlim(-79.740533, -79.707834)
ax.set_ylim(8.863337, 8.882626)

ax.set_title("Red vial + casas — Puerto Caimito", fontsize=14, color="#2c3a3b")
plt.savefig("grafo_con_casas.png", dpi=150, bbox_inches="tight")
plt.show()