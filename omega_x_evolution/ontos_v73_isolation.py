"""v73 authenticated finite A-E boundary, not an operating-system sandbox.

The trusted host provisions distinct T_obj and T_ext public keys, a unique
session ID, and the logical clock. Candidate code is never executed here.
A-D represent object-side ingress in this finite profile; E belongs to T_ext.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from threading import Lock

from .ontos_v63_interface import Session
from .ontos_v66_wire import Receiver, decode, model_precommit_delivery
from .ontos_v72_jcs import canonical_json
from .ontos_v72_receipts import _prime_order_point, strict_verify

_DOMAIN = b'OMEGA-X/v73/A-E/frame\x00'
_INIT = b'OMEGA-X/v73/A-E/init\x00'
_NEXT = b'OMEGA-X/v73/A-E/next\x00'
_MAX_WIRE = 8192


def signing_bytes(session_id: bytes, history: bytes, raw: bytes) -> bytes:
    if (type(session_id) is not bytes or len(session_id) != 32
            or type(history) is not bytes or len(history) != 32
            or type(raw) is not bytes or not 1 <= len(raw) <= _MAX_WIRE):
        raise ValueError('bounded session, history and wire bytes required')
    return _DOMAIN + session_id + history + raw


@dataclass(frozen=True, slots=True)
class Snapshot:
    phase: str
    caps: frozenset[str]
    next_sequence: int
    history: bytes
    operational_capabilities_granted: bool = False


class IsolationGateway:
    """Atomic authenticated delivery to the existing model, no real capabilities."""

    def __init__(self, *, tenant: str, session_id: bytes, root_caps: frozenset[str],
                 deadline: int, object_key: bytes, external_key: bytes) -> None:
        if (type(session_id) is not bytes or len(session_id) != 32
                or not _prime_order_point(object_key)
                or not _prime_order_point(external_key) or object_key == external_key):
            raise ValueError('distinct valid authority keys and session ID required')
        self._session = Session(root_caps, root_caps, deadline)
        self._receiver = Receiver(tenant, 0)
        self._session_id = session_id
        self._object_key = object_key
        self._external_key = external_key
        self._history = hashlib.sha256(_INIT + session_id + object_key + external_key
            + canonical_json({'tenant': tenant, 'deadline': deadline,
                              'root_caps': sorted(root_caps)})).digest()
        self._lock = Lock()

    @property
    def session_id(self) -> bytes:
        return self._session_id

    def snapshot(self) -> Snapshot:
        with self._lock:
            return Snapshot(self._session.phase, self._session.caps,
                            self._receiver.next_sequence, self._history)

    def submit(self, raw: bytes, signature: bytes, *, at_tick: int) -> str:
        if type(at_tick) is not int or not 0 <= at_tick < 2**63:
            return 'INVALID_TICK'
        if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_WIRE:
            return 'INVALID_FRAME'
        with self._lock:
            try:
                msg = decode(raw)
            except (ValueError, RecursionError):
                return 'INVALID_FRAME'
            key = self._external_key if msg.channel == 'E' else self._object_key
            preimage = signing_bytes(self._session_id, self._history, raw)
            if not strict_verify(key, preimage, signature):
                return 'UNAUTHENTICATED'
            try:
                session, receiver, receipt = model_precommit_delivery(
                    self._session, self._receiver, raw, at_tick=at_tick)
            except (ValueError, RecursionError):
                return 'POLICY_REJECTED'
            if receipt['status'] != 'COMMITTED_TO_MODEL':
                return receipt['status']
            # Commit the protocol state and exact signed history together.
            history = hashlib.sha256(_NEXT + self._history + at_tick.to_bytes(8, 'big') + raw + signature).digest()
            self._session, self._receiver, self._history = session, receiver, history
            return 'COMMITTED_TO_MODEL'
