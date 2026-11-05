from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from traderbot.risk.manager import RiskVerdict


@dataclass(frozen=True, slots=True)
class PairRiskLimits:
    """Pair-specific risk limits for statistical arbitrage."""

    max_pair_allocation_pct: float = 0.20  # Max 20% of total equity per pair
    max_gross_pair_exposure: float = 1_000_000.0  # Max gross USD notional per pair
    max_net_exposure_pct: float = 0.15  # Max 15% net residual dollar exposure (|net| / gross)
    max_leverage: float = 3.0  # Max gross / allocated equity
    max_hedge_deviation_pct: float = 0.10  # Max 10% drift from theoretical hedge ratio
    max_holding_duration_bars: int = 120  # Maximum bars to hold an un-reverted pair
    max_pair_loss_pct: float = 3.0  # Stop loss at 3% loss on allocated equity
    max_spread_divergence_z: float = 4.0  # Stop out if spread z-score diverges beyond +/-4.0
    max_adverse_funding_apr: float = 0.25  # 25% APR net adverse carry ceiling
    max_spread_vol_expansion: float = 2.0  # Stop if current spread std expands > 2x entry std


@dataclass(slots=True)
class PairRiskState:
    """Live state tracking for an open or pending statistical arbitrage pair."""

    pair_id: str
    symbol_a: str
    symbol_b: str
    leg_a_qty: float = 0.0
    leg_b_qty: float = 0.0
    entry_price_a: float = 0.0
    entry_price_b: float = 0.0
    current_price_a: float = 0.0
    current_price_b: float = 0.0
    hedge_ratio: float = 1.0
    allocated_capital: float = 0.0
    entry_spread: float = 0.0
    current_spread: float = 0.0
    current_z_score: float = 0.0
    entry_bar_index: int = 0
    holding_bars: int = 0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    status: str = "OPEN"  # 'OPEN', 'REDUCING', 'CLOSED', 'EMERGENCY_EXIT'
    entry_spread_std: float = 0.0
    current_spread_std: float = 0.0
    initial_half_life: float | None = None
    current_half_life: float | None = None

    @property
    def leg_a_notional(self) -> float:
        return self.leg_a_qty * self.current_price_a

    @property
    def leg_b_notional(self) -> float:
        return self.leg_b_qty * self.current_price_b

    @property
    def gross_notional(self) -> float:
        return abs(self.leg_a_notional) + abs(self.leg_b_notional)

    @property
    def net_notional(self) -> float:
        return self.leg_a_notional + self.leg_b_notional

    @property
    def effective_leverage(self) -> float:
        if self.allocated_capital <= 0:
            return 0.0
        return self.gross_notional / self.allocated_capital

    @property
    def hedge_deviation_pct(self) -> float:
        """Percentage deviation between actual notional ratio and target hedge ratio."""
        if abs(self.leg_a_notional) <= 1e-12 or self.hedge_ratio <= 1e-12:
            return 0.0
        actual_ratio = abs(self.leg_b_notional) / abs(self.leg_a_notional)
        return abs(actual_ratio - self.hedge_ratio) / self.hedge_ratio

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl

    @property
    def pair_loss_pct(self) -> float:
        if self.allocated_capital <= 0:
            return 0.0
        # Positive return -> 0 loss; negative return -> positive loss percentage
        pnl_pct = (self.total_pnl / self.allocated_capital) * 100.0
        return -pnl_pct if pnl_pct < 0 else 0.0

    def update_prices(self, price_a: float, price_b: float) -> None:
        self.current_price_a = price_a
        self.current_price_b = price_b
        # Calculate unrealized PnL: Long leg profits from price rise, Short leg profits from price drop
        upnl_a = self.leg_a_qty * (price_a - self.entry_price_a) if self.entry_price_a > 0 else 0.0
        upnl_b = self.leg_b_qty * (price_b - self.entry_price_b) if self.entry_price_b > 0 else 0.0
        self.unrealized_pnl = upnl_a + upnl_b

    def snapshot(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "symbol_a": self.symbol_a,
            "symbol_b": self.symbol_b,
            "leg_a_qty": self.leg_a_qty,
            "leg_b_qty": self.leg_b_qty,
            "entry_price_a": self.entry_price_a,
            "entry_price_b": self.entry_price_b,
            "current_price_a": self.current_price_a,
            "current_price_b": self.current_price_b,
            "hedge_ratio": self.hedge_ratio,
            "allocated_capital": self.allocated_capital,
            "entry_spread": self.entry_spread,
            "current_spread": self.current_spread,
            "current_z_score": self.current_z_score,
            "entry_bar_index": self.entry_bar_index,
            "holding_bars": self.holding_bars,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "status": self.status,
            "entry_spread_std": self.entry_spread_std,
            "current_spread_std": self.current_spread_std,
            "initial_half_life": self.initial_half_life,
            "current_half_life": self.current_half_life,
        }

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> PairRiskState:
        return cls(
            pair_id=str(data.get("pair_id", "")),
            symbol_a=str(data.get("symbol_a", "")),
            symbol_b=str(data.get("symbol_b", "")),
            leg_a_qty=float(data.get("leg_a_qty", 0.0)),
            leg_b_qty=float(data.get("leg_b_qty", 0.0)),
            entry_price_a=float(data.get("entry_price_a", 0.0)),
            entry_price_b=float(data.get("entry_price_b", 0.0)),
            current_price_a=float(data.get("current_price_a", 0.0)),
            current_price_b=float(data.get("current_price_b", 0.0)),
            hedge_ratio=float(data.get("hedge_ratio", 1.0)),
            allocated_capital=float(data.get("allocated_capital", 0.0)),
            entry_spread=float(data.get("entry_spread", 0.0)),
            current_spread=float(data.get("current_spread", 0.0)),
            current_z_score=float(data.get("current_z_score", 0.0)),
            entry_bar_index=int(data.get("entry_bar_index", 0)),
            holding_bars=int(data.get("holding_bars", 0)),
            realized_pnl=float(data.get("realized_pnl", 0.0)),
            unrealized_pnl=float(data.get("unrealized_pnl", 0.0)),
            status=str(data.get("status", "OPEN")),
            entry_spread_std=float(data.get("entry_spread_std", 0.0)),
            current_spread_std=float(data.get("current_spread_std", 0.0)),
            initial_half_life=data.get("initial_half_life"),
            current_half_life=data.get("current_half_life"),
        )


