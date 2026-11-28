"""Bounded, deterministic APEX state machine; no hardware actuation."""
from dataclasses import dataclass, replace
from threading import Lock
from .apex_shield import Decision, Limits, Telemetry, HTP, FeRAM, ReRAM, MTJ, decide


def integer(x, lo, hi):
    return type(x) is int and lo <= x <= hi


@dataclass(frozen=True, slots=True)
class Parameters:
    ambient_mc: int
    thermal_tau_ms: int
    heat_per_action_mc: int
    reram_busy_ms: int
    max_row_writes: int
    max_tracked_rows: int


@dataclass(frozen=True, slots=True)
class Snapshot:
    revision: int
    now_ms: int
    temp_mc: int
    vtcm_used_bytes: int = 0
    feram_ready: bool = False
    reram_busy_until_ms: int = 0
    reram_polled: bool = False
    row_writes: tuple[tuple[int, int], ...] = ()
    mtj_reads: int = 0
    mtj_writes: int = 0


class Twin:
    """Single-session CAS model, with virtual time and integer backward Euler cooling.

    Parameters are trusted scenario inputs, not calibrated device limits. Every
    accepted action atomically consumes a revision; denial changes no state.
    """
    def __init__(self, limits: Limits, parameters: Parameters):
        p = parameters
        if (type(limits) is not Limits or type(p) is not Parameters
                or not integer(p.ambient_mc, -40000, 124999)
                or not integer(p.thermal_tau_ms, 1, 1000000)
                or not integer(p.heat_per_action_mc, 0, 125000)
                or not integer(p.reram_busy_ms, 1, 60000)
                or not integer(p.max_row_writes, 1, 10**15)
                or not integer(p.max_tracked_rows, 1, 262144)
                or not decide(limits, Telemetry(0, p.ambient_mc, 0, False, False, False), HTP(0, 0), now=0).allowed):
            raise ValueError('invalid twin scenario')
        self._limits, self._parameters = limits, p
        self._state = Snapshot(0, 0, p.ambient_mc)
        self._lock = Lock()

    @property
    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._state

    def _cooled(self, revision, now):
        s, p = self._state, self._parameters
        if (not integer(revision, 0, 2**63-2) or revision != s.revision
                or not integer(now, s.now_ms, min(s.now_ms+1000000, 2**63-1-60000))):
            return None
        dt = now-s.now_ms
        excess = s.temp_mc-p.ambient_mc
        # Ceiling rounding never understates the remaining modeled excess heat.
        denom = p.thermal_tau_ms+dt
        temp = p.ambient_mc+(excess*p.thermal_tau_ms+denom-1)//denom
        return replace(s, revision=revision+1, now_ms=now, temp_mc=temp)

    def advance(self, revision, now, *, release_bytes=0) -> Decision:
        with self._lock:
            s = self._cooled(revision, now)
            if s is None or not integer(release_bytes, 0, self._state.vtcm_used_bytes):
                return Decision(False, 'invalid revision, time or release')
            self._state = replace(s, vtcm_used_bytes=s.vtcm_used_bytes-release_bytes)
            return Decision(True, 'virtual time advanced')

    def step(self, revision, now, action) -> Decision:
        with self._lock:
            s = self._cooled(revision, now)
            if s is None:
                return Decision(False, 'invalid revision or virtual time')
            busy = now < s.reram_busy_until_ms
            t = Telemetry(now, s.temp_mc, s.vtcm_used_bytes, s.feram_ready, busy, s.reram_polled)
            verdict = decide(self._limits, t, action, now=now)
            if not verdict.allowed:
                return verdict
            p = self._parameters
            temp = s.temp_mc+p.heat_per_action_mc
            if temp >= self._limits.max_temp_mc:
                return Decision(False, 'predicted thermal limit')
            s = replace(s, temp_mc=temp)
            if type(action) is HTP:
                s = replace(s, vtcm_used_bytes=s.vtcm_used_bytes+action.additional_vtcm_bytes)
            elif type(action) is FeRAM:
                if action.op == 'write':
                    first, count = action.address//4, action.length//4
                    if count > p.max_tracked_rows:
                        return Decision(False, 'row tracking budget')
                    rows = dict(s.row_writes)
                    for row in range(first, first+count):
                        n = rows.get(row, 0)+1
                        if n > p.max_row_writes or (row not in rows and len(rows) >= p.max_tracked_rows):
                            return Decision(False, 'row wear or tracking budget')
                        rows[row] = n
                    s = replace(s, row_writes=tuple(sorted(rows.items())))
                s = replace(s, feram_ready=True)
            elif type(action) is ReRAM:
                if action.op == 'poll':
                    s = replace(s, reram_polled=not busy)
                else:
                    s = replace(s, reram_polled=False, reram_busy_until_ms=now+p.reram_busy_ms)
            elif type(action) is MTJ:
                field = 'mtj_reads' if action.op == 'read' else 'mtj_writes'
                s = replace(s, **{field: getattr(s, field)+1})
            self._state = s
            return Decision(True, 'model action committed')
