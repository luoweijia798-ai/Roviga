"""Single-worker supervisor for resumable real-data synchronization (no backtest)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from .phase4_foundation import DEFAULT_CACHE
from .real_market import SQLiteMarketCache
from .sync_monitor import Phase4SyncMonitor


def worker_command(cache: Path, end_date: date) -> list[str]:
    return [sys.executable, "-u", "-m", "stock_picker.phase4_foundation", "sync",
            "--cache", str(cache), "--end", end_date.isoformat(),
            "--skip-classifications", "--request-interval", "0.5",
            "--max-attempts", "5", "--retry-delay", "2", "--segment-days", "366"]


def batch_end(state: dict[str, object], today: date) -> date:
    # Finish an interrupted batch before advancing the moving date boundary.
    if state.get("phase") not in {"audit_passed", "audit_blocked"} and state.get("end"):
        return date.fromisoformat(str(state["end"]))
    return today


def acquire_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if path.stat().st_size == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def process_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.GetExitCodeProcess.restype = wintypes.BOOL
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--monitor-seconds", type=float, default=1800)
    parser.add_argument("--retry-seconds", type=float, default=900)
    parser.add_argument("--wait-for-pid", type=int)
    args = parser.parse_args()
    if args.monitor_seconds <= 0 or args.retry_seconds <= 0:
        parser.error("intervals must be positive")
    lock = acquire_lock(args.cache.with_suffix(".guardian.lock"))
    if lock is None:
        print("guardian already running; no second worker started", flush=True)
        return
    logs = Path("logs")
    logs.mkdir(exist_ok=True)
    state_path = logs / "phase4_guardian_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    if state.get("phase") in {"audit_passed", "audit_blocked"} and args.end is None:
        print("audit completed; waiting for explicit next-step instruction", flush=True)
        lock.close()
        return
    end_date = args.end or batch_end(state, date.today())
    cache = SQLiteMarketCache(args.cache)
    monitor = Phase4SyncMonitor(cache)

    def save_state(phase: str, **details: object) -> None:
        state.update(end=end_date.isoformat(), phase=phase, guardian_pid=os.getpid(),
                     updated_at=datetime.now(timezone.utc).isoformat(), **details)
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(state_path)

    def refresh(audit: bool = False):
        return monitor.refresh(end_date=end_date,
                               status_output=Path("phase4_sync_status.json"),
                               audit_output=Path("phase4_data_audit_report"),
                               audit_when_settled=audit)

    try:
        # Adopt/wait for an existing downloader or its legacy supervisor without
        # killing it or starting a concurrent writer. Persist this across restart.
        existing_pid = args.wait_for_pid or state.get("legacy_pid") or state.get("worker_pid")
        if existing_pid and int(existing_pid) != os.getpid():
            save_state("waiting_for_existing_sync", legacy_pid=int(existing_pid))
            next_monitor = 0.0
            while process_alive(int(existing_pid)):
                if time.monotonic() >= next_monitor:
                    try:
                        refresh()
                    except Exception as error:
                        print(f"monitor error while preserving existing sync: {error}", flush=True)
                    next_monitor = time.monotonic() + args.monitor_seconds
                time.sleep(min(10, args.monitor_seconds))
            save_state("retry_wait", legacy_pid=None, worker_pid=None)
        with (logs / "phase4_sync.worker.log").open("a", encoding="utf-8") as worker_log:
            while True:
                snapshot, _ = refresh()
                if snapshot["sync_complete"]:
                    save_state("auditing", worker_pid=None)
                    _, audit = refresh(True)
                    save_state("audit_passed" if audit and audit.passed else "audit_blocked",
                               worker_pid=None)
                    print("sync complete; audit finished; waiting for next instruction", flush=True)
                    return
                worker = subprocess.Popen(worker_command(args.cache, end_date),
                                          stdout=worker_log, stderr=subprocess.STDOUT)
                save_state("syncing", worker_pid=worker.pid)
                next_monitor = time.monotonic() + args.monitor_seconds
                while worker.poll() is None:
                    time.sleep(min(10, args.monitor_seconds))
                    if time.monotonic() >= next_monitor:
                        try:
                            refresh()
                        except Exception as error:
                            print(f"monitor error: {type(error).__name__}: {error}", flush=True)
                        next_monitor = time.monotonic() + args.monitor_seconds
                save_state("retry_wait", worker_pid=None, last_exit_code=worker.returncode)
                try:
                    snapshot, _ = refresh()
                except Exception as error:
                    print(f"post-sync monitor error: {error}", flush=True)
                    snapshot = {"sync_complete": False}
                if snapshot["sync_complete"]:
                    continue
                print(f"sync exited {worker.returncode}; retained failures; retrying", flush=True)
                deadline = time.monotonic() + args.retry_seconds
                while time.monotonic() < deadline:
                    time.sleep(min(10, max(0.1, deadline - time.monotonic())))
    finally:
        # Closing our lock never terminates a running downloader.
        lock.close()


if __name__ == "__main__":
    main()
