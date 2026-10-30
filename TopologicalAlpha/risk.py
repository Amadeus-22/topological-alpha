# region imports
from AlgorithmImports import *
import core
# endregion


class RegimeRiskManagementModel(RiskManagementModel):
    """Scales the whole book by SPY's volatility target and trend filter.

    The scale is recomputed once a day. New targets from portfolio construction
    are scaled before they reach execution; when the scale moves by more than
    ``threshold`` between rebalances, current holdings are resized too.
    """

    def __init__(self, benchmark: Symbol, target_vol: float, bear_scale: float, threshold: float = 0.1) -> None:
        self._benchmark = benchmark
        self._target_vol = target_vol
        self._bear_scale = bear_scale
        self._threshold = threshold
        self._scale = 1.0
        self._applied = 1.0
        self._day = None

    def manage_risk(self, algorithm: QCAlgorithm, targets: list[PortfolioTarget]) -> list[PortfolioTarget]:
        if algorithm.time.date() != self._day:
            self._day = algorithm.time.date()
            history = algorithm.history(self._benchmark, 252, Resolution.DAILY)
            if not history.empty:
                self._scale = core.regime_scale(history["close"].values, self._target_vol,
                                                bear_scale=self._bear_scale)

        if targets:
            # a rebalance resizes the book at the current scale; closing targets alone don't
            if any(t.quantity != 0 for t in targets):
                self._applied = self._scale
            return [PortfolioTarget(t.symbol, int(t.quantity * self._scale)) for t in targets]

        if abs(self._scale - self._applied) <= self._threshold or self._applied == 0:
            return []
        ratio = self._scale / self._applied
        self._applied = self._scale
        algorithm.log(f"{algorithm.time:%Y-%m-%d} regime scale -> {self._scale:.2f}")
        return [PortfolioTarget(h.symbol, int(h.quantity * ratio))
                for h in algorithm.portfolio.values() if h.invested]
