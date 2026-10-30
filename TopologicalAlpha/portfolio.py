# region imports
from AlgorithmImports import *
import core
from alpha import ClusterState
# endregion


class ClusterRiskPortfolioConstructionModel(PortfolioConstructionModel):
    """Cluster budgets proportional to sqrt(cluster size), inverse volatility inside each cluster.

    Long only, fully invested before risk management, no name above ``max_weight``.
    Rebalances when the insights change (once a month), not on universe changes.
    """

    def __init__(self, state: ClusterState, max_weight: float, vol_window: int = 63) -> None:
        # no time-based rebalancing: only new or expired insights rebalance the book
        super().__init__(lambda time: None)
        self._state = state
        self._max_weight = max_weight
        self._vol_window = vol_window
        self._algorithm = None

    def determine_target_percent(self, active_insights: list[Insight]) -> dict[Insight, float]:
        long = [i for i in active_insights if i.direction == InsightDirection.UP]
        targets = {insight: 0.0 for insight in active_insights}
        if not long or self._algorithm is None:
            return targets

        symbols = [i.symbol for i in long]
        history = self._algorithm.history(symbols, self._vol_window + 1, Resolution.DAILY)
        if history.empty:
            return targets
        volatility = core.log_returns(history["close"].unstack(level=0)).std() * (core.TRADING_DAYS ** 0.5)
        selected = {s: self._state.cluster_of.get(s, -1) for s in symbols}
        weights = core.cluster_risk_weights(selected, self._state.cluster_sizes, volatility, self._max_weight)
        for insight in long:
            targets[insight] = weights.get(insight.symbol, 0.0)
        return targets

    def on_securities_changed(self, algorithm: QCAlgorithm, changes: SecurityChanges) -> None:
        self._algorithm = algorithm
        super().on_securities_changed(algorithm, changes)
