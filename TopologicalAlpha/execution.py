# region imports
from AlgorithmImports import *
# endregion


class MinimumTradeExecutionModel(ExecutionModel):
    """Market orders toward the targets, skipping trades worth less than ``min_trade`` of equity.

    Small adjustments cost commissions and spread for no change in risk; closing
    a position (target quantity 0) is never skipped.
    """

    def __init__(self, min_trade: float) -> None:
        self._min_trade = min_trade
        self._targets = PortfolioTargetCollection()

    def execute(self, algorithm: QCAlgorithm, targets: list[PortfolioTarget]) -> None:
        self._targets.add_range(targets)
        if self._targets.is_empty:
            return
        threshold = algorithm.portfolio.total_portfolio_value * self._min_trade
        for target in self._targets.order_by_margin_impact(algorithm):
            security = algorithm.securities[target.symbol]
            quantity = OrderSizing.get_unordered_quantity(algorithm, target, security)
            if quantity == 0:
                continue
            if target.quantity != 0 and abs(quantity * security.price) < threshold:
                continue
            algorithm.market_order(target.symbol, quantity)
        self._targets.clear_fulfilled(algorithm)
        # skipped small trades are dropped, not retried every bar
        self._targets.clear()