@dataclass(frozen=True, slots=True)
class PairExposureInfo:
    pair_id: str
    symbol_a: str
    symbol_b: str
    leg_a_qty: float
    leg_b_qty: float
    leg_a_notional: float
    leg_b_notional: float
    gross_notional: float
    net_notional: float
    leverage: float
    hedge_deviation_pct: float
    holding_duration_bars: int
    current_spread: float
    spread_z_score: float


@dataclass(frozen=True, slots=True)
class PortfolioExposureInfo:
    total_equity: float
    aggregate_long_notional: float
    aggregate_short_notional: float
    gross_notional: float
    net_notional: float
    margin_used: float
    available_margin: float
    margin_ratio: float
    active_pair_count: int
    open_pairs: list[str]
    shared_symbols: dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class FundingRiskEstimate:
    symbol_a: str
    symbol_b: str
    hourly_rate_a: float
    hourly_rate_b: float
    payment_a_hourly: float
    payment_b_hourly: float
    net_payment_hourly: float
    net_annualized_apr: float
    status: str
    adverse_carry_breach: bool


@dataclass(frozen=True, slots=True)
class ExecutionRiskAssessment:
    status: str
    reconciled: bool
    leg_a_fill_pct: float
    leg_b_fill_pct: float
    slippage_a_pct: float
    slippage_b_pct: float
    depth_sufficient: bool
    legging_risk_warning: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class StatArbRiskVerdict(RiskVerdict):
    """
    Unified verdict satisfying all 8 user-specified output requirements:
    1. approved / rejected (via .approved and .allowed)
    2. risk reason (via .reason)
    3. maximum allowed position (via .max_allowed_position)
    4. pair exposure (via .pair_exposure)
    5. portfolio exposure (via .portfolio_exposure)
    6. funding estimate (via .funding_estimate)
    7. execution risk (via .execution_risk)
    8. risk status (via .risk_status)
    """

    approved: bool = True
    max_allowed_position: float = 0.0
    pair_exposure: PairExposureInfo | None = None
    portfolio_exposure: PortfolioExposureInfo | None = None
    funding_estimate: FundingRiskEstimate | None = None
    execution_risk: ExecutionRiskAssessment | None = None
    risk_status: str = "NORMAL"

    def __post_init__(self) -> None:
        if not self.allowed:
            self.approved = False
        elif not self.approved:
            self.allowed = False

