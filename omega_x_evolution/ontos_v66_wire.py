"""Canonical bounded IPC envelope and idempotent logical receiver.

This contract is data-only. No native WIT, WASI, Zenoh or Rust message is
sent and no <1 ms latency is claimed. Checksum detects corruption but DOES
NOT authenticate a sender, sign capabilities, or prevent adversarial replay.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import base64
import binascii
import hashlib
import json
import re

_SCHEMA='ontos-ipc-v1'
_ID=re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
_CHANNELS=frozenset('ABCDE')
_KEYS=frozenset({'v','c','t','n','s','issued','expires','payload','checksum'})
_MAX_ENCODED=8192
_MAX_PAYLOAD=4096


@dataclass(frozen=True, slots=True)
class Envelope:
    schema: str
    channel: str
    tenant: str
    nonce: str
    sequence: int
    issued_at: int
    expires_at: int
    payload: bytes

    def __post_init__(self):
        if (type(self.schema) is not str or self.schema!=_SCHEMA
                or type(self.channel) is not str or self.channel not in _CHANNELS
                or any(type(x) is not str or _ID.fullmatch(x) is None
                       for x in (self.tenant,self.nonce))
                or type(self.sequence) is not int or not 0<=self.sequence<2**32
                or type(self.issued_at) is not int or not 0<=self.issued_at<2**63
                or type(self.expires_at) is not int or not self.issued_at<=self.expires_at<2**63
                or type(self.payload) is not bytes or len(self.payload)>_MAX_PAYLOAD):
            raise ValueError('IPC envelope contract')


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def _fields(msg: Envelope) -> dict:
    return {'v':msg.schema,'c':msg.channel,'t':msg.tenant,'n':msg.nonce,
            's':msg.sequence,'issued':msg.issued_at,'expires':msg.expires_at,
            'payload':base64.b64encode(msg.payload).decode('ascii')}


def encode(message: Envelope) -> bytes:
    if type(message) is not Envelope:
        raise ValueError('envelope required')
    message.__post_init__()
    obj=_fields(message)
    obj['checksum']=hashlib.sha256(_json_bytes(obj)).hexdigest()
    result=_json_bytes(obj)
    if len(result)>_MAX_ENCODED:
        raise ValueError('IPC wire size exceeded')
    return result


def decode(raw: bytes) -> Envelope:
    if type(raw) is not bytes or not 1<=len(raw)<=_MAX_ENCODED:
        raise ValueError('bounded wire bytes required')
    try:
        value=json.loads(raw)
        if type(value) is not dict or set(value)!=_KEYS:
            raise ValueError('wire key set')
        checksum=value.pop('checksum')
        if type(checksum) is not str or len(checksum)!=64:
            raise ValueError('checksum type')
        if hashlib.sha256(_json_bytes(value)).hexdigest()!=checksum:
            raise ValueError('checksum mismatch')
        if any(type(value[key]) is not str for key in ('v','c','t','n','payload')):
            raise ValueError('wire text type')
        if any(type(value[key]) is not int for key in ('s','issued','expires')):
            raise ValueError('wire integer type')
        payload=base64.b64decode(value['payload'],validate=True)
        msg=Envelope(value['v'],value['c'],value['t'],value['n'],
                     value['s'],value['issued'],value['expires'],payload)
        if encode(msg)!=raw:
            raise ValueError('noncanonical wire data')
        return msg
    except (UnicodeError,UnicodeDecodeError,ValueError,TypeError,KeyError,
            json.JSONDecodeError,binascii.Error,OverflowError) as exc:
        raise ValueError('invalid canonical wire payload') from exc


@dataclass(frozen=True, slots=True)
class Receiver:
    tenant: str
    next_sequence: int
    seen_nonces: tuple[str, ...] = ()
    last_tick: int = 0
    deliveries: int = 0

    def __post_init__(self) -> None:
        if (type(self.tenant) is not str or _ID.fullmatch(self.tenant) is None
                or type(self.next_sequence) is not int or not 0<=self.next_sequence<2**32
                or type(self.seen_nonces) is not tuple or len(self.seen_nonces)>1024
                or len(set(self.seen_nonces))!=len(self.seen_nonces)
                or any(type(x) is not str or _ID.fullmatch(x) is None for x in self.seen_nonces)
                or type(self.last_tick) is not int or not 0<=self.last_tick<2**63
                or type(self.deliveries) is not int or not 0<=self.deliveries<=1024
                or self.deliveries!=len(self.seen_nonces)):
            raise ValueError('receiver state contract')


def receive(state: Receiver, raw: bytes, *, at_tick: int) -> tuple[Receiver,dict]:
    if type(state) is not Receiver or type(at_tick) is not int or not 0<=at_tick<2**63:
        raise ValueError('bounded receiver tick and state required')
    state.__post_init__()
    def result(status: str,logical_age: int | None=None):
        return {'status':status,'native_rust_zenoh_wasi_verified':False,
                'observed_ipc_latency_ms':None,'logical_age_ticks':logical_age,
                'checksum_authenticates_sender':False}
    try:
        msg=decode(raw)
    except ValueError:
        return state,result('INVALID_FRAME')
    if at_tick<state.last_tick:
        return state,result('CLOCK_REGRESSION')
    if msg.tenant!=state.tenant:
        return state,result('TENANT_REJECTED')
    if msg.nonce in state.seen_nonces or msg.sequence<state.next_sequence:
        return state,result('REPLAY_REJECTED')
    if msg.sequence!=state.next_sequence:
        return state,result('OUT_OF_ORDER')
    if at_tick<msg.issued_at:
        return state,result('NOT_YET_VALID')
    if at_tick>msg.expires_at:
        return state,result('EXPIRED')
    if state.deliveries>=1024 or state.next_sequence == 2**32-1:
        return state,result('CAPACITY_EXHAUSTED')
    next_state=replace(state,next_sequence=state.next_sequence+1,
                       seen_nonces=state.seen_nonces+(msg.nonce,),
                       last_tick=at_tick,deliveries=state.deliveries+1)
    return next_state,result('DELIVERED_MODEL',at_tick-msg.issued_at)


def model_precommit_delivery(session, receiver: Receiver, raw: bytes,
                             *, at_tick: int) -> tuple[object, Receiver, dict]:
    """Atomic data-only connection from wire v66 to finite model v63.

    The sender is not authenticated, and an E:allow remains solely a
    MODEL_APPROVED label. Invalid frames are not consumed by the receiver.
    """
    from .ontos_v63_interface import Session, Frame, transition
    if type(session) is not Session or type(receiver) is not Receiver:
        raise ValueError('strict model state required')
    session.__post_init__()
    receiver.__post_init__()
    next_receiver,receipt=receive(receiver,raw,at_tick=at_tick)
    if receipt['status'] != 'DELIVERED_MODEL':
        return session,receiver,receipt
    try:
        msg=decode(raw)
        body=json.loads(msg.payload)
        if (type(body) is not dict or set(body)!= {'kind','cap','alarm'}
                or type(body['kind']) is not str
                or body['cap'] is not None and type(body['cap']) is not str
                or type(body['alarm']) is not bool
                or _json_bytes(body) != msg.payload):
            raise ValueError('noncanonical or invalid frame payload')
        candidate=Frame(msg.channel,body['kind'],msg.nonce,at_tick,
                        body['cap'],body['alarm'])
        next_session=transition(session,candidate)
    except (ValueError,TypeError,KeyError,UnicodeError):
        return session,receiver,{**receipt,'status':'POLICY_REJECTED'}
    return next_session,next_receiver,{**receipt,'status':'COMMITTED_TO_MODEL',
                                       'operational_capabilities_granted':False}
