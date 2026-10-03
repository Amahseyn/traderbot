"""Terminal-facing live and replay execution (paper by default)."""

from traderbot.terminal.events import print_signal_event
from traderbot.terminal.trader import TerminalAlgorithmTrader

__all__ = ["TerminalAlgorithmTrader", "print_signal_event"]
