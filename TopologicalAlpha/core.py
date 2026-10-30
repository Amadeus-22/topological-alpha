"""Pure functions behind the strategy: no LEAN imports, so they run under pytest.

Inputs are pandas objects indexed by symbol (any hashable), outputs are plain
Python lists and dicts. The LEAN models only fetch data and call these.
"""
# region imports
from __future__ import annotations

import math

import numpy as np
import pandas as pd
# endregion

TRADING_DAYS = 252


def log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Daily log returns of a (days x symbols) price frame, rows with gaps dropped."""
    return np.log(prices / prices.shift(1)).iloc[1:].dropna(axis=1, how="any")


def mapper_clusters(returns: pd.DataFrame, n_cubes: int = 10, overlap: float = 0.1,
                    eps: float = 0.5, min_samples: int = 5, seed: int = 1) -> list[list]:
    """Connected components of the Mapper graph of the symbols' return paths.

    Same construction as QuantConnect's "Portfolio Construction Using Topological
    Data Analysis": each symbol is a point whose coordinates are its daily log
    returns; the lens is PCA (80% of variance) followed by a 1-d UMAP; each cover
    interval is clustered with DBSCAN on correlation distance. Symbols DBSCAN
    marks as noise belong to no node and are left out. Two nodes sharing a member
    are linked, so a connected component is a set of symbols that move together.

    :param returns: (days x symbols) log returns
    :return: components as lists of symbols, largest first
    """
    import kmapper as km
    from sklearn.cluster import DBSCAN
    from sklearn.decomposition import PCA
    from umap import UMAP

    points = returns.T
    mapper = km.KeplerMapper(verbose=0)
    lens = mapper.fit_transform(points.values, projection=[
        PCA(n_components=0.8, random_state=seed),
        UMAP(n_components=1, random_state=seed),
    ])
    graph = mapper.map(lens, points.values,
                       clusterer=DBSCAN(eps=eps, min_samples=min_samples, metric="correlation"),
                       cover=km.Cover(n_cubes=n_cubes, perc_overlap=overlap))
    nodes = {node: [points.index[i] for i in members] for node, members in graph["nodes"].items()}
    return connected_components(nodes, graph["links"])


def connected_components(nodes: dict[str, list], links: dict[str, list[str]]) -> list[list]:
    """Groups the members of linked nodes, largest component first.

    :param nodes: node id -> member symbols
    :param links: node id -> linked node ids
    """
    parent = {node: node for node in nodes}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for node, linked in links.items():
        for other in linked:
            if node in parent and other in parent:
                parent[find(node)] = find(other)

    groups: dict[str, set] = {}
    for node, members in nodes.items():
        groups.setdefault(find(node), set()).update(members)
    return sorted((sorted(group, key=str) for group in groups.values()), key=lambda g: (-len(g), str(g[0])))


def correlation_clusters(returns: pd.DataFrame, n_clusters: int) -> list[list]:
    """Fallback: average-linkage clusters on correlation distance, largest first."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    corr = returns.corr().clip(-1.0, 1.0).values
    distance = np.sqrt(np.maximum(0.0, 2.0 * (1.0 - corr)))
    np.fill_diagonal(distance, 0.0)
    labels = fcluster(linkage(squareform(distance, checks=False), method="average"),
                      t=min(n_clusters, len(returns.columns)), criterion="maxclust")
    groups: dict[int, list] = {}
    for symbol, label in zip(returns.columns, labels, strict=True):
        groups.setdefault(label, []).append(symbol)
    return sorted(groups.values(), key=lambda g: (-len(g), str(g[0])))


def momentum_scores(prices: pd.DataFrame, lookback: int = 252, skip: int = 21,
                    vol_window: int = 126) -> pd.Series:
    """12-1 month momentum divided by annualised volatility, per symbol.

    The last ``skip`` days are left out to avoid the short-term reversal effect.
    Symbols without ``lookback + 1`` prices get no score.
    """
    if len(prices) <= lookback:
        return pd.Series(dtype=float)
    window = prices.iloc[-(lookback + 1):].dropna(axis=1, how="any")
    momentum = window.iloc[-(skip + 1)] / window.iloc[0] - 1.0
    volatility = log_returns(window).iloc[-vol_window:].std() * math.sqrt(TRADING_DAYS)
    return (momentum / volatility.replace(0.0, np.nan)).dropna()


