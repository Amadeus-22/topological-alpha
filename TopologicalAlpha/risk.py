# region imports
from AlgorithmImports import *
import core
# endregion


class RegimeRiskManagementModel(RiskManagementModel):
    """Scales the whole book by SPY's volatility target and trend filter.

    The scale is recomputed once a week and moves in steps of ``step`` (0.25 by
    default), so day-to-day noise in SPY's volatility does not resize the book.
    New targets from portfolio construction are scaled before they reach
    execution; when the stepped scale changes between rebalances, current
    holdings are resized once.
    """

    def __init__(self, benchmark: Symbol, target_vol: float, bear_scale: float,
                 vol_window: int = 63, step: float = 0.25) -> None:
        self._benchmark = benchmark
        self._target_vol = target_vol
        self._bear_scale = bear_scale
        self._vol_window = vol_window
        self._step = step
        self._scale = 1.0
        self._applied = 1.0
        self._week: tuple[int, int] | None = None

    def manage_risk(self, algorithm: QCAlgorithm, targets: list[IPortfolioTarget]) -> list[IPortfolioTarget]:
        week = algorithm.time.isocalendar()[:2]
        if week != self._week:
            self._week = week
            history = algorithm.history(self._benchmark, 252, Resolution.DAILY)
            if not history.empty:
                raw = core.regime_scale(history["close"].values, self._target_vol,
                                        vol_window=self._vol_window, bear_scale=self._bear_scale)
                self._scale = core.quantize(raw, self._step)

        adjusted: list[IPortfolioTarget] = []
        if targets:
            # a rebalance resizes the book at the current scale; closing targets alone don't
            if any(t.quantity != 0 for t in targets):
                self._applied = self._scale
            adjusted.extend(PortfolioTarget(t.symbol, int(t.quantity * self._scale)) for t in targets)
            return adjusted

        if self._scale == self._applied or self._applied == 0:
            return adjusted
        ratio = self._scale / self._applied
        self._applied = self._scale
        algorithm.log(f"{algorithm.time:%Y-%m-%d} regime scale -> {self._scale:.2f}")
        adjusted.extend(PortfolioTarget(h.symbol, int(h.quantity * ratio))
                        for h in algorithm.portfolio.values() if h.invested)
        return adjusted
