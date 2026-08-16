from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Protocol

from .risk import RiskManager


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderRejected(RuntimeError):
    """Raised when a paper order cannot legally or financially execute."""


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.001
    slippage_rate: float = 0.0005

    def __post_init__(self) -> None:
        if any(
            value < 0
            for value in (
                self.commission_rate,
                self.stamp_tax_rate,
                self.slippage_rate,
            )
        ):
            raise ValueError("execution cost rates cannot be negative")


@dataclass(frozen=True, slots=True)
class Trade:
    trading_date: date
    symbol: str
    side: Side
    quantity: int
    market_price: float
    execution_price: float
    gross_amount: float
    commission: float
    stamp_tax: float
    slippage_cost: float
    cash_change: float
    realized_profit: float | None = None


class TradeLedger(Protocol):
    def append(self, trade: Trade) -> None: ...

    def all(self) -> tuple[Trade, ...]: ...


class InMemoryTradeLedger:
    def __init__(self) -> None:
        self._trades: list[Trade] = []

    def append(self, trade: Trade) -> None:
        self._trades.append(trade)

    def all(self) -> tuple[Trade, ...]:
        return tuple(self._trades)


class JsonLinesTradeLedger(InMemoryTradeLedger):
    """Append-only portable trade storage; existing records are loaded on start."""

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self.path = Path(path)
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                row["trading_date"] = date.fromisoformat(row["trading_date"])
                row["side"] = Side(row["side"])
                self._trades.append(Trade(**row))

    def append(self, trade: Trade) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = asdict(trade)
        row["trading_date"] = trade.trading_date.isoformat()
        row["side"] = trade.side.value
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        super().append(trade)


@dataclass(slots=True)
class _Lot:
    quantity: int
    unit_cost: float
    acquired_on: date


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    quantity: int
    average_cost: float
    market_value: float


class PaperAccount:
    def __init__(self, initial_cash: float = 1_000_000.0) -> None:
        if initial_cash <= 0:
            raise ValueError("initial cash must be positive")
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.realized_profit = 0.0
        self._lots: dict[str, list[_Lot]] = {}

    def quantity(self, symbol: str) -> int:
        return sum(lot.quantity for lot in self._lots.get(symbol, ()))

    def available_to_sell(self, symbol: str, trading_date: date) -> int:
        return sum(
            lot.quantity
            for lot in self._lots.get(symbol, ())
            if lot.acquired_on < trading_date
        )

    def position(self, symbol: str, market_price: float | None = None) -> Position:
        lots = self._lots.get(symbol, ())
        quantity = sum(lot.quantity for lot in lots)
        total_cost = sum(lot.quantity * lot.unit_cost for lot in lots)
        average_cost = total_cost / quantity if quantity else 0.0
        price = average_cost if market_price is None else market_price
        return Position(symbol, quantity, average_cost, quantity * price)

    def positions(self, market_prices: dict[str, float] | None = None) -> tuple[Position, ...]:
        prices = market_prices or {}
        return tuple(
            self.position(symbol, prices.get(symbol))
            for symbol in sorted(self._lots)
            if self.quantity(symbol) > 0
        )

    def exposure(self, market_prices: dict[str, float] | None = None) -> float:
        return sum(position.market_value for position in self.positions(market_prices))

    def equity(self, market_prices: dict[str, float] | None = None) -> float:
        return self.cash + self.exposure(market_prices)


class PaperBroker:
    def __init__(
        self,
        account: PaperAccount,
        config: ExecutionConfig | None = None,
        ledger: TradeLedger | None = None,
        risk_manager: RiskManager | None = None,
    ) -> None:
        self.account = account
        self.config = config or ExecutionConfig()
        self.ledger = ledger or InMemoryTradeLedger()
        self.risk_manager = risk_manager

    def buy(
        self,
        *,
        trading_date: date,
        symbol: str,
        quantity: int,
        market_price: float,
        limit_up_locked: bool = False,
    ) -> Trade:
        self._validate_order(symbol, quantity, market_price)
        if limit_up_locked:
            raise OrderRejected("buy rejected: stock is locked at the upper limit")
        execution_price = market_price * (1 + self.config.slippage_rate)
        gross = execution_price * quantity
        commission = gross * self.config.commission_rate
        total_cost = gross + commission
        if total_cost > self.account.cash + 1e-9:
            raise OrderRejected("buy rejected: insufficient cash after costs")

        self.account.cash -= total_cost
        self.account._lots.setdefault(symbol, []).append(
            _Lot(quantity, total_cost / quantity, trading_date)
        )
        trade = Trade(
            trading_date=trading_date,
            symbol=symbol,
            side=Side.BUY,
            quantity=quantity,
            market_price=market_price,
            execution_price=execution_price,
            gross_amount=gross,
            commission=commission,
            stamp_tax=0.0,
            slippage_cost=(execution_price - market_price) * quantity,
            cash_change=-total_cost,
        )
        self.ledger.append(trade)
        return trade

    def sell(
        self,
        *,
        trading_date: date,
        symbol: str,
        quantity: int,
        market_price: float,
        limit_down_locked: bool = False,
    ) -> Trade:
        self._validate_order(symbol, quantity, market_price)
        if limit_down_locked:
            raise OrderRejected("sell rejected: stock is locked at the lower limit")
        if quantity > self.account.available_to_sell(symbol, trading_date):
            raise OrderRejected("sell rejected: T+1 quantity is insufficient")

        execution_price = market_price * (1 - self.config.slippage_rate)
        gross = execution_price * quantity
        commission = gross * self.config.commission_rate
        stamp_tax = gross * self.config.stamp_tax_rate
        proceeds = gross - commission - stamp_tax
        cost_basis = self._consume_fifo_lots(symbol, quantity, trading_date)
        realized_profit = proceeds - cost_basis
        self.account.cash += proceeds
        self.account.realized_profit += realized_profit
        trade = Trade(
            trading_date=trading_date,
            symbol=symbol,
            side=Side.SELL,
            quantity=quantity,
            market_price=market_price,
            execution_price=execution_price,
            gross_amount=gross,
            commission=commission,
            stamp_tax=stamp_tax,
            slippage_cost=(market_price - execution_price) * quantity,
            cash_change=proceeds,
            realized_profit=realized_profit,
        )
        self.ledger.append(trade)
        if self.risk_manager is not None:
            self.risk_manager.record_trade_result(realized_profit)
        return trade

    def _consume_fifo_lots(
        self, symbol: str, quantity: int, trading_date: date
    ) -> float:
        remaining = quantity
        cost_basis = 0.0
        lots = self.account._lots.get(symbol, [])
        for lot in lots:
            if remaining == 0:
                break
            if lot.acquired_on >= trading_date or lot.quantity == 0:
                continue
            consumed = min(lot.quantity, remaining)
            lot.quantity -= consumed
            remaining -= consumed
            cost_basis += consumed * lot.unit_cost
        self.account._lots[symbol] = [lot for lot in lots if lot.quantity > 0]
        return cost_basis

    @staticmethod
    def _validate_order(symbol: str, quantity: int, market_price: float) -> None:
        if not symbol.strip():
            raise ValueError("symbol cannot be blank")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if market_price <= 0:
            raise ValueError("market price must be positive")
