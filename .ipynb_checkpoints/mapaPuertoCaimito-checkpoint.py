import osmnx as ox

G = ox.graph_from_place("Puerto Caimito, Panama", network_type="drive")
ox.plot_graph(G)