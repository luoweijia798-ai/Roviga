from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .models import Selection
from .trading import Side, Trade


class TrackingState(str, Enum):
    WAITING_FILL = "WAITING_FILL"
    ACTIVE = "ACTIVE"
    STOPPED_OUT = "STOPPED_OUT"
    TOOK_PROFIT = "TOOK_PROFIT"


@dataclass(frozen=True, slots=True)
class PriceObservation:
    trading_date: date
    close: float
    high: float
    low: float


@dataclass(slots=True)
class CandidateTrack:
    signal: Selection
    planned_entry_price: float
    stop_price: float
    take_profit_price: float
    fill: Trade | None = None
    observations: list[PriceObservation] = field(default_factory=list)
    performance: dict[int, float] = field(default_factory=dict)
    maximum_gain: float = 0.0
    maximum_loss: float = 0.0
    state: TrackingState = TrackingState.WAITING_FILL

    @property
    def reference_price(self) -> float:
        return self.fill.execution_price if self.fill else self.planned_entry_price


class DailyTracker:
    """Tracks one and only one candidate for each signal date."""

    HORIZONS = (1, 3, 5)

    def __init__(self) -> None:
        self._tracks: dict[date, CandidateTrack] = {}

    def reserve_signal(self, selection, **prices):
        """Workflow reservation must reject an already submitted candidate."""
        return self.record_signal(selection, **prices)

    def record_signal(
        self,
        selection: Selection,
        *,
        planned_entry_price: float,
        stop_price: float,
        take_profit_price: float,
    ) -> CandidateTrack:
        if selection.trading_date in self._tracks:
            raise ValueError("a candidate is already recorded for this trading day")
        if not 0 < stop_price < planned_entry_price < take_profit_price:
            raise ValueError("prices must satisfy stop < entry < take profit")
        track = CandidateTrack(
            signal=selection,
            planned_entry_price=planned_entry_price,
            stop_price=stop_price,
            take_profit_price=take_profit_price,
        )
        self._tracks[selection.trading_date] = track
        return track

    def record_fill(self, signal_date: date, trade: Trade) -> CandidateTrack:
        track = self.get(signal_date)
        if trade.side is not Side.BUY:
            raise ValueError("candidate fill must be a buy trade")
        if trade.symbol != track.signal.symbol:
            raise ValueError("fill symbol does not match the selected candidate")
        if track.fill is not None:
            raise ValueError("candidate fill has already been recorded")
        track.fill = trade
        track.state = TrackingState.ACTIVE
        self._recalculate(track)
        return track

    def update_market(
        self,
        signal_date: date,
        *,
        trading_date: date,
        close: float,
        high: float | None = None,
        low: float | None = None,
    ) -> CandidateTrack:
        track = self.get(signal_date)
        if trading_date <= signal_date:
            raise ValueError("performance observations must be after the signal date")
        if close <= 0:
            raise ValueError("close must be positive")
        high = close if high is None else high
        low = close if low is None else low
        if low <= 0 or high < close or low > close:
            raise ValueError("prices must satisfy 0 < low <= close <= high")
        if any(item.trading_date == trading_date for item in track.observations):
            raise ValueError("market date has already been recorded")

        observation = PriceObservation(trading_date, close, high, low)
        track.observations.append(observation)
        track.observations.sort(key=lambda item: item.trading_date)
        self._recalculate(track)
        return track

    def get(self, signal_date: date) -> CandidateTrack:
        try:
            return self._tracks[signal_date]
        except KeyError as error:
            raise KeyError(f"no candidate recorded for {signal_date.isoformat()}") from error

    def all(self) -> tuple[CandidateTrack, ...]:
        return tuple(self._tracks[key] for key in sorted(self._tracks))

    def _recalculate(self, track: CandidateTrack) -> None:
        reference = track.reference_price
        track.performance.clear()
        for horizon in self.HORIZONS:
            if len(track.observations) >= horizon:
                close = track.observations[horizon - 1].close
                track.performance[horizon] = close / reference - 1.0

        gains = [item.high / reference - 1.0 for item in track.observations]
        losses = [item.low / reference - 1.0 for item in track.observations]
        track.maximum_gain = max([0.0, *gains])
        track.maximum_loss = min([0.0, *losses])
        if any(item.low <= track.stop_price for item in track.observations):
            track.state = TrackingState.STOPPED_OUT
        elif any(
            item.high >= track.take_profit_price for item in track.observations
        ):
            track.state = TrackingState.TOOK_PROFIT
        elif track.fill is not None:
            track.state = TrackingState.ACTIVE


