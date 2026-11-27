"""Finite pre-commit A-E interface state machine with no operating capabilities.

All grants here are simulated labels. No token issuer, trust root, IO or
external evaluator exists inside this module. The root set is immutable and
active caps can only shrink, including after logical restart.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import re

CAPABILITIES = frozenset({'sense', 'remember', 'compute'})
CHANNEL_KINDS = {
    'A': frozenset({'observe'}),
    'B': frozenset({'assess', 'alarm'}),
    'C': frozenset({'propose'}),
    'D': frozenset({'propose'}),
    'E': frozenset({'allow', 'veto', 'restart', 'timeout'}),
}
PHASES = frozenset({'IDLE', 'OBSERVED', 'ASSESSED', 'PROPOSED_C',
                    'PROPOSED_D', 'MODEL_APPROVED', 'LOCKDOWN'})
_NONCE = re.compile(r'[a-zA-Z0-9_-]{1,64}\Z')


@dataclass(frozen=True, slots=True)
class Frame:
    channel: str
    kind: str
    nonce: str
    tick: int
    cap: str | None = None
    alarm: bool = False

    def __post_init__(self) -> None:
        if (type(self.channel) is not str or self.channel not in CHANNEL_KINDS
                or type(self.kind) is not str or self.kind not in CHANNEL_KINDS[self.channel]
                or type(self.nonce) is not str or _NONCE.fullmatch(self.nonce) is None
                or type(self.tick) is not int or not 0 <= self.tick < 2**63
                or type(self.alarm) is not bool
                or (self.cap is not None and (type(self.cap) is not str or self.cap not in CAPABILITIES))
                or (self.cap is not None) != (self.channel in ('C', 'D') and self.kind == 'propose' or self.channel == 'E' and self.kind == 'allow')
                or (self.alarm != (self.channel == 'B' and self.kind == 'alarm'))):
            raise ValueError('invalid finite A-E frame')


@dataclass(frozen=True, slots=True)
class Session:
    root_caps: frozenset[str]
    caps: frozenset[str]
    deadline: int
    phase: str = 'IDLE'
    last_tick: int = 0
    seen_nonces: tuple[str, ...] = ()
    audit: tuple[str, ...] = ()
    pending_cap: str | None = None

    @property
    def operational_capabilities_granted(self) -> bool:
        return False

    def __post_init__(self) -> None:
        if (type(self.root_caps) is not frozenset or type(self.caps) is not frozenset
                or not self.root_caps <= CAPABILITIES or not self.caps <= self.root_caps
                or type(self.deadline) is not int or not 1 <= self.deadline <= 1_000_000
                or type(self.last_tick) is not int or not 0 <= self.last_tick < 2**63
                or type(self.phase) is not str or self.phase not in PHASES
                or type(self.seen_nonces) is not tuple or type(self.audit) is not tuple
                or len(self.seen_nonces) != len(self.audit) or len(self.seen_nonces) > 256
                or len(set(self.seen_nonces)) != len(self.seen_nonces)
                or any(type(x) is not str or _NONCE.fullmatch(x) is None for x in self.seen_nonces)
                or any(type(x) is not str or len(x) > 90 for x in self.audit)
                or (self.pending_cap is not None and self.pending_cap not in self.caps)
                or (self.pending_cap is None) != (self.phase not in ('PROPOSED_C', 'PROPOSED_D'))
                or (self.phase == 'LOCKDOWN' and self.caps)):
            raise ValueError('corrupted model-only session')


def transition(state: Session, frame: Frame) -> Session:
    if type(state) is not Session or type(frame) is not Frame:
        raise ValueError('validated state and frame required')
    state.__post_init__()
    frame.__post_init__()
    if len(state.audit) >= 256 or frame.nonce in state.seen_nonces or frame.tick < state.last_tick:
        raise ValueError('replay, time regression or audit budget')

    record = f'{frame.channel}:{frame.kind}:{frame.nonce}'
    base = dict(last_tick=frame.tick, seen_nonces=state.seen_nonces + (frame.nonce,),
                audit=state.audit + (record,))
    # Valid alarms are hard vetoes in every phase, not only OBSERVED.
    if frame.tick > state.deadline or frame.kind in ('veto', 'timeout', 'alarm'):
        return replace(state, **base, caps=frozenset(), phase='LOCKDOWN', pending_cap=None)
    if frame.kind == 'restart':
        return replace(state, **base, phase='LOCKDOWN' if state.phase == 'LOCKDOWN' else 'IDLE',
                       pending_cap=None)
    if state.phase == 'LOCKDOWN':
        raise ValueError('fail-closed lockdown state')
    if frame.channel == 'A' and state.phase == 'IDLE':
        return replace(state, **base, phase='OBSERVED')
    if frame.channel == 'B' and state.phase == 'OBSERVED':
        return replace(state, **base, phase='ASSESSED')
    if frame.channel in ('C', 'D') and state.phase == 'ASSESSED':
        if frame.cap not in state.caps:
            raise ValueError('proposal cannot expand cap set')
        return replace(state, **base, phase='PROPOSED_' + frame.channel, pending_cap=frame.cap)
    if frame.channel == 'E' and frame.kind == 'allow' and state.phase in ('PROPOSED_C', 'PROPOSED_D'):
        if frame.cap != state.pending_cap:
            raise ValueError('approval must bind exact pending capability')
        return replace(state, **base, caps=state.caps & {frame.cap}, phase='MODEL_APPROVED',
                       pending_cap=None)
    raise ValueError('invalid A-E protocol ordering')


def run_sequence(state: Session, frames: tuple[Frame, ...]) -> Session:
    if type(frames) is not tuple or len(frames) > 256:
        raise ValueError('bounded frame sequence required')
    result = state
    for frame in frames:
        result = transition(result, frame)
    return result
