from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from stock_picker import (
    ExecutionConfig,
    JsonLinesTradeLedger,
    OrderRejected,
    PaperAccount,
    PaperBroker,
    Side,
)


DAY = date(2026, 8, 17)


class SimulatedExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.account = PaperAccount(100_000)
        self.broker = PaperBroker(
            self.account,
            ExecutionConfig(
                commission_rate=0.001,
                stamp_tax_rate=0.002,
                slippage_rate=0.01,
            ),
        )

    def test_buy_sell_costs_t_plus_one_and_ledger(self) -> None:
        buy = self.broker.buy(
            trading_date=DAY,
            symbol="AAA",
            quantity=100,
            market_price=10,
        )

        self.assertEqual(buy.execution_price, 10.1)
        self.assertAlmostEqual(buy.commission, 1.01)
        self.assertEqual(self.account.quantity("AAA"), 100)
        with self.assertRaisesRegex(OrderRejected, r"T\+1"):
            self.broker.sell(
                trading_date=DAY,
                symbol="AAA",
                quantity=100,
                market_price=11,
            )

        sell = self.broker.sell(
            trading_date=DAY + timedelta(days=1),
            symbol="AAA",
            quantity=100,
            market_price=11,
        )

        self.assertEqual(sell.side, Side.SELL)
        self.assertGreater(sell.stamp_tax, 0)
        self.assertGreater(sell.realized_profit or 0, 0)
        self.assertEqual(self.account.quantity("AAA"), 0)
        self.assertEqual(len(self.broker.ledger.all()), 2)

    def test_limit_lock_and_insufficient_cash_reject_orders(self) -> None:
        with self.assertRaisesRegex(OrderRejected, "upper limit"):
            self.broker.buy(
                trading_date=DAY,
                symbol="AAA",
                quantity=100,
                market_price=10,
                limit_up_locked=True,
            )
        with self.assertRaisesRegex(OrderRejected, "insufficient cash"):
            self.broker.buy(
                trading_date=DAY,
                symbol="AAA",
                quantity=100_000,
                market_price=10,
            )

    def test_lower_limit_blocks_a_sell(self) -> None:
        self.broker.buy(
            trading_date=DAY,
            symbol="AAA",
            quantity=100,
            market_price=10,
        )
        with self.assertRaisesRegex(OrderRejected, "lower limit"):
            self.broker.sell(
                trading_date=DAY + timedelta(days=1),
                symbol="AAA",
                quantity=100,
                market_price=9,
                limit_down_locked=True,
            )

    def test_json_lines_ledger_persists_and_reloads_trades(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trades.jsonl"
            ledger = JsonLinesTradeLedger(path)
            broker = PaperBroker(PaperAccount(10_000), ledger=ledger)
            broker.buy(
                trading_date=DAY,
                symbol="AAA",
                quantity=10,
                market_price=10,
            )

            reloaded = JsonLinesTradeLedger(path)

            self.assertEqual(len(reloaded.all()), 1)
            self.assertEqual(reloaded.all()[0].symbol, "AAA")


if __name__ == "__main__":
    unittest.main()
