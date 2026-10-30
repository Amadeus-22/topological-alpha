# region imports
from AlgorithmImports import *
from alpha import ClusterState, TopologicalMomentumAlpha
from execution import MinimumTradeExecutionModel
from portfolio import ClusterRiskPortfolioConstructionModel
from risk import RegimeRiskManagementModel
from universe import SpyConstituentsUniverse
# endregion


class SlippageSecurityInitializer(BrokerageModelSecurityInitializer):
    """IBKR fees from the brokerage model plus a constant slippage on every fill."""

    def __init__(self, brokerage_model: IBrokerageModel, seeder: ISecuritySeeder, slippage: float) -> None:
        super().__init__(brokerage_model, seeder)
        self._slippage = slippage

    def initialize(self, security: Security) -> None:
        super().initialize(security)
        security.set_slippage_model(ConstantSlippageModel(self._slippage))


class TopologicalAlphaAlgorithm(QCAlgorithm):
    """SPY constituents clustered by the Mapper graph, momentum leaders per cluster.

    Universe: SPY members filtered by price, dollar volume and market cap.
    Alpha: monthly Mapper clusters, top positive 12-1 risk-adjusted momentum per cluster.
    Portfolio: sqrt(cluster size) budgets, inverse volatility inside, capped per name.
    Risk: volatility target and trend filter on SPY.
    Execution: market orders, trades below a fraction of equity are skipped.

    Based on QuantConnect's "Portfolio Construction Using Topological Data Analysis".
    """

    def initialize(self) -> None:
        self.set_start_date(*self._date("start", "2015-01-01"))
        self.set_end_date(*self._date("end", "2025-09-30"))
        self.set_cash(1_000_000)
        np.random.seed(0)

        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_security_initializer(SlippageSecurityInitializer(
            self.brokerage_model, FuncSecuritySeeder(self.get_last_known_prices),
            self._float("slippage", 0.0005)))
        self.settings.rebalance_portfolio_on_security_changes = False
        self.settings.free_portfolio_value_percentage = 0.02

        resolution = Resolution.MINUTE if self.live_mode else Resolution.DAILY
        self.universe_settings.resolution = resolution
        spy = self.add_equity("SPY", resolution).symbol
        self.set_benchmark(spy)

        # optional fixed list ("AAPL,IBM,..."), for quick research and the local smoke test
        symbols = [s.strip() for s in self.get_parameter("symbols", "").split(",") if s.strip()]
        if symbols:
            for ticker in symbols:
                self.add_equity(ticker, resolution)
        else:
            SpyConstituentsUniverse(
                self, spy,
                size=self._int("universe_size", 200),
                min_price=self._float("min_price", 10.0),
                min_dollar_volume=self._float("min_dollar_volume", 25e6),
                min_market_cap=self._float("min_market_cap", 10e9))

        state = ClusterState()
        self.add_alpha(TopologicalMomentumAlpha(
            state,
            lookback=self._int("history_lookback", 150),
            min_universe=self._int("min_universe", 20),
            select_fraction=self._float("select_fraction", 0.25),
            min_clusters=self._int("min_clusters", 3),
            fallback_clusters=self._int("fallback_clusters", 10),
            n_cubes=self._int("n_cubes", 10),
            overlap=self._float("overlap", 0.1)))
        self.set_portfolio_construction(ClusterRiskPortfolioConstructionModel(
            state, max_weight=self._float("max_weight", 0.05)))
        self.add_risk_management(RegimeRiskManagementModel(
            spy, target_vol=self._float("target_vol", 0.15), bear_scale=self._float("bear_scale", 0.5),
            vol_window=self._int("vol_window", 63), step=self._float("risk_step", 0.25)))
        self.set_execution(MinimumTradeExecutionModel(self._float("min_trade", 0.005)))

    def _int(self, name: str, default: int) -> int:
        return int(self.get_parameter(name, str(default)))

    def _float(self, name: str, default: float) -> float:
        return float(self.get_parameter(name, str(default)))

    def _date(self, name: str, default: str) -> tuple[int, int, int]:
        year, month, day = (int(part) for part in self.get_parameter(name, default).split("-"))
        return year, month, day
