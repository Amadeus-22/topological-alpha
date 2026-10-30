"""Baseline: QuantConnect's "Portfolio Construction Using Topological Data Analysis".

Strategy logic as published (Mapper clusters of SPY's top 200 constituents,
equal weight by cluster and node, daily rebalance, recalibration every 125
days on 150 days of returns). Only the run settings are aligned with the
strategy it is compared against: period, cash, daily data, IBKR fees and the
same constant slippage.
"""
# region imports
from AlgorithmImports import *
import kmapper as km
from sklearn.cluster import DBSCAN
from sklearn.decomposition import PCA
from umap import UMAP
# endregion
np.random.seed(0)


class TopologicalGraphUniverseSelectionModel(ETFConstituentsUniverseSelectionModel):
    def __init__(self, etf_symbol, lookback_window=250, recalibration_period=None, universe_filter_func=None):
        self._symbol = etf_symbol
        self.lookback_window = lookback_window
        self.recalibration_period = recalibration_period
        self.clustered_symbols = None
        super().__init__(etf_symbol, None, universe_filter_func)

    def create_universes(self, algorithm):
        universe_list = super().create_universes(algorithm)
        next_open = algorithm.securities[self._symbol].exchange.hours.get_next_market_open(algorithm.time, False)
        algorithm.schedule.on(algorithm.date_rules.on([next_open]), algorithm.time_rules.at(9, 31),
                              lambda: self.get_graph_symbols(algorithm))
        return universe_list

    def get_graph_symbols(self, algorithm):
        graph, symbol_list = self.construct_simplicial_complex(algorithm, self.lookback_window)
        if list(symbol_list):
            self.clustered_symbols = self.clustering_symbols(graph, symbol_list)
        next_recalibration = algorithm.time + timedelta(self.recalibration_period)
        algorithm.schedule.on(algorithm.date_rules.on([next_recalibration]), algorithm.time_rules.at(0, 1),
                              lambda: self.get_graph_symbols(algorithm))

    def construct_simplicial_complex(self, algorithm, lookback_window):
        if not self.universe.selected:
            return {}, []
        history = algorithm.history(self.universe.selected, lookback_window, Resolution.DAILY)
        if history.empty:
            return {}, []
        prices = history.unstack(0).close
        log_returns = np.log(prices / prices.shift(1)).dropna().T
        if log_returns.empty:
            return {}, []
        mapper = km.KeplerMapper()
        projection = [PCA(n_components=0.8, random_state=1), UMAP(n_components=1, random_state=1, n_jobs=-1)]
        projected_data = mapper.fit_transform(log_returns, projection=projection)
        clusterer = DBSCAN(metric='correlation', n_jobs=-1)
        graph = mapper.map(projected_data, log_returns, clusterer)
        return graph, prices.columns

    def clustering_symbols(self, graph, symbol_list):
        linked_clusters = []
        for x, y in graph['links'].items():
            isin = False
            for i in range(len(linked_clusters)):
                if x in linked_clusters[i] or y in linked_clusters[i]:
                    linked_clusters[i] = list(set(linked_clusters[i] + [x] + y))
                    isin = True
            if isin:
                continue
            linked_clusters.append([x] + y)
        linked_clusters += [[x] for x in graph['nodes'] if x not in [z for y in linked_clusters for z in y]]
        return [[list([symbol_list[graph['nodes'][x]]][0]) for x in linked_cluster]
                for linked_cluster in linked_clusters]


class SlippageSecurityInitializer(BrokerageModelSecurityInitializer):
    """Same cost model as the strategy: IBKR fees plus a constant slippage."""

    def __init__(self, brokerage_model, seeder, slippage):
        super().__init__(brokerage_model, seeder)
        self._slippage = slippage

    def initialize(self, security):
        super().initialize(security)
        security.set_slippage_model(ConstantSlippageModel(self._slippage))


class TopologicalPortfolio(QCAlgorithm):
    def initialize(self) -> None:
        year, month, day = (int(p) for p in self.get_parameter("start", "2015-01-01").split("-"))
        self.set_start_date(year, month, day)
        year, month, day = (int(p) for p in self.get_parameter("end", "2025-09-30").split("-"))
        self.set_end_date(year, month, day)
        self.set_cash(1000000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_security_initializer(SlippageSecurityInitializer(
            self.brokerage_model, FuncSecuritySeeder(self.get_last_known_prices), 0.0005))
        self.universe_settings.resolution = Resolution.DAILY

        spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark(spy)

        history_lookback = int(self.get_parameter("history_lookback", "150"))
        recalibrate_period = int(self.get_parameter("recalibrate_period", "125"))
        self.universe_model = TopologicalGraphUniverseSelectionModel(
            spy,
            history_lookback,
            recalibrate_period,
            lambda u: [x.symbol for x in sorted([x for x in u if x.weight], key=lambda x: x.weight, reverse=True)[:200]]
        )
        self.add_universe_selection(self.universe_model)
        self.schedule.on(self.date_rules.every_day(spy), self.time_rules.at(9, 31), self.rebalance)
        self.set_warm_up(timedelta(365))

    def rebalance(self) -> None:
        if self.universe_model.clustered_symbols:
            weights = self.weight_distribution(self.universe_model.clustered_symbols)
            self.set_holdings([PortfolioTarget(symbol, weight) for symbol, weight in weights.items()],
                              liquidate_existing_holdings=True)

    def weight_distribution(self, clustered_symbols):
        weights = {}

        def assign_weights(nested_list, level=1):
            num_elements = len(nested_list)
            if num_elements == 0:
                return
            weight_per_element = 1 / num_elements
            for item in nested_list:
                if isinstance(item, list):
                    assign_weights(item, level + 1)
                else:
                    weights[item] = weights.get(item, 0) + weight_per_element / (2 ** (level - 1))

        assign_weights(clustered_symbols)
        return pd.Series(weights) / sum(weights.values())
