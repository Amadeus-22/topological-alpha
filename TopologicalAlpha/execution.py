# region imports
from AlgorithmImports import *
import core
# endregion


class MinimumTradeExecutionModel(ExecutionModel):
    """Market orders toward the targets, skipping small orders that would only add exposure.

    An order worth less than ``min_trade`` of equity costs commissions and spread for no
    material change in risk, so it is skipped when it adds to a position. Reductions and
    closes always go through, so the book never ends above its target exposure.
    """

    def __init__(self, min_trade: float) -> None:
        self._min_trade = min_trade
        self._targets = PortfolioTargetCollection()

    def execute(self, algorithm: QCAlgorithm, targets: list[IPortfolioTarget]) -> None:
        self._targets.add_range(targets)
        if self._targets.is_empty:
            return
        threshold = algorithm.portfolio.total_portfolio_value * self._min_trade
        for target in self._targets.order_by_margin_impact(algorithm):
            security = algorithm.securities[target.symbol]
            quantity = OrderSizing.get_unordered_quantity(algorithm, target, security)
            if quantity == 0:
                continue
            if core.skip_small_trade(quantity, security.holdings.quantity, target.quantity,
                                     security.price, threshold):
                continue
            algorithm.market_order(target.symbol, quantity)
        self._targets.clear_fulfilled(algorithm)
        # skipped small trades are dropped, not retried every bar
        self._targets.clear()