class SQLiteDailyTracker(DailyTracker):
    """Transactional event storage for the existing tracker, not a trading gate.

    Replays exactly the existing tracking calculations; does not select stocks,
    generate fills, repair prices or restore the broker/account/risk state.
    A separate journal must never be the live market or candidate database.
    """

    def __init__(self, path, *, context=None, create=False, read_only=False):
        import json
        from pathlib import Path
        super().__init__()
        self.path = Path(path).resolve()
        self.read_only = read_only
        if not self.path.exists() and create:
            if read_only or context is None:
                raise ValueError('creating a journal requires context and write access')
            self._validate_context(context)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation: never initialize tables in an existing market DB.
            with self.path.open('xb'):
                pass
            with self._connection(write=True) as connection:
                connection.execute('CREATE TABLE tracking_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
                connection.execute('CREATE TABLE tracking_events('
                    'seq INTEGER PRIMARY KEY, event_key TEXT UNIQUE NOT NULL, '
                    'payload TEXT NOT NULL, digest TEXT NOT NULL)')
                connection.execute('INSERT INTO tracking_meta VALUES(?,?)',
                                   ('schema','roviga-tracking-events-v1'))
                connection.execute('INSERT INTO tracking_meta VALUES(?,?)',
                                   ('context',self._encode(context)))
        with self._connection() as connection:
            schema = connection.execute("SELECT value FROM tracking_meta WHERE key='schema'").fetchone()
            if schema is None or schema[0] != 'roviga-tracking-events-v1':
                raise ValueError('unsupported tracking journal')
            row = connection.execute("SELECT value FROM tracking_meta WHERE key='context'").fetchone()
            if row is None:
                raise ValueError('missing tracking context')
            self.context = json.loads(row[0])
            self._validate_context(self.context)
            if context is not None and self._encode(context) != self._encode(self.context):
                raise ValueError('tracking data/configuration/provenance changed; use a new journal')
            tracker, _, _ = self._replay(connection)
            self._tracks = tracker._tracks

    @staticmethod
    def _validate_context(context):
        if (not isinstance(context, dict)
                or set(context) != {'kind','data_version','configuration_id'}
                or context['kind'] not in {'synthetic_test','historical_replay','prospective_paper'}
                or any(not isinstance(value,str) or not value.strip() for value in context.values())):
            raise ValueError('explicit provenance, data version and configuration identity required')

    def _connection(self, *, write=False):
        import sqlite3
        from contextlib import contextmanager

        @contextmanager
        def opened():
            if write and self.read_only:
                raise ValueError('tracking journal opened read-only')
            connection = sqlite3.connect(self.path.as_uri() + ('?mode=rw' if write else '?mode=ro'),
                                         uri=True, timeout=10)
            try:
                # One consistent view, including replay and append by concurrent callers.
                connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()
        return opened()

    @staticmethod
    def _encode(value):
        import json
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'), allow_nan=False)

    @staticmethod
    def _apply(tracker, event):
        from .trading import Trade
        action = event['action']
        signal_date = date.fromisoformat(event['signal_date'])
        values = dict(event['values'])
        if action == 'signal':
            signal = dict(values.pop('selection'))
            signal['trading_date'] = date.fromisoformat(signal['trading_date'])
            if signal['trading_date'] != signal_date:
                raise ValueError('signal date mismatch')
            return tracker.record_signal(Selection(**signal), **values)
        if action == 'fill':
            values['trading_date'] = date.fromisoformat(values['trading_date'])
            values['side'] = Side(values['side'])
            return tracker.record_fill(signal_date, Trade(**values))
        if action == 'market':
            values['trading_date'] = date.fromisoformat(values['trading_date'])
            return tracker.update_market(signal_date, **values)
        raise ValueError('unknown tracking event')

    @staticmethod
    def _event_key(event):
        key = event['action'] + ':' + event['signal_date']
        if event['action'] == 'market':
            key += ':' + event['values']['trading_date']
        return key

    def _replay(self, connection):
        import hashlib
        import json
        tracker = DailyTracker()
        stored_context = connection.execute("SELECT value FROM tracking_meta WHERE key='context'").fetchone()
        if stored_context is None or stored_context[0] != self._encode(self.context):
            raise ValueError('tracking context changed during use')
        previous = hashlib.sha256(self._encode(self.context).encode('utf-8')).hexdigest()
        count = 0
        for seq, key, payload, digest in connection.execute(
                'SELECT seq,event_key,payload,digest FROM tracking_events ORDER BY seq'):
            if seq != count + 1:
                raise ValueError('non-contiguous tracking history')
            expected = hashlib.sha256((previous + '\n' + payload).encode('utf-8')).hexdigest()
            event = json.loads(payload)
            from datetime import datetime
            if datetime.fromisoformat(event['recorded_at']).tzinfo is None:
                raise ValueError('event acquisition time must be timezone-aware')
            if digest != expected or key != self._event_key(event):
                raise ValueError('tracking history integrity mismatch')
            self._apply(tracker,event)
            previous = digest
            count += 1
        return tracker, count, previous

    def _append(self, event, *, require_new=False):
        import copy
        import hashlib
        import json
        from datetime import datetime, timezone
        payload = self._encode(event)
        key = self._event_key(event)
        with self._connection(write=True) as connection:
            # Never trust an in-memory copy after restart or another writer.
            tracker, count, previous = self._replay(connection)
            existing = connection.execute('SELECT payload FROM tracking_events WHERE event_key=?',(key,)).fetchone()
            if existing is not None:
                if require_new:
                    raise ValueError('candidate already submitted; reconcile existing history before retry')
                original = json.loads(existing[0])
                original.pop('recorded_at')
                if self._encode(original) != payload:
                    raise ValueError('conflicting repeat; original tracking event retained')
                result = tracker.get(date.fromisoformat(event['signal_date']))
            else:
                result = self._apply(tracker,event)
                payload = self._encode({**event,'recorded_at':datetime.now(timezone.utc).isoformat()})
                digest = hashlib.sha256((previous + '\n' + payload).encode('utf-8')).hexdigest()
                connection.execute('INSERT INTO tracking_events VALUES(?,?,?,?)',
                                   (count+1,key,payload,digest))
        self._tracks = tracker._tracks
        return copy.deepcopy(result)

    def record_signal(self, selection, *, planned_entry_price, stop_price, take_profit_price, require_new=False):
        from dataclasses import asdict
        signal = asdict(selection)
        signal['trading_date'] = selection.trading_date.isoformat()
        return self._append({'action':'signal','signal_date':selection.trading_date.isoformat(),
            'values':{'selection':signal,'planned_entry_price':planned_entry_price,
                      'stop_price':stop_price,'take_profit_price':take_profit_price}},require_new=require_new)

    def reserve_signal(self, selection, **prices):
        return self.record_signal(selection, **prices, require_new=True)

    def record_fill(self, signal_date, trade):
        from dataclasses import asdict
        values = asdict(trade)
        values.update(trading_date=trade.trading_date.isoformat(),side=trade.side.value)
        return self._append({'action':'fill','signal_date':signal_date.isoformat(),'values':values})

    def update_market(self, signal_date, *, trading_date, close, high=None, low=None):
        return self._append({'action':'market','signal_date':signal_date.isoformat(),
            'values':{'trading_date':trading_date.isoformat(),'close':close,'high':high,'low':low}})

    def get(self, signal_date):
        with self._connection() as connection:
            tracker, _, _ = self._replay(connection)
        return tracker.get(signal_date)

    def all(self):
        with self._connection() as connection:
            tracker, _, _ = self._replay(connection)
        return tracker.all()

    def inspection(self):
        """Counts/identities only; does not run a selector or publish returns."""
        with self._connection() as connection:
            tracker, count, digest = self._replay(connection)
        tracks = tracker.all()
        return {'schema':'roviga-tracking-inspection-v1','context':self.context,
                'event_count':count,'chain_head':digest,'candidate_count':len(tracks),
                'signal_dates':[t.signal.trading_date.isoformat() for t in tracks],
                'fill_count':sum(t.fill is not None for t in tracks),
                'price_observation_count':sum(len(t.observations) for t in tracks),
                'not_an_admission_or_account_restore':True}
