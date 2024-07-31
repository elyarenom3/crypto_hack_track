import numpy as np
import requests
import networkx as nx
import matplotlib.pyplot as plt
import time
from datetime import datetime, timedelta
import random
from dotenv import load_dotenv
import os

load_dotenv()
# Etherscan API key
API_KEY = os.getenv('ETHERSCAN_API_KEY')

# Function to fetch transactions for a given account with retry on rate limiting
def get_transactions(account, startblock=0, endblock=99999999, page=1, offset=10000, sort='desc'):
    url = f"https://api.etherscan.io/api"
    params = {
        'module': 'account',
        'action': 'txlist',
        'address': account,
        'startblock': startblock,
        'endblock': endblock,
        'page': page,
        'offset': offset,
        'sort': sort,
        'apikey': API_KEY
    }
    while True:
        response = requests.get(url, params=params)
        if response.status_code == 429:
            print("Rate limit hit, sleeping for 60 seconds...")
            time.sleep(60)
        else:
            response.raise_for_status()
            return response.json()


# Recursive function to fetch all transactions for an account within a date range
def fetch_all_transactions(account, start_datetime, end_datetime, depth=1, max_depth=2):
    transactions = []
    page = 1
    while True:
        data = get_transactions(account, page=page)
        if data['status'] == '0':
            break
        for txn in data['result']:
            txn_time = int(txn['timeStamp'])
            txn_date = datetime.utcfromtimestamp(txn_time)
            amount = float(txn['value']) / 1e18  # Convert from Wei to Ether
            if start_datetime <= txn_date <= end_datetime and amount > 0.0000:
                print(f"Including transaction: {txn['hash']} - {amount:.10f} ETH")  # Debug statement
                transactions.append(txn)
        if len(data['result']) < 10000:
            break
        page += 1
    return transactions


# Recursive function to trace ETH flow within a date range
def trace_transactions(account, start_datetime, end_datetime, depth=0, max_depth=2, traced=set(), node_levels={}):
    if depth > max_depth or account in traced:
        return []

    print(f"Tracing transactions for account {account} at depth {depth}")

    traced.add(account)
    transactions = fetch_all_transactions(account, start_datetime, end_datetime, depth, max_depth)
    all_transactions = []

    for txn in transactions:
        destination = txn['to']
        amount = float(txn['value']) / 1e18  # Convert from Wei to Ether
        if destination and destination not in traced and amount > 0.0000:
            all_transactions.append(txn)
            node_levels[destination] = depth + 1
            all_transactions.extend(
                trace_transactions(destination, start_datetime, end_datetime, depth + 1, max_depth, traced,
                                   node_levels))

    return all_transactions


def build_graph(transactions, node_levels):
    G = nx.DiGraph()
    for txn in transactions:
        source = txn['from']
        destination = txn['to']
        amount = float(txn['value']) / 1e18  # Convert from Wei to Ether
        G.add_edge(source, destination, weight=amount)
        if source not in node_levels:
            node_levels[source] = 0  # Original wallet level
        # Set the subset_key attribute for each node
        G.nodes[source]['subset_key'] = node_levels[source]
        G.nodes[destination]['subset_key'] = node_levels[destination]
    return G


def format_wallet_address(address):
    return f"{address[:4]}...{address[-4:]}"


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

    remaining_nodes = set(G.nodes) - set(pos.keys())
    for node in remaining_nodes:
        pos[node] = (random.uniform(0, max_depth + 1), random.uniform(-len(G.nodes) / 2, len(G.nodes) / 2))

    plt.figure(figsize=(30, 30))

    color_map = []
    for node in G:
        level = node_levels[node]
        gray_value = 1 - (level / max(node_levels.values())) * 0.8
        color_map.append((gray_value, gray_value, gray_value))

    edge_weights = [G.edges[edge]['weight'] for edge in G.edges]

    if edge_weights:  # Check if edge_weights is not empty
        sorted_weights = sorted(edge_weights)
        quantiles = np.percentile(sorted_weights, [25, 50, 75])

        edge_color_map = []
        for edge in G.edges:
            weight = G.edges[edge]['weight']
            if weight <= quantiles[0]:
                edge_color_map.append('#084960')
            elif weight <= quantiles[1]:
                edge_color_map.append('#016E93')
            elif weight <= quantiles[2]:
                edge_color_map.append('#4897B4')
            else:
                edge_color_map.append('#B0D8E9')
    else:
        edge_color_map = ['#084960'] * len(G.edges)  # Default color if no edges

    labels = {node: format_wallet_address(node) for node in G.nodes}
    nx.draw(G, pos, with_labels=True, labels=labels, node_size=200, node_color=color_map, font_size=10,
            font_weight='bold',
            edge_color=edge_color_map)
    edge_labels = {edge: f"{G.edges[edge]['weight']:,} ETH" for edge in G.edges}
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)
    plt.savefig(filename)
    print(f"Graph saved as {filename}")


# Main function
if __name__ == "__main__":
    initial_account = "0xb566f98023AD311499f4A30350da878FFd543954"
    end_datetime = datetime.utcnow()
    start_datetime = end_datetime - timedelta(weeks=13)

    node_levels = {initial_account: 0}  # Level of the initial account
    transactions = trace_transactions(initial_account, start_datetime, end_datetime, max_depth=2,
                                      node_levels=node_levels)
    G = build_graph(transactions, node_levels)
    visualize_graph(G, node_levels, scale_factor=3.0,
                    filename="ena_claimer1.png")