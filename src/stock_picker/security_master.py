"""Exchange-sourced security observations; never infer listing from price rows."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path


def canonical_code(value) -> str | None:
    text = str(value).strip()
    if re.fullmatch(r"\d{1,6}\.0", text):
        text = text[:-2]
    return text.zfill(6) if re.fullmatch(r"\d{1,6}", text) else None


def verified_date(value) -> str | None:
    text = str(value).strip()
    if text.lower() in {"", "none", "nan", "nat", "--"}:
        return None
    text = text[:10]
    if re.fullmatch(r"\d{8}", text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


SPECS = (
    ("stock_info_sz_name_code", "A股列表", "SZSE", "A股代码", "A股上市日期", None, None),
    ("stock_info_sh_name_code", "主板A股", "SSE", "证券代码", "上市日期", None, "主板"),
    ("stock_info_sh_name_code", "科创板", "SSE", "证券代码", "上市日期", None, "科创板"),
    ("stock_info_sz_delist", "终止上市公司", "SZSE", "证券代码", "上市日期", "终止上市日期", None),
    ("stock_info_sh_delist", "全部", "SSE", "公司代码", "上市日期", "暂停上市日期", None),
    ("stock_info_bj_name_code", None, "BSE", "证券代码", "上市日期", None, "北交所"),
)


def sse_a_retired_frame(payload):
    """COMPANY_CODE is an issuer key: never apply B-share LIST_DATE to A shares."""
    import pandas as pd
    rows = []
    for raw in payload.get("result", []):
        if str(raw.get("STOCK_TYPE")) not in {"1", "8"}:
            continue
        code = canonical_code(raw.get("A_STOCK_CODE"))
        if not code:
            continue
        rows.append({"公司代码": code, "公司简称": raw.get("COMPANY_ABBR"),
            "上市日期": verified_date(raw.get("LIST_DATE")),
            "暂停上市日期": verified_date(raw.get("DELIST_DATE")),
            "STOCK_TYPE": str(raw.get("STOCK_TYPE")), "issuer_company_code": raw.get("COMPANY_CODE"),
            "source_raw": json.dumps(raw, ensure_ascii=False)})
    return pd.DataFrame(rows, columns=("公司代码", "公司简称", "上市日期", "暂停上市日期", "STOCK_TYPE", "issuer_company_code", "source_raw"))


def fetch_sse_a_retired(timeout=20):
    import requests
    response = requests.get("https://query.sse.com.cn/commonQuery.do", timeout=timeout,
        headers={"Referer": "https://www.sse.com.cn/", "User-Agent": "Mozilla/5.0"},
        params={"sqlId": "COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L", "STOCK_TYPE": "1,8",
                "COMPANY_STATUS": "3", "type": "inParams", "isPagination": "true",
                "pageHelp.pageSize": "1000", "pageHelp.pageNo": "1"})
    response.raise_for_status()
    return sse_a_retired_frame(response.json())


@contextmanager
def capture_responses(directory: Path):
    """Capture response bytes, not request credentials or headers."""
    import requests
    directory.mkdir(parents=True, exist_ok=True)
    original = requests.sessions.Session.request
    records = []
    def capture(session, method, url, **kwargs):
        response = original(session, method, url, **kwargs)
        digest = hashlib.sha256(response.content).hexdigest()
        path = directory / (digest + ".response")
        if not path.exists():
            path.write_bytes(response.content)
        records.append({"url": response.url, "method": method, "status": response.status_code,
            "sha256": digest, "file": str(path.resolve()), "fetched_at": datetime.now(timezone.utc).isoformat()})
        return response
    requests.sessions.Session.request = capture
    try:
        yield records
    finally:
        requests.sessions.Session.request = original


def observations_from_frame(frame, spec, fetched_at, response_refs):
    method, argument, exchange, code_col, date_col, delist_col, board = spec
    if code_col not in frame or date_col not in frame:
        raise ValueError(f"{method}: required code/date columns missing: {list(frame.columns)}")
    observations = []
    for _, series in frame.iterrows():
        raw = {str(k): str(v) for k,v in series.items()}
        symbol = canonical_code(raw.get(code_col))
        if not symbol:
            continue
        listing = verified_date(raw.get(date_col))
        delisting = verified_date(raw.get(delist_col)) if delist_col else None
        observations.append({"symbol": symbol, "registry_key": f"{exchange}:{symbol}",
            "security_id": raw.get("ISIN") or raw.get("SECURITY_ID"),
            "code_valid_from": verified_date(raw.get("代码生效日期")),
            "code_valid_to": verified_date(raw.get("代码失效日期")),
            "exchange": exchange, "board_current": raw.get("板块") or board,
            "list_date": listing, "delist_date": delisting,
            "last_trade_date": verified_date(raw.get("最后交易日期")),
            "source": "AkShare." + method, "source_argument": argument, "fetched_at": fetched_at,
            "verification_status": "exchange_listing_date_verified" if listing else "source_date_missing_or_invalid",
            "raw": raw, "response_refs": response_refs,
            "notes": ["registry_key is an operational code key, not proof of stable security identity",
                "current board is not backdated board history",
                "code validity and last trading date remain unknown unless explicitly sourced",
                "BSE listing may mean former selected-layer entry; exchange eligibility is separate"]})
    return observations


def collect_master(adapter, directory: Path) -> dict:
    import akshare as ak
    observations, errors, responses = [], [], []
    for spec in SPECS:
        method, argument = spec[:2]
        try:
            with capture_responses(directory / "raw") as refs:
                frame = (adapter._request(fetch_sse_a_retired) if method == "stock_info_sh_delist" else
                         adapter._request(getattr(ak, method), **({"symbol": argument} if argument else {})))
            fetched = datetime.now(timezone.utc).isoformat()
            observations.extend(observations_from_frame(frame, spec, fetched, refs))
            responses.extend(refs)
        except Exception as error:
            errors.append({"source": method, "argument": argument, "error": f"{type(error).__name__}: {error}"})
        payload = {"observations": observations, "errors": errors, "responses": responses}
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "security_master_evidence.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"master {method}/{argument}: observations={len(observations)} errors={len(errors)}", flush=True)
    return payload


def apply_master(cache, observations: list[dict]) -> dict:
    """Append evidence and fill ONLY null fields, within one serialized transaction.

    No inventory replacement, no historic bars rewritten, no alias merge.
    Conflicting observations are retained but cannot overwrite verified values.
    """
    result = {"list_dates_filled": 0, "delist_dates_filled": 0, "conflicts": [], "unmatched": [], "unknown": []}
    grouped = {}
    for obs in observations:
        grouped.setdefault(obs["symbol"], []).append(obs)
    with cache.connect() as c:
        c.execute("PRAGMA busy_timeout=30000")
        c.execute("BEGIN IMMEDIATE")
        c.execute("CREATE TABLE IF NOT EXISTS security_master_observations ("
                  "observation_id TEXT PRIMARY KEY,symbol TEXT NOT NULL,registry_key TEXT NOT NULL,"
                  "source TEXT NOT NULL,fetched_at TEXT NOT NULL,verification_status TEXT NOT NULL,payload TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS metadata_repair_journal ("
                  "repair_id TEXT PRIMARY KEY,symbol TEXT NOT NULL,field TEXT NOT NULL,old_value TEXT,new_value TEXT,"
                  "evidence_id TEXT NOT NULL,applied_at TEXT NOT NULL)")
        for symbol, group in sorted(grouped.items()):
            old = c.execute("SELECT * FROM stocks WHERE symbol=?", (symbol,)).fetchone()
            if old is None:
                result["unmatched"].append(symbol)
                continue
            compatible = [o for o in group if o["exchange"] == old["exchange"]]
            for obs in group:
                serialized = json.dumps(obs, sort_keys=True, ensure_ascii=False)
                key = hashlib.sha256(serialized.encode()).hexdigest()
                c.execute("INSERT OR IGNORE INTO security_master_observations VALUES (?,?,?,?,?,?,?)",
                          (key, symbol, obs["registry_key"], obs["source"], obs["fetched_at"], obs["verification_status"], serialized))
            for field in ("list_date", "delist_date"):
                candidates = {o[field] for o in compatible if o.get(field)}
                if len(candidates) > 1 or (old[field] and candidates and old[field] not in candidates):
                    result["conflicts"].append({"symbol": symbol, "field": field, "stored": old[field], "observed": sorted(candidates)})
                    continue
                if not old[field] and len(candidates) == 1:
                    new_value = next(iter(candidates))
                    obs = next(o for o in compatible if o[field] == new_value)
                    evidence_id = hashlib.sha256(json.dumps(obs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                    repair_id = hashlib.sha256(f"{symbol}:{field}:{new_value}:{evidence_id}".encode()).hexdigest()
                    c.execute(f"UPDATE stocks SET {field}=? WHERE symbol=? AND {field} IS NULL", (new_value, symbol))
                    c.execute("INSERT OR IGNORE INTO metadata_repair_journal VALUES (?,?,?,?,?,?,?)",
                              (repair_id, symbol, field, None, new_value, evidence_id, datetime.now(timezone.utc).isoformat()))
                    result[field.replace("_date", "_dates_filled")] += 1
        result["unknown"] = [dict(r) for r in c.execute("SELECT symbol,exchange,source FROM stocks WHERE list_date IS NULL ORDER BY symbol")]
        if observations:
            cache._invalidate_audit(c)
    return result


def resolve_proven_b_share_date(cache, raw_payload: dict, evidence_ref: str) -> list[dict]:
    """CAS correction ONLY where stored A date exactly equals same issuer's B date."""
    corrections = []
    groups = {}
    for r in raw_payload.get("result", []):
        groups.setdefault(canonical_code(r.get("A_STOCK_CODE")), []).append(r)
    with cache.connect() as c:
        c.execute("PRAGMA busy_timeout=30000"); c.execute("BEGIN IMMEDIATE")
        for symbol, rows in groups.items():
            old = c.execute("SELECT * FROM stocks WHERE symbol=?", (symbol,)).fetchone()
            if not old or old["exchange"] != "SSE" or old["source"] != "AkShare.stock_info_sh_delist":
                continue
            a_dates = {verified_date(r.get("LIST_DATE")) for r in rows if str(r.get("STOCK_TYPE")) in {"1", "8"}}
            b_dates = {verified_date(r.get("LIST_DATE")) for r in rows if str(r.get("STOCK_TYPE")) == "2"}
            a_dates.discard(None); b_dates.discard(None)
            if len(a_dates) != 1 or old["list_date"] not in b_dates or old["list_date"] in a_dates:
                continue
            new = next(iter(a_dates)); repair_id = hashlib.sha256(f"A-not-B:{symbol}:{old['list_date']}:{new}:{evidence_ref}".encode()).hexdigest()
            c.execute("UPDATE stocks SET list_date=? WHERE symbol=? AND list_date=?", (new, symbol, old["list_date"]))
            c.execute("INSERT OR IGNORE INTO metadata_repair_journal VALUES (?,?,?,?,?,?,?)", (repair_id,
                symbol, "list_date", old["list_date"], new, evidence_ref, datetime.now(timezone.utc).isoformat()))
            corrections.append({"symbol": symbol, "old_b_share_date": old["list_date"], "new_a_share_date": new,
                "proof": evidence_ref, "reason": "issuer COMPANY_CODE had both STOCK_TYPE=1 and STOCK_TYPE=2 records"})
        if corrections:
            cache._invalidate_audit(c)
    return corrections
