# topological-alpha

[![CI](https://github.com/Amadeus-22/topological-alpha/actions/workflows/ci.yml/badge.svg)](https://github.com/Amadeus-22/topological-alpha/actions/workflows/ci.yml)

A systematic equity strategy for [QuantConnect LEAN](https://github.com/QuantConnect/Lean) that clusters S&P 500 constituents with the Mapper algorithm from topological data analysis and holds the momentum leaders of each cluster. It is built on LEAN's Algorithm Framework, with the pure logic unit-tested and the whole project type-checked against the LEAN stubs in CI.

It starts from QuantConnect's research article [Portfolio Construction Using Topological Data Analysis](https://www.quantconnect.com/research/18987/portfolio-construction-using-topological-data-analysis/) by Louis Szeto. That strategy diversifies by holding every clustered name, and in a public port it trailed SPY over 2021-2026 (CAGR 10.8% vs 12.2%, Sharpe 0.33 vs 0.40) at many times SPY's turnover. This project keeps the same Mapper construction but uses the clusters to diversify a momentum selection, and adds risk and cost controls.

## Strategy

| Framework model | What it does |
| --- | --- |
| **Universe** | SPY constituents (point-in-time ETF holdings) filtered by price > $10, daily dollar volume > $25M and market cap > $10B; the 200 most liquid, refreshed monthly. |
| **Alpha** | Monthly Mapper graph on 150 days of log returns: PCA (80% of variance) then a 1-d UMAP as the lens, DBSCAN on correlation distance inside each cover interval. Each connected component is a cluster; names DBSCAN marks as noise are left out. Inside each cluster, the names with the best positive 12-1 month momentum per unit of volatility get an Up insight. If Mapper finds too few clusters, or the universe is too small, it falls back to average-linkage correlation clusters. |
| **Portfolio construction** | Cluster budgets proportional to the square root of cluster size, inverse volatility inside each cluster, at most 5% per name. Rebalances only when insights change. |
| **Risk management** | Scales the whole book by a 15% volatility target on SPY (63-day realised volatility) and halves it when SPY is below its 200-day average. Evaluated weekly, in steps of 0.25, so noise does not resize the book. |
| **Execution** | Market orders, skipping adjustments smaller than 0.5% of equity. Interactive Brokers fee model plus 5 bps slippage on every fill. |

## Results

QuantConnect cloud backtest, 2015-01-01 to 2025-09-30, $1,000,000, daily data.

| | Initial version |
| --- | --- |
| CAGR | 9.17% |
| Sharpe ratio | 0.44 |
| Max drawdown | 18.2% |
| Annual volatility | 10.1% |
| Beta / Alpha | 0.51 / 0.004 |
| Information ratio | -0.35 |
| Orders / fees | 16,593 / $29,649 |

The initial version is a lower-risk portfolio than SPY, with half the beta and a much smaller drawdown than SPY's 2020 fall, but it shows no meaningful alpha, and turnover was too high. Since then:

- the risk model is evaluated weekly in 0.25 steps instead of resizing the book on daily volatility moves;
- the minimum trade size went from 0.25% to 0.5% of equity.

On the local smoke test these changes cut orders by a third. A like-for-like comparison of the current version against SPY buy-and-hold and the original QuantConnect strategy, with the same period, cash and costs, is the next update to this table. The three algorithms are in this repository.

## Project layout

```
TopologicalAlpha/        LEAN project (paste into QuantConnect or push with lean-cli)
  main.py                wires the five framework models, brokerage and costs
  universe.py            Universe selection
  alpha.py               Alpha model (Mapper clusters, momentum selection)
  portfolio.py           Portfolio construction
  risk.py                Risk management
  execution.py           Execution
  core.py                pure functions: Mapper, clustering, scores, weights, regime
  config.json            parameters (all optional, defaults in main.py)
baselines/
  spy_buy_and_hold.py    SPY buy and hold, same period, cash and costs
  qc_topological_original.py   QuantConnect's original strategy, same run settings
scripts/bundle.py        joins the modules into one main.py for the QuantConnect editor
tests/                   pytest for core.py
```

The models only fetch data and call `core.py`. That keeps the strategy logic testable without LEAN.

## Running on QuantConnect

**Single file.** Run `make bundle` and paste `dist/main.py` into the `main.py` of a new Python project. CI also uploads it as an artifact on every push.

**Modules.** Create the seven files of `TopologicalAlpha/` in a project with the same names.

**lean-cli.** From a `lean init` workspace containing `TopologicalAlpha/`, run `make backtest` to push and backtest in the cloud.

Parameters such as `start`, `end`, `universe_size`, `select_fraction`, `max_weight` and `target_vol` can be changed from the project's parameters panel without editing code (see `config.json`).

## Development

```bash
make setup     # venv with numpy, pandas, scipy, scikit-learn, kmapper, umap-learn, pytest, ruff, mypy, lean
make test      # pytest
make lint      # ruff
make bundle    # build dist/main.py and type-check it against the LEAN stubs
```

CI runs ruff, pytest and a strict mypy check of the single-file build against `quantconnect-stubs`. These are the same rules the QuantConnect editor applies. A manual workflow run can also push the project and start a cloud backtest through lean-cli (needs `QC_USER_ID`, `QC_API_TOKEN` and `QC_ORGANIZATION` secrets).

## Limitations and next steps

- **Ablation:** does the Mapper clustering add value over plain correlation clusters with the same selection and sizing?
- **Robustness:** walk-forward and parameter-stability checks over `history_lookback`, `select_fraction` and `target_vol`.
- **Costs:** the cost model is a fee schedule plus constant slippage; there is no market impact model.

## Credits

The Mapper construction (PCA + UMAP lens, DBSCAN on correlation distance) and the idea of using its connected components to build a portfolio come from Louis Szeto's QuantConnect research article linked above. The original code is reproduced in `baselines/` for comparison.

## Disclaimer

This is research code. Backtests are not indicative of future results, and nothing here is investment advice.

## License

[Apache-2.0](LICENSE), the same license as LEAN.
