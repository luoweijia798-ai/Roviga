from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any


def write_pilot_readiness(payload: dict, output_directory: str | Path) -> Path:
    """Append an immutable check record and render a local, dependency-free UI.

    This is prerequisite visibility only; no signals, trades or historical
    returns are invented. Existing equity/report writers remain unchanged.
    """
    import html
    import uuid
    if (payload.get('kind') != 'pilot_readiness_check'
            or payload.get('status') != 'DATA_NOT_READY'
            or payload.get('candidate') is not None
            or payload.get('strategy_evaluated') is not False
            or payload.get('formal_backtest_authorized') is not False
            or payload.get('operational_observation') is not False):
        raise ValueError('readiness writer cannot publish candidate or trading results')
    output = Path(output_directory)
    records = output / 'records'; records.mkdir(parents=True, exist_ok=True)
    record = records / (payload['observed_at'].replace(':', '-') + '-' + uuid.uuid4().hex + '.json')
    with record.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    esc = lambda value: html.escape(str(value))
    recent = []
    history_errors = 0
    for path in sorted(records.glob('*.json'), reverse=True)[:20]:
        try:
            row = json.loads(path.read_text(encoding='utf-8'))
            if (row['kind'] != 'pilot_readiness_check'
                    or row['status'] != 'DATA_NOT_READY'
                    or not isinstance(row['observed_at'], str)):
                raise ValueError('not a readiness record')
        except (OSError, ValueError, KeyError, TypeError):
            history_errors += 1
            continue
        recent.append(f"<tr><td>{esc(row['observed_at'])}</td><td>数据未就绪</td><td>{esc(row.get('snapshot_id', '未验证'))}</td></tr>")
    def layer_label(value):
        if not isinstance(value, str):
            return '未验证'
        if value.startswith('PASS FOR DECLARED V2 RECONSTRUCTION:'):
            return '仅已声明重建口径有依据'
        if value.startswith('PASS:'):
            return '报告记载通过'
        if value.startswith('BLOCKED:'):
            return '仍受阻'
        return '未验证'

    layers = ''.join(
        f'<tr><td>{esc(symbol)}</td><td>{esc(state.get("quotes", "未验证"))}</td>'
        + ''.join(f'<td>{esc(layer_label(state.get(key)))}</td>' for key in ('A', 'B', 'C'))
        + '</tr>' for symbol, state in payload.get('securities', {}).items())
    requirements = payload.get('data_requirements', {}) if payload.get('requirements_status') == 'BOUND_TO_SNAPSHOT' else {}
    vwap_rows = []
    for item in requirements.get('four_dates', []):
        raw = item['raw']
        cells = [item['symbol'], item['date'], raw['low'], raw['high'], raw['volume'], raw['amount'], raw['vwap']]
        vwap_rows.append('<tr>' + ''.join(f'<td>{esc(value)}</td>' for value in cells) + '</tr>')
    scope_rows = ''.join(
        f'<tr><td>{esc(item["symbol"])}</td><td>{esc(item["start"])} 至 {esc(item["end"])}</td>'
        '<td>需该来源量额的交易范围、发布精度与舍入依据；尚未取得完整证据。</td></tr>'
        for item in requirements.get('turnover_scope', []))
    requirements_view = (
        f'<p>已核对清单归属、数量及下列原始值：{len(vwap_rows)} 个异常日期、'
        f'{len(requirements.get("turnover_scope", []))} 段统计范围。两类可能重叠，不相加为独立问题总数。</p>'
        '<p>表中为候选库原始值：价格/金额为元、数量为股。未修正、未截断 VWAP，偏差小不代表通过。</p>'
        '<div class="scroll"><table><tr><th>证券</th><th>日期</th><th>最低价</th><th>最高价</th>'
        '<th>成交量</th><th>成交额</th><th>当前 VWAP</th></tr>' + ''.join(vwap_rows) + '</table></div>'
        '<table><tr><th>证券</th><th>需核实区间（含预热）</th><th>缺少材料</th></tr>' + scope_rows + '</table>'
        '<p>可用的下一步：如已有授权行情客户端，提供以上日期的不复权 OHLC、原始量额及字段/统计范围/精度说明。'
        '仅有四舍五入后的截图不足以证明；不需要账号、密码或 Token，也不要求购买服务。</p>'
        '<details><summary>原始材料需求、已尝试来源及模型限制</summary><pre>'
        + esc(json.dumps(requirements, ensure_ascii=False, indent=2)) + '</pre></details>'
        if requirements else '<p>尚未加载或未能核对缺项清单；不表示没有阻塞。请查看下方证据读取结果。</p>')
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Roviga 数据准备状态</title>
<style>body{{font:16px system-ui;max-width:1120px;margin:36px auto;padding:0 22px;background:#f4f7fa;color:#17273c}}section{{background:white;border-radius:12px;padding:22px;margin:18px 0}}h1{{font-size:28px}}.state{{font-size:26px;color:#9b4a00}}small{{color:#516078}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:10px;border-bottom:1px solid #ddd;overflow-wrap:anywhere}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}}.note{{border-left:5px solid #bd741c}}.scroll{{overflow-x:auto}}details{{margin:16px 0}}summary{{cursor:pointer}}p{{overflow-wrap:anywhere}}</style>
<h1>Roviga · 数据准备状态</h1><small>本地只读验收视图 · 不接券商 · 不使用真实资金</small>
<section class="note"><div class="state">数据未就绪，未选股</div><p>{esc(payload['reason'])}</p>
<p>这不是“无合格标的”，也不是风控主动空仓。风险计算尚未运行。</p></section>
<section><h2>本页面范围</h2><p>保持现有成交模型不变；本页面仅展示数据与未就绪状态，不代表整个总任务的授权范围。</p>
<p>本页面不生成候选或收益，不恢复 919 队列，不自动扩大迁移。模型限制保留，不视为已解决；正式回测门禁仍关闭。</p></section>
<section><h2>本次核对</h2><p>检查时间：{esc(payload['observed_at'])}（Asia/Shanghai）</p>
<p>候选数据最新日期：{esc(payload.get('data_latest_date') or '未验证')}；行情条数：{esc(payload.get('quote_rows', '未验证'))}；证券数：{esc(payload.get('security_count', '未验证'))}</p>
<p>快照：{esc(payload.get('snapshot_id', '未验证'))}</p>
<p>验收报告生成时间：{esc(payload.get('admission_generated_at') or '未记录')}；正式区间：2015-06-01 至 2026-09-30（另含必要预热）。</p>
<p>检查时间不代表下载成功时间；候选快照不是今日全市场数据。</p>
<p>证据读取结果：{esc('; '.join(payload.get('evidence_errors', [])) or '已提供文件的身份核对完成；不是数据审计通过')}</p>
<details><summary>原始统计与证据文件校验值</summary><pre>{esc(json.dumps({'counts': payload.get('counts', {}), 'evidence_files': payload.get('evidence_files', {})}, ensure_ascii=False, indent=2))}</pre></details></section>
<section><h2>三只试点验收分层</h2><div class="scroll"><table><tr><th>证券</th><th>真实行情条数</th><th>A 覆盖与重现</th><th>B 信号依据</th><th>C 成交依赖</th></tr>{layers}</table></div>
<p>B 的重建依据不等于数据当年已留存；分层通过不等于整只证券正式可用。</p>
<details><summary>原报告逐证券结论</summary><pre>{esc(json.dumps(payload.get('securities', {}), ensure_ascii=False, indent=2))}</pre></details></section>
<section><h2>待补材料与具体日期</h2>{requirements_view}</section>
<section><h2>最近 20 条准备状态检查</h2><p>不是 20 个交易日的前瞻观察；没有历史收益或模拟成交结果。</p>
<p>最近记录读取失败或格式不符：{history_errors} 条。原文件保留，未补造记录。</p>
<table><tr><th>检查时间</th><th>状态</th><th>快照</th></tr>{''.join(recent)}</table></section>
<section><h2>后续条件</h2><p>本页面不控制总任务推进。新证据按原规则核验；只有实际满足相应准入条件，才继续下一阶段。此页面不能改动成交模型或授权回测。</p></section></html>'''
    temporary = output / ('index-' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(page, encoding='utf-8')
    temporary.replace(output / 'index.html')
    return output / 'index.html'

from .analytics import BacktestAnalysis, analyze_backtest
from .backtest import BacktestResult


class BacktestReportWriter:
    """Writes a complete, dependency-free backtest report directory."""

    def write(
        self,
        result: BacktestResult,
        output_directory: str | Path,
        analysis: BacktestAnalysis | None = None,
    ) -> Path:
        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)
        analysis = analysis or analyze_backtest(result)
        self._write_summary(output / "summary.json", result, analysis)
        self._write_equity(output / "equity_curve.csv", result)
        self._write_trades(output / "trades.csv", result)
        self._write_events(output / "events.csv", result)
        self._write_monthly(output / "monthly_returns.csv", analysis)
        self._write_svg(output / "equity_curve.svg", result)
        return output

    def _write_summary(
        self, path: Path, result: BacktestResult, analysis: BacktestAnalysis
    ) -> None:
        payload = {
            "period": {
                "start": result.start_date,
                "end": result.end_date,
            },
            "initial_equity": result.initial_equity,
            "final_equity": result.final_equity,
            "performance": analysis.summary,
            "benchmarks": analysis.benchmarks,
            "market_regimes": analysis.regimes,
            "maximum_profit_trade": analysis.maximum_profit_trade,
            "maximum_loss_trade": analysis.maximum_loss_trade,
        }
        path.write_text(
            json.dumps(_jsonable(payload), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _write_equity(self, path: Path, result: BacktestResult) -> None:
        benchmark_names = sorted(
            {
                name
                for point in result.equity_curve
                for name in point.benchmark_closes
            }
        )
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "date",
                    "equity",
                    "cash",
                    "exposure",
                    "regime",
                    *benchmark_names,
                ]
            )
            for point in result.equity_curve:
                writer.writerow(
                    [
                        point.trading_date.isoformat(),
                        point.equity,
                        point.cash,
                        point.exposure,
                        point.regime.value,
                        *[
                            point.benchmark_closes.get(name, "")
                            for name in benchmark_names
                        ],
                    ]
                )

    def _write_trades(self, path: Path, result: BacktestResult) -> None:
        fields = [
            "symbol",
            "signal_date",
            "entry_date",
            "exit_date",
            "quantity",
            "entry_price",
            "exit_price",
            "net_profit",
            "return_fraction",
            "entry_reason",
            "exit_reason",
            "signal_regime",
        ]
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for trade in result.trades:
                row = asdict(trade)
                row["signal_date"] = trade.signal_date.isoformat()
                row["entry_date"] = trade.entry_date.isoformat()
                row["exit_date"] = trade.exit_date.isoformat()
                row["signal_regime"] = trade.signal_regime.value
                writer.writerow(row)

    def _write_events(self, path: Path, result: BacktestResult) -> None:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["date", "event_type", "symbol", "reason"])
            for event in result.events:
                writer.writerow(
                    [
                        event.trading_date.isoformat(),
                        event.event_type,
                        event.symbol or "",
                        event.reason,
                    ]
                )

    def _write_monthly(self, path: Path, analysis: BacktestAnalysis) -> None:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["month", "return"])
            writer.writerows(analysis.monthly_returns.items())

    def _write_svg(self, path: Path, result: BacktestResult) -> None:
        width, height, padding = 960, 420, 50
        values = [point.equity for point in result.equity_curve]
        minimum, maximum = min(values), max(values)
        spread = maximum - minimum or 1.0
        count = max(1, len(values) - 1)
        coordinates = [
            (
                padding + index * (width - 2 * padding) / count,
                height
                - padding
                - (value - minimum) * (height - 2 * padding) / spread,
            )
            for index, value in enumerate(values)
        ]
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in coordinates)
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <line x1="{padding}" y1="{height-padding}" x2="{width-padding}" y2="{height-padding}" stroke="#94a3b8"/>
  <line x1="{padding}" y1="{padding}" x2="{padding}" y2="{height-padding}" stroke="#94a3b8"/>
  <polyline points="{points}" fill="none" stroke="#2563eb" stroke-width="2.5"/>
  <text x="{padding}" y="28" font-family="sans-serif" font-size="18" fill="#0f172a">Equity Curve</text>
  <text x="{padding}" y="{height-14}" font-family="sans-serif" font-size="12" fill="#475569">{result.start_date.isoformat()}</text>
  <text x="{width-padding-70}" y="{height-14}" font-family="sans-serif" font-size="12" fill="#475569">{result.end_date.isoformat()}</text>
  <text x="{padding+5}" y="{padding+15}" font-family="sans-serif" font-size="12" fill="#475569">{maximum:.2f}</text>
  <text x="{padding+5}" y="{height-padding-8}" font-family="sans-serif" font-size="12" fill="#475569">{minimum:.2f}</text>
</svg>
"""
        path.write_text(svg, encoding="utf-8")


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {
            (key.value if isinstance(key, Enum) else str(key)): _jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value
