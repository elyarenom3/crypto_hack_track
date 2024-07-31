import numpy as np
import requests
import networkx as nx
import matplotlib.pyplot as plt
import time
from datetime import datetime
import random

# Function to fetch transactions for a given account with retry on rate limiting and 504 errors
def get_transactions(account, marker=None, limit=200, retries=5, timeout=10):
    url = f"https://api.xrpscan.com/api/v1/account/{account}/transactions"
    params = {'marker': marker, 'limit': limit} if marker else {'limit': limit}
    attempt = 0
    while attempt < retries:
        try:
            response = requests.get(url, params=params, timeout=timeout)
            if response.status_code == 429:
                print("Rate limit hit, sleeping for 60 seconds...")
                time.sleep(60)
            else:
                response.raise_for_status()
                return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 504:
                print(f"504 error, retrying... ({attempt + 1}/{retries})")
                time.sleep(30)
                attempt += 1
            else:
                raise e
    raise Exception("Max retries exceeded")

# Recursive function to fetch all transactions for an account within a date range
def fetch_all_transactions(account, start_datetime, end_datetime, depth=1, max_depth=2, limit=200):
    transactions = []
    marker = None
    while True:
        data = get_transactions(account, marker, limit)
        for txn in data['transactions']:
            txn_date = datetime.strptime(txn['date'], '%Y-%m-%dT%H:%M:%S.%fZ')
            if start_datetime <= txn_date <= end_datetime:
                transactions.append(txn)
        if 'marker' in data and depth < max_depth:
            marker = data['marker']
        else:
            break
    return transactions

# Recursive function to trace XRP flow within a date range
def trace_transactions(account, start_datetime, end_datetime, depth=0, max_depth=2, traced=set(), node_levels={}):
    if depth > max_depth or account in traced:
        return []

    print(f"Tracing transactions for account {account} at depth {depth}")

    traced.add(account)
    transactions = fetch_all_transactions(account, start_datetime, end_datetime, depth, max_depth)
    all_transactions = []

    for txn in transactions:
        if 'Destination' in txn and 'Amount' in txn:  # Check if 'Destination' and 'Amount' fields exist
            destination = txn['Destination']
            if destination not in traced:
                all_transactions.append(txn)
                node_levels[destination] = depth + 1
                all_transactions.extend(trace_transactions(destination, start_datetime, end_datetime, depth + 1, max_depth, traced, node_levels))

    return all_transactions

# Create a graph from transactions
def build_graph(transactions, node_levels):
    G = nx.DiGraph()
    for txn in transactions:
        source = txn['Account']
        if 'Destination' in txn and 'Amount' in txn:  # Ensure 'Destination' and 'Amount' fields exist
            destination = txn['Destination']
            amount = txn['Amount']['value']
            G.add_edge(source, destination, weight=float(amount) / 1_000_000)  # Convert from drops to XRP
            if source not in node_levels:
                node_levels[source] = 0  # Original wallet level
            # Set the subset_key attribute for each node
            G.nodes[source]['subset_key'] = node_levels[source]
            G.nodes[destination]['subset_key'] = node_levels[destination]
    return G

def format_wallet_address(address):
    return f"{address[:4]}...{address[-4:]}"

# Visualize the graph
def visualize_graph(G, node_levels, scale_factor=3.0, filename="graph.png"):
    pos = {}
    level_nodes = {}
    max_depth = max(node_levels.values())

    # Group nodes by levels
    for node, level in node_levels.items():
        if level not in level_nodes:
            level_nodes[level] = []
        level_nodes[level].append(node)

    # Sort nodes at each level by descending transaction amount
    for level, nodes in level_nodes.items():
        if level == 0:
            pos[nodes[0]] = (0, 0)
        else:
            nodes.sort(key=lambda node: sum([G.edges[edge]['weight'] for edge in G.in_edges(node)]), reverse=True)
            for i, node in enumerate(nodes):
                pos[node] = (level, -i)

    # Perturb node positions slightly to avoid overlapping edges
    for node in pos:
        x, y = pos[node]
        pos[node] = (x + random.uniform(-0.05, 0.05), y + random.uniform(-0.05, 0.05))

    plt.figure(figsize=(30, 30))

    color_map = []
    for node in G:
        level = node_levels[node]
        gray_value = 1 - (level / max(node_levels.values())) * 0.8  # Shades of gray
        color_map.append((gray_value, gray_value, gray_value))

    edge_weights = [G.edges[edge]['weight'] for edge in G.edges]
    sorted_weights = sorted(edge_weights)
    quantiles = np.percentile(sorted_weights, [25, 50, 75])

    # Create color map for edges
    edge_color_map = []
    for edge in G.edges:
        weight = G.edges[edge]['weight']
        if weight <= quantiles[0]:
            edge_color_map.append('#084960')  # Color for first quartile
        elif weight <= quantiles[1]:
            edge_color_map.append('#016E93')  # Color for second quartile
        elif weight <= quantiles[2]:
            edge_color_map.append('#4897B4')  # Color for third quartile
        else:
            edge_color_map.append('#B0D8E9')  # Color for fourth quartile

    labels = {node: format_wallet_address(node) for node in G.nodes}
    nx.draw(G, pos, with_labels=True, labels=labels, node_size=200, node_color=color_map, font_size=10, font_weight='bold',
            edge_color=edge_color_map)
    edge_labels = {edge: f"{G.edges[edge]['weight']:,} XRP" for edge in G.edges}
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)
    plt.savefig(filename)
    print(f"Graph saved as {filename}")

# Main function
if __name__ == "__main__":
    initial_account = "rJNLz3A1qPKfWCtJLPhmMZAfBkutC2Qojm"
    start_datetime_str = "2024-01-30T00:00:00"
    end_datetime_str = "2024-07-16T23:59:59"
    start_datetime = datetime.strptime(start_datetime_str, '%Y-%m-%dT%H:%M:%S')
    end_datetime = datetime.strptime(end_datetime_str, '%Y-%m-%dT%H:%M:%S')

    node_levels = {initial_account: 0}  # Level of the initial account
    transactions = trace_transactions(initial_account, start_datetime, end_datetime, max_depth=2, node_levels=node_levels)
    G = build_graph(transactions, node_levels)
    visualize_graph(G, node_levels, scale_factor=3.0, filename="ripple_hack_graph.png")  # Adjust the scale_factor to increase spacing