def select_in_clusters(clusters: list[list], scores: pd.Series, fraction: float,
                       min_cluster_size: int = 2) -> dict:
    """Best-scoring symbols of each cluster: symbol -> cluster index.

    Keeps the top ``fraction`` of each cluster (at least one name), only names with
    a positive score, so a cluster in a downtrend gets nothing and its budget stays
    in cash. Clusters smaller than ``min_cluster_size`` are treated as outliers.
    """
    selected = {}
    for index, cluster in enumerate(clusters):
        if len(cluster) < min_cluster_size:
            continue
        ranked = scores.reindex(cluster).dropna().sort_values(ascending=False)
        ranked = ranked[ranked > 0]
        keep = max(1, math.ceil(len(cluster) * fraction))
        for symbol in ranked.index[:keep]:
            selected[symbol] = index
    return selected


def cluster_risk_weights(selected: dict, cluster_sizes: dict[int, int], volatility: pd.Series,
                         max_weight: float, gross: float = 1.0) -> dict:
    """Target weights: cluster budgets grow with sqrt(cluster size), inverse volatility inside.

    sqrt keeps a giant component from taking the whole book while still giving it
    more than a two-name cluster. Weights above ``max_weight`` are capped and the
    excess goes to the uncapped names; whatever cannot be placed stays in cash.

    :param selected: symbol -> cluster index
    :param cluster_sizes: cluster index -> number of symbols in the full cluster
    :param volatility: symbol -> annualised volatility
    """
    by_cluster: dict[int, list] = {}
    for symbol, cluster in selected.items():
        if symbol in volatility.index and volatility[symbol] > 0:
            by_cluster.setdefault(cluster, []).append(symbol)
    if not by_cluster:
        return {}

    budgets = {c: math.sqrt(cluster_sizes.get(c, len(s))) for c, s in by_cluster.items()}
    total_budget = sum(budgets.values())
    weights = {}
    for cluster, symbols in by_cluster.items():
        inverse = 1.0 / volatility[symbols]
        for symbol, w in (inverse / inverse.sum()).items():
            weights[symbol] = gross * budgets[cluster] / total_budget * w
    return cap_weights(weights, max_weight)


def cap_weights(weights: dict, max_weight: float) -> dict:
    """Caps each weight at ``max_weight``, handing the excess to uncapped names pro rata."""
    weights = dict(weights)
    capped: set = set()
    for _ in range(len(weights)):
        excess = sum(w - max_weight for w in weights.values() if w > max_weight)
        if excess <= 1e-12:
            break
        for symbol, w in weights.items():
            if w >= max_weight:
                weights[symbol] = max_weight
                capped.add(symbol)
        free = {s: w for s, w in weights.items() if s not in capped}
        free_total = sum(free.values())
        if free_total <= 0:
            break
        for symbol, w in free.items():
            weights[symbol] = w + excess * w / free_total
    return weights


def regime_scale(prices: np.ndarray, target_vol: float, trend_window: int = 200,
                 vol_window: int = 20, bear_scale: float = 0.5, max_scale: float = 1.0) -> float:
    """Gross exposure multiplier from the benchmark's trend and realised volatility.

    Volatility targeting (target / realised, capped at ``max_scale``) times
    ``bear_scale`` when the price is below its ``trend_window`` moving average.
    Returns ``max_scale`` when there is not enough history yet.
    """
    prices = np.asarray(prices, dtype=float)
    if len(prices) < max(trend_window, vol_window + 1):
        return max_scale
    returns = np.diff(np.log(prices[-(vol_window + 1):]))
    realised = returns.std(ddof=1) * math.sqrt(TRADING_DAYS)
    scale = max_scale if realised <= 0 else min(max_scale, target_vol / realised)
    if prices[-1] < prices[-trend_window:].mean():
        scale *= bear_scale
    return scale


def quantize(scale: float, step: float) -> float:
    """Rounds ``scale`` to the nearest multiple of ``step``, never below one step or above 1."""
    return min(1.0, max(step, round(scale / step) * step))
