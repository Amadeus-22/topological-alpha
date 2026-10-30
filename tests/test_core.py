import numpy as np
import pandas as pd
import pytest

import core


def _sector_prices(n_days=300, sectors=4, per_sector=6, seed=7):
    """Synthetic prices: names in the same sector share a factor, sectors are independent."""
    rng = np.random.default_rng(seed)
    columns, series = [], []
    for s in range(sectors):
        factor = rng.normal(0.0004 * (s + 1), 0.01, n_days)
        for i in range(per_sector):
            columns.append(f"S{s}_{i}")
            series.append(factor + rng.normal(0, 0.004, n_days))
    returns = np.column_stack(series)
    return pd.DataFrame(100 * np.exp(np.cumsum(returns, axis=0)), columns=columns)


def test_connected_components_merges_linked_nodes_and_sorts_by_size():
    nodes = {"a": ["X", "Y"], "b": ["Y", "Z"], "c": ["W"], "d": ["V", "U", "T", "S"]}
    links = {"a": ["b"]}
    assert core.connected_components(nodes, links) == [["S", "T", "U", "V"], ["X", "Y", "Z"], ["W"]]


def test_correlation_clusters_recover_the_sectors():
    returns = core.log_returns(_sector_prices())
    clusters = core.correlation_clusters(returns, n_clusters=4)
    assert sorted({name.split("_")[0] for name in c} == {c[0].split("_")[0]} for c in clusters) == [True] * 4
    assert sorted(len(c) for c in clusters) == [6, 6, 6, 6]


def test_momentum_scores_rank_the_uptrend_first_and_need_full_history():
    days = 260
    prices = pd.DataFrame({
        "up": np.linspace(100, 150, days) * (1 + 0.01 * np.sin(np.arange(days))),
        "down": np.linspace(100, 70, days) * (1 + 0.01 * np.sin(np.arange(days))),
    })
    scores = core.momentum_scores(prices)
    assert scores["up"] > 0 > scores["down"]
    assert core.momentum_scores(prices.iloc[:200]).empty


def test_select_in_clusters_keeps_positive_leaders_and_skips_outliers():
    clusters = [["a", "b", "c", "d"], ["e", "f"], ["g"]]
    scores = pd.Series({"a": 2.0, "b": 1.0, "c": -1.0, "d": 0.5, "e": -0.2, "f": -0.1, "g": 5.0})
    assert core.select_in_clusters(clusters, scores, fraction=0.5) == {"a": 0, "b": 0}


def test_cluster_risk_weights_budget_by_sqrt_size_and_inverse_volatility():
    selected = {"a": 0, "b": 0, "c": 1}
    sizes = {0: 16, 1: 4}
    vol = pd.Series({"a": 0.2, "b": 0.4, "c": 0.3})
    w = core.cluster_risk_weights(selected, sizes, vol, max_weight=1.0)
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["a"] + w["b"] == pytest.approx(4 / 6)
    assert w["a"] == pytest.approx(2 * w["b"])


def test_cap_weights_redistributes_excess_and_leaves_cash_when_impossible():
    w = core.cap_weights({"a": 0.6, "b": 0.3, "c": 0.1}, max_weight=0.4)
    assert max(w.values()) <= 0.4 + 1e-12
    assert sum(w.values()) == pytest.approx(1.0)
    small = core.cap_weights({"a": 0.5, "b": 0.5}, max_weight=0.05)
    assert sum(small.values()) == pytest.approx(0.10)


def test_regime_scale_targets_volatility_and_halves_below_trend():
    rng = np.random.default_rng(1)
    calm_up = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.005, 260)))
    assert core.regime_scale(calm_up, target_vol=0.15) == 1.0
    wild_down = 100 * np.exp(np.cumsum(rng.normal(-0.003, 0.03, 260)))
    scale = core.regime_scale(wild_down, target_vol=0.15)
    assert scale < 0.5 * 0.5
    assert core.regime_scale(calm_up[:50], target_vol=0.15) == 1.0


def test_mapper_clusters_returns_disjoint_groups():
    pytest.importorskip("kmapper")
    pytest.importorskip("umap")
    returns = core.log_returns(_sector_prices(per_sector=12))
    clusters = core.mapper_clusters(returns, min_samples=3)
    members = [name for c in clusters for name in c]
    assert len(members) == len(set(members))
    assert set(members) <= set(returns.columns)


def test_quantize_moves_in_steps_between_one_step_and_one():
    assert core.quantize(0.62, 0.25) == 0.5
    assert core.quantize(0.63, 0.25) == 0.75
    assert core.quantize(0.05, 0.25) == 0.25
    assert core.quantize(1.4, 0.25) == 1.0
