# region imports
from AlgorithmImports import *
# endregion


class SpyConstituentsUniverse:
    """SPY constituents, then liquidity, price and size filters on their fundamentals.

    Two chained universes: the ETF universe only records SPY's current members
    and subscribes to nothing; the fundamental universe keeps the members that
    pass the filters. Selection changes once a month, which bounds turnover from
    universe churn.
    """

    def __init__(self, algorithm: QCAlgorithm, etf: Symbol, size: int, min_price: float,
                 min_dollar_volume: float, min_market_cap: float) -> None:
        self._size = size
        self._min_price = min_price
        self._min_dollar_volume = min_dollar_volume
        self._min_market_cap = min_market_cap
        self._members: set[Symbol] = set()
        self._month = -1
        algorithm.add_universe(algorithm.universe.etf(etf, algorithm.universe_settings, self._record_members))
        algorithm.add_universe(self._select)

    def _record_members(self, constituents: list[ETFConstituentUniverse]) -> list[Symbol]:
        self._members = {c.symbol for c in constituents if c.weight}
        return []

    def _select(self, fundamentals: list[Fundamental]) -> list[Symbol]:
        if not self._members or fundamentals[0].end_time.month == self._month:
            return Universe.UNCHANGED
        self._month = fundamentals[0].end_time.month
        eligible = [f for f in fundamentals
                    if f.symbol in self._members
                    and f.has_fundamental_data
                    and f.price > self._min_price
                    and f.dollar_volume > self._min_dollar_volume
                    and f.market_cap > self._min_market_cap]
        eligible.sort(key=lambda f: f.dollar_volume, reverse=True)
        return [f.symbol for f in eligible[:self._size]]
