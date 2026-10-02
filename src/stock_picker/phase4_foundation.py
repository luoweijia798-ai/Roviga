from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from .data_audit import RealMarketDataAuditor
from .analytics import BacktestAnalysis, analyze_backtest
from .backtest import BacktestConfig, BacktestResult, EventDrivenBacktester
from .real_market import (
    PHASE4_START,
    AkShareAdapter,
    DataManifest,
    SQLiteMarketCache,
    TushareAdapter,
)
from .reporting import BacktestReportWriter
from .sync_monitor import Phase4SyncMonitor


DEFAULT_CACHE = Path("data/a_share_201506_present.sqlite")
DEFAULT_REPORT = Path("phase4_real_market_report/foundation")
DEFAULT_AUDIT = Path("phase4_data_audit_report")
DEFAULT_SYNC_STATUS = Path("phase4_sync_status.json")


class DataCoverageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Phase4FoundationResult:
    manifest: DataManifest
    coverage: dict[str, object]
    backtest: BacktestResult
    analysis: BacktestAnalysis
    report_directory: Path


class Phase4FoundationRunner:
    """Runs the unchanged selector/risk stack on the real-market SQLite cache."""

    def __init__(
        self,
        cache_path: str | Path = DEFAULT_CACHE,
        *,
        backtest_config: BacktestConfig | None = None,
    ) -> None:
        self.cache = SQLiteMarketCache(cache_path)
        self.backtest_config = backtest_config or BacktestConfig()

    def run(
        self,
        *,
        end_date: date | None = None,
        report_directory: str | Path = DEFAULT_REPORT,
    ) -> Phase4FoundationResult:
        end_date = end_date or date.today()
        manifest = self.cache.load_manifest()
        if manifest is None:
            raise DataCoverageError("real-market cache has no completed sync manifest")
        audit = self.cache.load_audit()
        if audit is None or not audit.get("passed"):
            raise DataCoverageError(
                "real-market data audit has not passed; run the audit command first"
            )
        if audit.get("manifest_fetched_at") != manifest.fetched_at:
            raise DataCoverageError(
                "data changed after the last passing audit; run the audit again"
            )
        if audit.get("data_revision") != self.cache.data_revision:
            raise DataCoverageError("audit is stale; data revision does not match")
        if audit.get("requested_start", "9999-12-31") > PHASE4_START.isoformat():
            raise DataCoverageError("passing audit does not cover the required start date")
        if audit.get("requested_end", "") < end_date.isoformat():
            raise DataCoverageError("passing audit does not cover the requested end date")
        coverage = self.cache.coverage()
        start = coverage["start_date"]
        finish = coverage["end_date"]
        if start is None or finish is None:
            raise DataCoverageError("real-market cache contains no daily bars")
        if start > PHASE4_START:
            raise DataCoverageError(
                f"cache starts at {start}; required start is {PHASE4_START}"
            )
        if manifest.end_date < end_date:
            raise DataCoverageError(
                f"cache manifest ends at {manifest.end_date}; requested {end_date}"
            )
        failed_warning = next(
            (item for item in manifest.warnings if item.startswith("failed symbols")),
            None,
        )
        if failed_warning is not None:
            raise DataCoverageError(
                "cache sync is incomplete; resolve provider failures before "
                f"using results: {failed_warning}"
            )
        data = self.cache.as_historical_data()
        missing_benchmarks = {"CSI300", "CSI1000"} - set(data.benchmark_names)
        if missing_benchmarks:
            raise DataCoverageError(
                f"cache is missing benchmarks: {sorted(missing_benchmarks)}"
            )
        result = EventDrivenBacktester(data, self.backtest_config).run(
            PHASE4_START, end_date
        )
        analysis = analyze_backtest(result)
        output = BacktestReportWriter().write(
            result, report_directory, analysis
        )
        self._write_data_audit(output, manifest, coverage)
        return Phase4FoundationResult(
            manifest, coverage, result, analysis, output
        )

    @staticmethod
    def _write_data_audit(
        output: Path, manifest: DataManifest, coverage: dict[str, object]
    ) -> None:
        manifest_payload = asdict(manifest)
        manifest_payload["start_date"] = manifest.start_date.isoformat()
        manifest_payload["end_date"] = manifest.end_date.isoformat()
        manifest_payload["warnings"] = list(manifest.warnings)
        coverage_payload = {
            key: value.isoformat() if isinstance(value, date) else value
            for key, value in coverage.items()
        }
        (output / "data_manifest.json").write_text(
            json.dumps(manifest_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (output / "data_coverage.json").write_text(
            json.dumps(coverage_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 4 real A-share data sync and foundation backtest"
    )
    parser.add_argument(
        "command", choices=("sync", "status", "monitor", "audit", "backtest")
    )
    parser.add_argument("--provider", choices=("akshare", "tushare"), default="akshare")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--status-output", type=Path, default=DEFAULT_SYNC_STATUS)
    parser.add_argument("--symbol-limit", type=int)
    parser.add_argument(
        "--history-source", choices=("auto", "sina"), default="auto"
    )
    parser.add_argument("--skip-classifications", action="store_true")
    parser.add_argument("--request-interval", type=float, default=0.25)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--retry-delay", type=float, default=1.0)
    parser.add_argument("--segment-days", type=int, default=366)
    args = parser.parse_args()

    cache = SQLiteMarketCache(args.cache)
    if args.command == "sync":
        adapter = (
            AkShareAdapter(
                symbol_limit=args.symbol_limit,
                include_classifications=not args.skip_classifications,
                history_source=args.history_source,
                request_interval=args.request_interval,
                max_attempts=args.max_attempts,
                retry_delay=args.retry_delay,
                segment_days=args.segment_days,
            )
            if args.provider == "akshare"
            else TushareAdapter()
        )
        manifest = adapter.sync(cache, PHASE4_START, args.end)
        print(json.dumps(_display_manifest(manifest), indent=2, ensure_ascii=False))
    elif args.command == "status":
        manifest = cache.load_manifest()
        payload = {
            "manifest": _display_manifest(manifest) if manifest else None,
            "coverage": {
                key: value.isoformat() if isinstance(value, date) else value
                for key, value in cache.coverage().items()
            },
            "sync_status": {
                "complete": sum(
                    item.status == "complete" for item in cache.sync_statuses()
                ),
                "incomplete": [
                    item.symbol for item in cache.sync_statuses()
                    if item.status != "complete"
                ],
            },
            "audit": cache.load_audit(),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif args.command == "monitor":
        payload, _ = Phase4SyncMonitor(cache).refresh(
            end_date=args.end,
            status_output=args.status_output,
            audit_output=args.audit_output,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif args.command == "audit":
        result = RealMarketDataAuditor(cache).run(
            start_date=PHASE4_START,
            end_date=args.end,
            output=args.audit_output,
        )
        print(json.dumps(result.payload, indent=2, ensure_ascii=False))
        if not result.passed:
            raise SystemExit(2)
    else:
        result = Phase4FoundationRunner(args.cache).run(
            end_date=args.end, report_directory=args.report
        )
        print(
            f"real-market foundation backtest {result.backtest.start_date}.."
            f"{result.backtest.end_date} trades={result.analysis.summary.total_trades} "
            f"return={result.analysis.summary.total_return:.2%} "
            f"max_dd={result.analysis.summary.maximum_drawdown:.2%}"
        )
        print(f"report={result.report_directory.resolve()}")


def _display_manifest(manifest: DataManifest) -> dict[str, object]:
    payload = asdict(manifest)
    payload["start_date"] = manifest.start_date.isoformat()
    payload["end_date"] = manifest.end_date.isoformat()
    payload["warnings"] = list(manifest.warnings)
    return payload


if __name__ == "__main__":
    main()
