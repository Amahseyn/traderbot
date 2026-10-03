from __future__ import annotations

from dataclasses import asdict, dataclass

from traderbot.algorithms.registry import list_strategies
from traderbot.market_data import RESOLUTIONS


@dataclass(frozen=True, slots=True)
class TerminalCommandEntry:
    id: str
    summary: str


TERMINAL_COMMANDS: tuple[TerminalCommandEntry, ...] = (
    TerminalCommandEntry(
        id="run",
        summary="Poll Nobitex UDF for new closed candles and step the algorithm (paper by default).",
    ),
    TerminalCommandEntry(
        id="once",
        summary="Evaluate the strategy on the latest closed candle once (smoke test).",
    ),
    TerminalCommandEntry(
        id="replay",
        summary="Walk an OHLC CSV bar-by-bar and emit signals (no API polling).",
    ),
    TerminalCommandEntry(
        id="catalog",
        summary="List terminal commands and implemented strategies.",
    ),
)


def catalog_dict(*, implemented_only: bool = False) -> dict:
    return {
        "commands": [asdict(c) for c in TERMINAL_COMMANDS],
        "strategies": [asdict(s) for s in list_strategies(implemented_only=implemented_only)],
        "execution_modes": ["paper", "live"],
        "udf_resolutions": list(RESOLUTIONS),
    }
