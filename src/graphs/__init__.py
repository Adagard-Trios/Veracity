from src.graphs.veracity_graph import veracity_graph
from src.graphs.adjacent_graph import adjacent_graph
from src.graphs.competitor_graph import competitor_graph
from src.graphs.market_trend_graph import market_trend_graph
from src.graphs.pricing_graph import pricing_graph
from src.graphs.user_voice_graph import user_voice_graph

import importlib
_wlg = importlib.import_module("src.graphs.win-loss_graph")
win_loss_graph = _wlg.win_loss_graph

__all__ = [
    "veracity_graph",
    "adjacent_graph",
    "competitor_graph",
    "market_trend_graph",
    "pricing_graph",
    "user_voice_graph",
    "win_loss_graph",
]
