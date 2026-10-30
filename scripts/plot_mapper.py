"""Draws the README figure: the Mapper graph the strategy builds, on synthetic factor data.

Each stock's returns are a sector factor plus its own noise, with a few stocks
driven by noise alone. The graph is built by core.mapper_graph, the same code
the alpha model runs; colours mark the connected components that become
portfolio clusters.

    python scripts/plot_mapper.py   # writes docs/mapper-graph-{light,dark}.png
"""
import sys
from pathlib import Path

import matplotlib
import networkx as nx
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "TopologicalAlpha"))
sys.modules.setdefault("AlgorithmImports", type(sys)("AlgorithmImports"))
import core  # noqa: E402

# reference palette, categorical slots 1-3 (validated all-pairs in both modes) and text/surface tokens
THEMES = {
    "light": dict(surface="#fcfcfb", primary="#0b0b0b", secondary="#52514e", muted="#c9c8c2",
                  series=["#2a78d6", "#eb6834", "#1baf7a"], other="#9a9992"),
    "dark": dict(surface="#1a1a19", primary="#f0efec", secondary="#c3c2b7", muted="#4a4945",
                 series=["#3987e5", "#d95926", "#199e70"], other="#8a8981"),
}


def synthetic_returns(sectors: int = 3, per_sector: int = 26, loners: int = 6, days: int = 150,
                      seed: int = 7) -> pd.DataFrame:
    """Returns = sector factor (with a stock-specific beta) + own noise; ``loners`` stocks are noise only."""
    rng = np.random.default_rng(seed)
    columns, series = [], []
    for s in range(sectors):
        factor = rng.normal(0, 0.012, days)
        for i in range(per_sector):
            columns.append(f"S{s}_{i:02d}")
            series.append(factor * rng.uniform(0.6, 1.4) + rng.normal(0, 0.008, days))
    for i in range(loners):
        columns.append(f"X_{i}")
        series.append(rng.normal(0, 0.015, days))
    return pd.DataFrame(np.column_stack(series), columns=columns)


def layout(graph: nx.Graph, components: list[set]) -> dict:
    """Spring layout per component, components side by side, largest first."""
    positions, x = {}, 0.0
    for component in components:
        sub = graph.subgraph(component)
        pos = nx.kamada_kawai_layout(sub) if len(sub) > 2 else nx.spring_layout(sub, seed=3)
        coords = np.array(list(pos.values()))
        span = np.ptp(coords, axis=0)
        scale = 1.0 / max(span.max(), 1e-9)
        for node, (px, py) in pos.items():
            positions[node] = (x + (px - coords[:, 0].min()) * scale, (py - coords[:, 1].mean()) * scale)
        x += span[0] * scale + 0.6
    return positions


def outlier_note(outliers: list[str]) -> str:
    loners = sum(o.startswith("X_") for o in outliers)
    if loners == len(outliers):
        return f"The {loners} stocks with no sector factor fall in no node (DBSCAN noise) and are left out."
    return (f"{len(outliers)} stocks fall in no node (DBSCAN noise) and are left out, "
            f"{loners} of them with no sector factor.")


def draw(theme: str, returns: pd.DataFrame, out: Path) -> None:
    t = THEMES[theme]
    nodes, links = core.mapper_graph(returns, n_cubes=20, overlap=0.5, min_samples=3)
    graph = nx.Graph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from((a, b) for a, linked in links.items() for b in linked)
    components = sorted(nx.connected_components(graph), key=len, reverse=True)
    positions = layout(graph, components)
    clustered = {s for members in nodes.values() for s in members}
    outliers = [c for c in returns.columns if c not in clustered]

    fig, ax = plt.subplots(figsize=(12, 5.6), dpi=200)
    fig.patch.set_facecolor(t["surface"])
    ax.set_facecolor(t["surface"])
    ax.axis("off")

    nx.draw_networkx_edges(graph, positions, ax=ax, edge_color=t["muted"], width=1.5)
    for index, component in enumerate(components):
        colour = t["series"][index] if index < len(t["series"]) else t["other"]
        members = sorted({s for node in component for s in nodes[node]})
        sizes = [60 + 22 * len(nodes[node]) for node in component]
        nx.draw_networkx_nodes(graph, positions, nodelist=list(component), ax=ax, node_color=colour,
                               node_size=sizes, edgecolors=t["surface"], linewidths=2)
        xs = [positions[n][0] for n in component]
        ys = [positions[n][1] for n in component]
        label = f"Cluster {index + 1} · {len(members)} stocks" if index < 3 else f"{len(members)} stocks"
        ax.text(np.mean(xs), max(ys) + 0.14, label, ha="center", va="bottom",
                color=t["primary"], fontsize=11, fontweight="semibold")

    fig.text(0.04, 0.93, "The Mapper graph behind the portfolio clusters", color=t["primary"],
             fontsize=15, fontweight="bold", ha="left")
    fig.text(0.04, 0.875,
             "Each node is a group of stocks that move together; linked nodes share stocks. "
             "Each connected component becomes one cluster.",
             color=t["secondary"], fontsize=10.5, ha="left")
    fig.text(0.04, 0.05,
             f"Synthetic data: {len(returns.columns)} stocks, 3 sector factors with stock-specific betas plus noise. "
             + outlier_note(outliers),
             color=t["secondary"], fontsize=9.5, ha="left")
    ax.margins(x=0.04, y=0.18)
    fig.subplots_adjust(left=0.03, right=0.97, top=0.82, bottom=0.11)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=t["surface"])
    plt.close(fig)
    print(out)


if __name__ == "__main__":
    np.random.seed(0)
    data = synthetic_returns()
    for name in THEMES:
        draw(name, data, ROOT / "docs" / f"mapper-graph-{name}.png")
