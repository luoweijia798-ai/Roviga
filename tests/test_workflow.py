from __future__ import annotations

import unittest
from datetime import date

from stock_picker import (
    DailyTracker,
    PaperAccount,
    PaperBroker,
    PaperTradingWorkflow,
    RiskManager,
    Selection,
)


DAY = date(2026, 8, 17)


class WorkflowTests(unittest.TestCase):
    def test_selected_candidate_is_sized_filled_and_tracked(self) -> None:
        account = PaperAccount(100_000)
        broker = PaperBroker(account)
        risk = RiskManager(100_000, DAY)
        tracker = DailyTracker()
        workflow = PaperTradingWorkflow(account, broker, risk, tracker)

        result = workflow.submit_candidate(
            Selection(DAY, "AAA", 0.1, 0.08, 1.0),
            entry_price=100,
            stop_price=95,
            take_profit_price=115,
        )

        self.assertEqual(result.sizing.quantity, 200)
        self.assertIsNotNone(result.trade)
        self.assertEqual(account.quantity("AAA"), 200)
        self.assertIsNotNone(tracker.get(DAY).fill)


if __name__ == "__main__":
    unittest.main()
