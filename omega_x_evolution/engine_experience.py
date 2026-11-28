"""Fenced learning from committed DGM rounds; advisory, never a release gate.

Stores compact research outcomes, not source text. Every public read checks the
current source and DGM fences and the imported prefix. Revocation is permanent
for a round and its dependent suffix; retained historical bytes are not erased.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from hashlib import sha256
from pathlib import Path

from .engine_dgm import BASE, DGMJournal, Selector, _metric, _promote, _valid_metrics
from .engine import run
from .ontos_epoch_journal_core import IntegrityError
from .ontos_managed_journal import Fence, ManagedJournal
from .ontos_rcc import Statistics, _int, _pin
from .ontos_reversible_ops import _train
from .ontos_v72_jcs import canonical_json, parse_json
from .ontos_v72_receipts import strict_verify

DOMAIN = b'OMEGA-X/DGM-experience/v1\x00'
MAX_ROUNDS = 8


def _hash(value):
    return sha256(DOMAIN + canonical_json(value)).hexdigest()


def _selector(wire):
    if type(wire) is not list or len(wire) != 3:
        raise ValueError('selector wire')
    return Selector(*wire)


def _features(s):
    if type(s) is not Selector:
        raise ValueError('typed selector required')
    s.__post_init__()
    return (1, s.stride, s.fast, s.deep)


def revoke_bytes(pin, round_no, digest, reason):
    if not all(_pin(x) for x in (pin, digest, reason)) or not _int(round_no, 1, MAX_ROUNDS):
        raise ValueError('invalid revocation scope')
    return DOMAIN + b'revoke\x00' + canonical_json([pin, round_no, digest, reason])


def _learn(record):
    return {'kind': 'learn', 'round': record['round'], 'digest': _hash(record),
            'selector': record['challenger'], 'active': record['active'],
            'label': 1 if record['promoted'] else (0 if record['challenger'] == record['parent'] else -1)}


@dataclass(frozen=True, slots=True)
class Experience:
    round: int
    digest: str
    selector: Selector
    label: int


@dataclass(frozen=True, slots=True)
class View:
    entries: tuple[Experience, ...]
    statistics: Statistics
    ridge: tuple[Fraction, ...]
    perceptron: tuple[int, ...]
    trusted_active: Selector
    imported: int
    pending: int
    invalidated_from: int | None

    def rank(self, candidates):
        """R2 exact selector outcomes, then R1/R3 predictions; research advice."""
        if self.pending:
            raise ValueError('synchronize committed rounds before ranking')
        if type(candidates) is not tuple or not 1 <= len(candidates) <= 8:
            raise ValueError('bounded candidate set required')
        for c in candidates:
            _features(c)
        if len(set(candidates)) != len(candidates):
            raise ValueError('duplicate candidates')
        def score(c):
            labels = [e.label for e in self.entries if e.selector == c and e.label]
            empirical = Fraction(sum(labels), len(labels)) if labels else Fraction(0)
            x = _features(c)
            return (empirical, sum(a*b for a,b in zip(self.ridge,x)),
                    sum(a*b for a,b in zip(self.perceptron,x)))
        return tuple(sorted(candidates, key=score, reverse=True))


@dataclass(frozen=True, slots=True)
class Update:
    status: str
    fence: Fence | None


class ExperienceJournal:
    @staticmethod
    def pin_for(dgm):
        if type(dgm) is not DGMJournal:
            raise ValueError('typed DGM required')
        return _hash([dgm.pin, dgm.memory.source._scope.revoker.hex(), 'selector-features-v1',
                      sha256(Path(__file__).read_bytes()).hexdigest()])

    def __init__(self, anchor, segments, dgm, pin):
        if self.pin_for(dgm) != pin:
            raise ValueError('independent experience pin required')
        source = dgm.memory.source
        dirs = [Path(anchor).parent.resolve(), Path(segments).resolve(),
                dgm._journal.anchor.parent.resolve(), dgm._journal.segments,
                source._vault_path.parent.resolve(), source._journal.anchor.parent.resolve(), source._journal.segments]
        if any(a == b or a in b.parents or b in a.parents for i,a in enumerate(dirs) for b in dirs[i+1:]):
            raise ValueError('separate experience trust directories required')
        self.dgm = dgm
        self.pin = pin
        self._revoker = source._scope.revoker
        self._journal = ManagedJournal(anchor, segments, self._digest, self._replay, self._encode, self._decode)

    def _reduce(self, rows):
        if type(rows) is not tuple or len(rows) > 2*MAX_ROUNDS:
            raise ValueError('experience event budget')
        learned = []
        cutoff = MAX_ROUNDS + 1
        for row in rows:
            if type(row) is not dict:
                raise ValueError('invalid experience row')
            i = row.get('round')
            if not _int(i, 1, self.dgm.plan.rounds):
                raise ValueError('round bounds')
            if row.get('kind') == 'learn':
                if (set(row) != {'kind','round','digest','selector','active','label'} or i != len(learned)+1
                        or not _pin(row['digest']) or not _int(row['label'],-1,1)):
                    raise ValueError('invalid learned round')
                _selector(row['selector']); _selector(row['active'])
                learned.append(row)
            elif row.get('kind') == 'revoke':
                if (set(row) != {'kind','round','reason','signature'} or i > len(learned) or i >= cutoff
                        or not _pin(row['reason']) or type(row['signature']) is not str or len(row['signature']) != 128):
                    raise ValueError('invalid revocation')
                raw = revoke_bytes(self.pin, i, learned[i-1]['digest'], row['reason'])
                sig = bytes.fromhex(row['signature'])
                if sig.hex() != row['signature'] or not strict_verify(self._revoker, raw, sig):
                    raise ValueError('revocation signature')
                cutoff = i
            else:
                raise ValueError('unsupported experience event')
        return learned, cutoff

    def _encode(self, rows):
        self._reduce(rows)
        return canonical_json([self.pin, list(rows)])

    def _digest(self, rows):
        return sha256(DOMAIN + self._encode(rows)).digest()

    def _decode(self, raw):
        pin, rows = parse_json(raw)
        if pin != self.pin or type(rows) is not list:
            raise ValueError('experience scope')
        rows = tuple(rows)
        if self._encode(rows) != raw:
            raise ValueError('noncanonical experience state')
        return rows

    def _replay(self, rows, raw):
        try:
            row = parse_json(raw)
            if canonical_json(row) != raw:
                return None
            out = rows + (row,)
            self._reduce(out)
            return out
        except (ValueError, TypeError, KeyError, OverflowError):
            return None

    def _guard(self, source_fence):
        if self.pin_for(self.dgm) != self.pin:
            raise IntegrityError('experience runtime changed')
        return self.dgm._guard(source_fence)

    def _source(self, dgm_fence):
        if type(dgm_fence) is not Fence:
            raise ValueError('independent DGM fence required')
        records = self.dgm._journal.read(dgm_fence).state
        self.dgm._validate(records)
        return records

    def _checked(self, retained, records):
        if type(retained) is not Fence:
            raise ValueError('independent experience fence required')
        learned, cutoff = self._reduce(self._journal.read(retained).state)
        if len(learned) > len(records) or any(row != _learn(record) for row,record in zip(learned,records)):
            raise IntegrityError('experience source prefix mismatch')
        return learned, cutoff

    def initialize(self, dgm_fence, *, source_fence):
        with self._guard(source_fence):
            self._source(dgm_fence)
            return self._journal.initialize(()).fence

    def recover_from_anchor(self, dgm_fence, *, source_fence):
        """Explicit trusted recovery; anchor alone is not freshness evidence."""
        with self._guard(source_fence):
            records = self._source(dgm_fence)
            fence = self._journal.read().fence
            self._checked(fence, records)
            return fence

    def sync(self, retained, dgm_fence, *, source_fence):
        with self._guard(source_fence):
            records = self._source(dgm_fence)
            learned, _ = self._checked(retained, records)
            if len(learned) == len(records):
                return Update('UP_TO_DATE', retained)
            u = self._journal.append(retained, canonical_json(_learn(records[len(learned)])))
            return Update(u.status, u.snapshot.fence if u.status == 'COMMITTED' else None)

    def revoke(self, retained, dgm_fence, round_no, reason, signature, *, source_fence):
        if type(signature) is not bytes or len(signature) != 64:
            raise ValueError('typed signature required')
        with self._guard(source_fence):
            records = self._source(dgm_fence)
            self._checked(retained, records)
            u = self._journal.append(retained, canonical_json({'kind':'revoke','round':round_no,
                                      'reason':reason,'signature':signature.hex()}))
            return Update(u.status, u.snapshot.fence if u.status == 'COMMITTED' else None)

    def view(self, retained, dgm_fence, *, source_fence):
        with self._guard(source_fence):
            records = self._source(dgm_fence)
            learned, cutoff = self._checked(retained, records)
            active = learned[:cutoff-1]
            entries = tuple(Experience(r['round'],r['digest'],_selector(r['selector']),r['label']) for r in active)
            stats = Statistics.zero(4)
            for r in learned:
                if r['label']:
                    stats = stats.delta(_features(_selector(r['selector'])),r['label'],1)
            for r in learned[cutoff-1:]:
                if r['label']:
                    stats = stats.delta(_features(_selector(r['selector'])),r['label'],-1)
            samples = [(e.digest,_features(e.selector),e.label) for e in entries if e.label]
            check = Statistics.zero(4)
            for _,x,y in samples:
                check = check.delta(x,y,1)
            if stats != check:
                raise IntegrityError('experience downdate invariant')
            return View(entries,stats,stats.ridge(1),_train((0,)*4,samples),
                        _selector(active[-1]['active']) if active else BASE,len(learned),len(records)-len(learned),
                        cutoff if cutoff <= MAX_ROUNDS else None)

    def rank(self, retained, dgm_fence, candidates, *, source_fence):
        return self.view(retained,dgm_fence,source_fence=source_fence).rank(candidates)

    async def assess(self, retained, dgm_fence, candidates, seeds, *, source_fence):
        """Assess one learned recommendation on two seeds outside the DGM plan.

        Advisory only; repeated assessment seeds are not a blind holdout.
        Does not write learning records or mutate the DGM state.
        """
        scheduled = {s for i in range(self.dgm.plan.rounds) for s in self.dgm.plan.schedule(i)}
        if (type(seeds) is not tuple or len(seeds)!=2 or any(not _int(s,0,2**32-1) for s in seeds)
                or len(set(seeds))!=2 or scheduled.intersection(seeds)):
            raise ValueError('two distinct seeds outside the original DGM plan required')
        before = self.view(retained,dgm_fence,source_fence=source_fence)
        candidate = before.rank(candidates)[0]
        async def measure(selector):
            rows=[]
            for seed in seeds:
                self.view(retained,dgm_fence,source_fence=source_fence)
                rows.append(_metric(await run(replace(self.dgm.plan.config,seed=seed),
                                              replace(self.dgm.memory,selector=selector),source_fence=source_fence)))
            if not _valid_metrics(rows,self.dgm.plan.config.budget):
                raise IntegrityError('invalid assessment metrics')
            return rows
        incumbent_metrics=await measure(before.trusted_active)
        candidate_metrics=await measure(candidate)
        if self.view(retained,dgm_fence,source_fence=source_fence)!=before:
            raise IntegrityError('experience changed during assessment')
        return {'seeds':list(seeds),'incumbent':before.trusted_active.wire(),'candidate':candidate.wire(),
                'incumbent_metrics':incumbent_metrics,'candidate_metrics':candidate_metrics,
                'eligible_for_review':candidate!=before.trusted_active and _promote(incumbent_metrics,candidate_metrics),
                'release_authorized':False}
