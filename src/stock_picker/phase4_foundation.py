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
        admission_path: str | Path | None = None,
    ) -> None:
        # Inspect a frozen input without schema initialization or switching it
        # into WAL mode. A rejected command must not mutate the candidate.
        from .phase4_acceptance import SnapshotCache
        self.cache = SnapshotCache(Path(cache_path))
        self.backtest_config = backtest_config or BacktestConfig()
        self.admission_path = Path(admission_path) if admission_path else None

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
        if audit and (audit.get("formal_gate_eligible") is False or audit.get("report_kind") == "preaudit"):
            raise DataCoverageError("preaudit/snapshot report cannot authorize a formal backtest")
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
        self._verify_formal_binding(end_date)
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
        # If another process altered an input mid-run, publish no result.
        self._verify_formal_binding(end_date)
        analysis = analyze_backtest(result)
        output = BacktestReportWriter().write(
            result, report_directory, analysis
        )
        self._write_data_audit(output, manifest, coverage)
        return Phase4FoundationResult(
            manifest, coverage, result, analysis, output
        )

    def _verify_formal_binding(self, end_date: date) -> None:
        """Strengthen the existing gate; never generate approval from a flag.

        Sidecars are produced only after actual full-market/model review. Pilot
        evidence is not eligible. This binds evidence/config/code/data identity,
        not the truth of independently missing source evidence.
        """
        import hashlib
        from .phase4_acceptance import ACCEPTANCE_END, verify_snapshot
        from .selector import SelectionConfig
        from .risk import RiskConfig
        from .trading import ExecutionConfig
        if self.admission_path is None:
            raise DataCoverageError('formal snapshot/config/code admission binding is missing')
        if end_date != ACCEPTANCE_END:
            raise DataCoverageError('first formal interval must end at 2026-09-30')
        expected_config = {'backtest': asdict(self.backtest_config),
                           'selector': asdict(SelectionConfig()),
                           'risk': asdict(RiskConfig()), 'execution': asdict(ExecutionConfig())}
        try:
            binding = json.loads(self.admission_path.read_text(encoding='utf-8'))
            if binding['schema'] != 'roviga-formal-binding-v1':
                raise ValueError('unsupported formal binding')
            if binding['formal_interval'] != [PHASE4_START.isoformat(), ACCEPTANCE_END.isoformat()]:
                raise ValueError('formal interval mismatch')
            if binding['configuration'] != expected_config:
                raise ValueError('effective configuration changed')
            expected_code = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in Path(__file__).parent.glob('*.py')}
            if binding['code_sha256'] != expected_code:
                raise ValueError('code changed since admission')
            if Path(str(self.cache.path) + '-wal').exists():
                raise ValueError('use a frozen checkpoint, not a WAL-backed sync database')
            verify_snapshot(self.cache.path, binding['snapshot'])
            if binding['snapshot']['data_revision'] != self.cache.data_revision:
                raise ValueError('snapshot revision mismatch')
            evidence = binding['evidence']
            if set(evidence) != {'full_market_admission', 'frozen_configuration', 'execution_model_validation'}:
                raise ValueError('full-market, configuration and execution evidence all required')
            for kind, ref in evidence.items():
                data = Path(ref['path']).read_bytes()
                if hashlib.sha256(data).hexdigest() != ref['sha256']:
                    raise ValueError('admission evidence changed: ' + kind)
                proof = json.loads(data)
                if kind == 'frozen_configuration':
                    if proof != expected_config: raise ValueError('frozen configuration evidence mismatch')
                elif (proof.get('snapshot', {}).get('id') != binding['snapshot']['id']
                      or proof.get('scope') != 'full_market'
                      or proof.get('formal_gate_eligible') is not True
                      or proof.get('passed') is not True or proof.get('blockers') != []):
                    raise ValueError('ineligible or blocked evidence: ' + kind)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise DataCoverageError('formal binding rejected: ' + str(error)) from error

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
        "command", choices=("sync", "status", "monitor", "audit", "backtest", "readiness")
    )
    parser.add_argument("--provider", choices=("akshare", "tushare"), default="akshare")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--status-output", type=Path, default=DEFAULT_SYNC_STATUS)
    parser.add_argument("--snapshot-identity", type=Path,
                        help="exact saved pilot identity; readiness never writes this database")
    parser.add_argument("--admission-report", type=Path,
                        help="existing layered pilot admission JSON for readiness display")
    parser.add_argument("--data-requirements", type=Path,
                        help="existing snapshot-bound missing-evidence list; readiness display only")
    parser.add_argument("--formal-binding", type=Path,
                        help="verified full-market snapshot/config/code binding; never a pilot report")
    parser.add_argument("--symbol-limit", type=int)
    parser.add_argument(
        "--history-source", choices=("auto", "sina"), default="auto"
    )
    parser.add_argument("--skip-classifications", action="store_true")
    parser.add_argument("--request-interval", type=float, default=0.25)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--retry-delay", type=float, default=1.0)
    parser.add_argument("--segment-days", type=int, default=366)
    parser.add_argument("--sync-plan", type=Path,
                        help="optional local split historical-acceptance/incremental plan")
    args = parser.parse_args()

    if args.command == "readiness":
        if args.snapshot_identity is None or args.admission_report is None:
            parser.error("readiness requires --snapshot-identity and --admission-report")
        from .sync_monitor import pilot_readiness
        from .reporting import write_pilot_readiness
        payload = pilot_readiness(args.snapshot_identity, args.admission_report,
                                  requirements_path=args.data_requirements)
        page = write_pilot_readiness(payload, args.report)
        print(json.dumps({"status": payload['status'], "page": str(page.resolve()),
                          "strategy_evaluated": False, "evidence_errors": payload['evidence_errors']}, ensure_ascii=False, indent=2))
        return

    if args.command == "backtest":
        result = Phase4FoundationRunner(args.cache, admission_path=args.formal_binding).run(
            end_date=args.end, report_directory=args.report)
        print(f"report={result.report_directory.resolve()}")
        return

    cache = SQLiteMarketCache(args.cache)
    if args.command == "sync":
        # An explicit local plan lets the existing single guardian worker
        # advance October without changing the frozen historical acceptance.
        plan_path = args.sync_plan or args.cache.with_suffix(".sync-plan.json")
        sync_end = args.end
        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            if plan.get("historical_acceptance_end") != "2026-09-30":
                raise ValueError("Phase4 acceptance end must remain 2026-09-30")
            incremental_end = date.fromisoformat(plan["incremental_target_end"])
            if incremental_end > date.today():
                raise ValueError("incremental target cannot be a future date")
            sync_end = max(sync_end, incremental_end)
            print(f"historical acceptance fixed at 2026-09-30; separate incremental target={sync_end}", flush=True)
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
        manifest = adapter.sync(cache, PHASE4_START, sync_end)
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


def _display_manifest(manifest: DataManifest) -> dict[str, object]:
    payload = asdict(manifest)
    payload["start_date"] = manifest.start_date.isoformat()
    payload["end_date"] = manifest.end_date.isoformat()
    payload["warnings"] = list(manifest.warnings)
    return payload


if __name__ == "__main__":
    main()
