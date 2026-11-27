"""Signed replay of the existing v63/v66 finite A-E model.

No OS authority, operational capability or tool execution. A/C/D are object
messages; B/E require the independently pinned auditor key. Logical clocks
are signed but not independently measured. A retained exact head detects
truncation relative to that head, not concurrent forks or joint rollback.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from .ontos_v63_interface import CAPABILITIES, Session
from .ontos_v66_wire import Receiver, decode, model_precommit_delivery
from .ontos_v72_jcs import canonical_json
from .ontos_v72_receipts import _prime_order_point, strict_verify

_DOMAIN=b'OMEGA-X/v63/authenticated-model/v1\x00'
_HEX=re.compile(r'[0-9a-f]{64}\Z')
_NAME=re.compile(r'[A-Za-z0-9_-]{1,64}\Z')


def _sha(value: object) -> bool:
    return type(value) is str and _HEX.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class BoundaryPlan:
    tenant: str
    session_id: str
    root_caps: frozenset[str]
    deadline: int
    object_key: bytes
    auditor_key: bytes

    def __post_init__(self):
        if (type(self.tenant) is not str or _NAME.fullmatch(self.tenant) is None
                or not _sha(self.session_id) or type(self.root_caps) is not frozenset
                or not self.root_caps <= CAPABILITIES
                or type(self.deadline) is not int or not 1 <= self.deadline <= 1_000_000
                or not _prime_order_point(self.object_key) or not _prime_order_point(self.auditor_key)
                or self.object_key == self.auditor_key):
            raise ValueError('invalid independent role pins and model genesis')

    @property
    def sha256(self) -> str:
        self.__post_init__()
        body={'tenant':self.tenant,'session':self.session_id,'root_caps':sorted(self.root_caps),
              'deadline':self.deadline,'object_key':self.object_key.hex(),'auditor_key':self.auditor_key.hex(),
              'object_channels':'ACD','auditor_channels':'BE'}
        return hashlib.sha256(_DOMAIN+b'plan\x00'+canonical_json(body)).hexdigest()


def signing_payload(plan_sha256: str, previous: str, at_tick: int, raw: bytes) -> bytes:
    """Fixed domain and unambiguous binary framing of a canonical v66 packet."""
    if (not _sha(plan_sha256) or not _sha(previous) or type(at_tick) is not int
            or not 0 <= at_tick < 2**63 or type(raw) is not bytes or not 1 <= len(raw) <= 8192):
        raise ValueError('bounded signed wire envelope')
    decode(raw)
    return (_DOMAIN+b'frame\x00'+bytes.fromhex(plan_sha256)+bytes.fromhex(previous)
            +at_tick.to_bytes(8,'big')+len(raw).to_bytes(2,'big')+raw)


@dataclass(frozen=True, slots=True)
class SignedEnvelope:
    previous: str
    at_tick: int
    raw: bytes
    signature: bytes

    def sha256(self, plan_sha256: str) -> str:
        if type(self.signature) is not bytes or len(self.signature)!=64:
            raise ValueError('invalid signature shape')
        body=signing_payload(plan_sha256,self.previous,self.at_tick,self.raw)
        return hashlib.sha256(_DOMAIN+b'link\x00'+body+self.signature).hexdigest()


@dataclass(frozen=True, slots=True)
class BoundaryReview:
    session: Session
    receiver: Receiver
    head: str
    retained_head_verified: bool


def replay_boundary(plan: BoundaryPlan, expected_plan_sha256: str,
                    messages: tuple[SignedEnvelope, ...], *,
                    expected_head: str | None = None) -> BoundaryReview:
    """All-or-nothing authenticated reconstruction, never a native grant.

    Only the actual v63/v66 reducer determines accepted model transitions.
    No caller-supplied state, sender key, capability expansion or unsigned
    event can enter the replay. Pin retention/custody is external.
    """
    if type(plan) is not BoundaryPlan or not _sha(expected_plan_sha256):
        raise ValueError('independently pinned plan required')
    pin=plan.sha256
    if (pin!=expected_plan_sha256 or type(messages) is not tuple or len(messages)>256
            or expected_head is not None and not _sha(expected_head)):
        raise ValueError('model replay bounds or plan mismatch')
    session=Session(plan.root_caps,plan.root_caps,plan.deadline)
    receiver=Receiver(plan.tenant,0)
    head=pin
    for msg in messages:
        if type(msg) is not SignedEnvelope or msg.previous!=head:
            raise ValueError('noncontiguous authenticated wire history')
        body=signing_payload(pin,head,msg.at_tick,msg.raw)
        envelope=decode(msg.raw)
        key=plan.auditor_key if envelope.channel in ('B','E') else plan.object_key
        if not strict_verify(key,body,msg.signature):
            raise ValueError('invalid role signature')
        next_session,next_receiver,receipt=model_precommit_delivery(session,receiver,msg.raw,at_tick=msg.at_tick)
        if receipt['status']!='COMMITTED_TO_MODEL' or not next_session.caps<=session.caps:
            raise ValueError('authenticated model transition rejected: '+receipt['status'])
        session,receiver=next_session,next_receiver
        head=msg.sha256(pin)
    if expected_head is not None and head!=expected_head:
        raise ValueError('retained exact head mismatch')
    return BoundaryReview(session,receiver,head,expected_head is not None)
