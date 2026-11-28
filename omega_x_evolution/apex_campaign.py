"""Durable bounded APEX model campaign with an independent retained cursor.

Only deterministic modeled actions are replayed; no hardware side effects.
The operator owns the trusted runtime, private directory and retained cursor.
"""
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import json
from .apex_planner import Plan, Scenario, evaluate, _plan, _work
from .apex_twin import Parameters, Snapshot, Twin, integer
from .ontos_epoch_journal_core import Cursor, IntegrityError, Journal

_DOMAIN = b'OMEGA-X/APEX/campaign/v1\x00'
_RUNTIME = ('apex_campaign.py', 'apex_planner.py', 'apex_twin.py', 'apex_shield.py',
            'ontos_epoch_journal_core.py')


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


@dataclass(frozen=True, slots=True)
class Progress:
    index: int
    snapshot: Snapshot


@dataclass(frozen=True, slots=True)
class Step:
    status: str
    cursor: Cursor | None


class Campaign:
    @staticmethod
    def pin_for(tenant, run_id, work, plan, scenario, deadline_ms):
        if (type(tenant) is not str or not 1 <= len(tenant) <= 64
                or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in tenant)
                or type(run_id) is not bytes or len(run_id) != 32
                or type(scenario) is not Scenario
                or type(scenario.parameters) is not Parameters
                or not integer(scenario.parameters.max_tracked_rows, 1, 4096)):
            raise ValueError('campaign scope')
        if evaluate(work, plan, scenario, deadline_ms) is None:
            raise ValueError('infeasible campaign')
        if any(type(v) not in (int, type(None)) for v in asdict(scenario.limits).values()):
            raise ValueError('typed campaign limits')
        here = Path(__file__).parent
        runtime = {name: sha256((here/name).read_bytes()).hexdigest() for name in _RUNTIME}
        return sha256(_DOMAIN + _bytes([tenant, run_id.hex(), _work(work), _plan(plan),
                                       asdict(scenario), deadline_ms, runtime])).digest()

    def __init__(self, path, tenant, run_id, work, plan, scenario, deadline_ms, pin):
        if type(pin) is not bytes or pin != self.pin_for(tenant, run_id, work, plan, scenario, deadline_ms):
            raise ValueError('independent campaign pin mismatch')
        self.path = Path(path).absolute()
        self.pin = pin
        self._scope = (tenant, run_id, work, plan, scenario, deadline_ms)
        self._initial = Progress(0, Twin(scenario.limits, scenario.parameters).snapshot)

    def _guard(self):
        if self.pin != self.pin_for(*self._scope):
            raise IntegrityError('campaign runtime or scope changed')

    def _digest(self, progress):
        return sha256(_DOMAIN + self.pin + _bytes(asdict(progress))).digest()

    def _replay(self, progress, payload):
        _, _, work, plan, scenario, deadline = self._scope
        index = progress.index + 1
        if index > len(work) or payload != index.to_bytes(2, 'big'):
            return None
        prefix = Plan(plan.name, plan.events[:index])
        result = evaluate(work[:index], prefix, scenario, deadline)
        return Progress(index, result.final) if result is not None else None

    def _journal(self):
        self._guard()
        return Journal(self.path, self._initial, self._digest, self._replay)

    def provision(self) -> Cursor:
        self._guard()
        return Journal.initialize(self.path, self._initial, self._digest, self._replay).genesis

    def read(self, retained: Cursor) -> Progress:
        current = self._journal().read(retained)
        if current.cursor != retained:
            raise IntegrityError('campaign differs from retained cursor')
        return current.state

    def recover(self, retained: Cursor) -> Cursor:
        """Explicit trusted recovery of a valid descendant of the retained floor."""
        return self._journal().read(retained).cursor

    def step(self, retained: Cursor) -> Step:
        if type(retained) is not Cursor:
            raise ValueError('independent cursor required')
        journal = self._journal()
        current = journal.read(retained)
        if current.cursor != retained:
            return Step('STALE', None)
        if current.state.index == len(self._scope[2]):
            return Step('COMPLETE', retained)
        update = journal.append(retained, (current.state.index+1).to_bytes(2, 'big'))
        return Step(update.status, update.snapshot.cursor if update.status == 'COMMITTED' else None)
