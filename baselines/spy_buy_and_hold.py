# region imports
from AlgorithmImports import *
# endregion


class SlippageSecurityInitializer(BrokerageModelSecurityInitializer):
    """Same cost model as the strategy: IBKR fees plus a constant slippage."""

    def __init__(self, brokerage_model: IBrokerageModel, seeder: ISecuritySeeder, slippage: float) -> None:
        super().__init__(brokerage_model, seeder)
        self._slippage = slippage

    def initialize(self, security: Security) -> None:
        super().initialize(security)
        security.set_slippage_model(ConstantSlippageModel(self._slippage))


class SpyBuyAndHold(QCAlgorithm):
    """Baseline: all in SPY on the first day, same period, cash and costs as the strategy."""

    def initialize(self) -> None:
        self.set_start_date(*self._date("start", "2015-01-01"))
        self.set_end_date(*self._date("end", "2025-09-30"))
        self.set_cash(1_000_000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_security_initializer(SlippageSecurityInitializer(
            self.brokerage_model, FuncSecuritySeeder(self.get_last_known_prices), 0.0005))
        self.settings.free_portfolio_value_percentage = 0.02
        self._spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark(self._spy)

    def on_data(self, data: Slice) -> None:
        if not self.portfolio.invested:
            self.set_holdings(self._spy, 1.0)

    def _date(self, name: str, default: str) -> tuple[int, int, int]:
        year, month, day = (int(part) for part in self.get_parameter(name, default).split("-"))
        return year, month, day
