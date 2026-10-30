# region imports
from AlgorithmImports import *
from datetime import timedelta
from importlib.util import find_spec
from typing import Any
import pandas as pd
import core
# endregion

# Mapper's cover and DBSCAN need enough points per interval; below this, cluster by correlation
MIN_MAPPER_SYMBOLS = 20


class ClusterState:
    """What the alpha model learned at the last recalibration, read by portfolio construction."""

    def __init__(self) -> None:
        self.cluster_of: dict[Symbol, int] = {}
        self.cluster_sizes: dict[int, int] = {}
        self.method = ""


class TopologicalMomentumAlpha(AlphaModel):
    """Clusters the universe with the Mapper graph, then picks momentum leaders per cluster.

    Once a month: Mapper on ``lookback`` days of log returns gives the clusters
    (correlation clusters if Mapper finds fewer than ``min_clusters``, the
    universe is under 20 names or its libraries are missing); inside each cluster the names with the best positive
    12-1 risk-adjusted momentum get an Up insight. Names dropped since the last
    recalibration get a Flat insight so they are closed at the same rebalance.
    """

    def __init__(self, state: ClusterState, lookback: int, min_universe: int, select_fraction: float,
                 min_clusters: int, fallback_clusters: int, n_cubes: int, overlap: float) -> None:
        self._state = state
        self._lookback = lookback
        self._min_universe = min_universe
        self._select_fraction = select_fraction
        self._min_clusters = min_clusters
        self._fallback_clusters = fallback_clusters
        self._n_cubes = n_cubes
        self._overlap = overlap
        self._symbols: set[Symbol] = set()
        self._held: set[Symbol] = set()
        self._month = -1
        self._mapper_available = all(find_spec(m) for m in ("kmapper", "umap", "sklearn"))

    def update(self, algorithm: QCAlgorithm, data: Slice) -> list[Insight]:
        if algorithm.time.month == self._month or len(self._symbols) < self._min_universe:
            return []
        self._month = algorithm.time.month

        history = algorithm.history(list(self._symbols), max(self._lookback, 252) + 1, Resolution.DAILY)
        if history.empty:
            return []
        prices = history["close"].unstack(level=0)
        returns = core.log_returns(prices.iloc[-(self._lookback + 1):])
        clusters, method = self._clusters(algorithm, returns)
        selected = core.select_in_clusters(clusters, core.momentum_scores(prices), self._select_fraction)

        self._state.cluster_of = selected
        self._state.cluster_sizes = {i: len(c) for i, c in enumerate(clusters)}
        self._state.method = method
        algorithm.log(f"{algorithm.time:%Y-%m-%d} {method}: {len(clusters)} clusters, "
                      f"{len(selected)} selected of {returns.shape[1]}")

        period = timedelta(days=40)
        insights = [Insight.price(symbol, period, InsightDirection.UP) for symbol in selected]
        insights += [Insight.price(symbol, timedelta(days=1), InsightDirection.FLAT)
                     for symbol in self._held - set(selected)]
        self._held = set(selected)
        return insights

    def _clusters(self, algorithm: QCAlgorithm, returns: pd.DataFrame) -> tuple[list[list[Any]], str]:
        if self._mapper_available and returns.shape[1] >= MIN_MAPPER_SYMBOLS:
            clusters = core.mapper_clusters(returns, n_cubes=self._n_cubes, overlap=self._overlap)
            if sum(len(c) >= 2 for c in clusters) >= self._min_clusters:
                return clusters, "mapper"
        return core.correlation_clusters(returns, self._fallback_clusters), "correlation"

    def on_securities_changed(self, algorithm: QCAlgorithm, changes: SecurityChanges) -> None:
        for security in changes.added_securities:
            if security.type == SecurityType.EQUITY and security.symbol.value != "SPY":
                self._symbols.add(security.symbol)
        for security in changes.removed_securities:
            self._symbols.discard(security.symbol)
