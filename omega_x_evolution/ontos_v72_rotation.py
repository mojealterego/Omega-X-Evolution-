"""Authenticated planned key handoff for the v72 monotonic witness.

Clients must persist the returned epoch pin in an independently trusted
rollback-resistant domain before switching to it. The old service must be
quiesced during cutover. This verifier does not revoke keys in other clients,
recover a lost signing authority, or provision an operational TCB.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256

from .ontos_v72_checkpoint_note import verify_note
from .ontos_v72_jcs import canonical_json
from .ontos_v72_receipts import _prime_order_point, strict_verify
from .ontos_v72_witness import WitnessPolicy, WitnessReceipt, verify_witness, verify_witness_transition

_DOMAIN = b'OMEGA-X/v72/witness-rotation/v1\x00'
_MAX_EPOCH = 2**31-1
_MAX_RETIRED = 128


def _receipt_digest(receipt: WitnessReceipt) -> str:
    if (type(receipt) is not WitnessReceipt or type(receipt.revision) is not int
            or not 0 <= receipt.revision < 2**63 or type(receipt.note) is not bytes
            or not 1 <= len(receipt.note) <= 1024 or type(receipt.challenge) is not bytes
            or len(receipt.challenge) != 32 or type(receipt.signature) is not bytes
            or len(receipt.signature) != 64):
        raise ValueError('bounded witness receipt required')
    return sha256(canonical_json({'revision':str(receipt.revision),
        'note_sha256':sha256(receipt.note).hexdigest(), 'challenge':receipt.challenge.hex(),
        'signature':receipt.signature.hex()})).hexdigest()


@dataclass(frozen=True, slots=True)
class EpochPin:
    epoch: int
    policy: WitnessPolicy
    authority_key: bytes
    receipt: WitnessReceipt
    retired_keys: tuple[bytes, ...]

    def __post_init__(self) -> None:
        if (type(self.epoch) is not int or not 0 <= self.epoch <= _MAX_EPOCH
                or type(self.policy) is not WitnessPolicy or not _prime_order_point(self.authority_key)
                or type(self.retired_keys) is not tuple or len(self.retired_keys)>_MAX_RETIRED
                or any(not _prime_order_point(k) for k in self.retired_keys)
                or tuple(sorted(set(self.retired_keys))) != self.retired_keys):
            raise ValueError('invalid trusted epoch pin')
        self.policy.__post_init__()
        active = (self.authority_key,self.policy.log_key,self.policy.witness_key)
        if len(set(active)) != 3 or set(active).intersection(self.retired_keys):
            raise ValueError('authority, log and witness keys must be distinct and not retired')
        _receipt_digest(self.receipt)
        if not verify_witness(self.receipt,self.policy,self.receipt.challenge):
            raise ValueError('epoch pin requires authenticated receipt')

    def digest(self) -> str:
        self.__post_init__()
        return sha256(canonical_json({'epoch':self.epoch,'policy':self.policy.digest().hex(),
            'authority_key':self.authority_key.hex(),'receipt_sha256':_receipt_digest(self.receipt),
            'retired_keys':[k.hex() for k in self.retired_keys]})).hexdigest()


def rotation_bytes(current: EpochPin, proposed: WitnessPolicy, old_tip: WitnessReceipt,
                   new_tip: WitnessReceipt, challenge: bytes) -> bytes:
    """Exact certificate preimage for an offline, independently pinned authority."""
    if (type(current) is not EpochPin or type(proposed) is not WitnessPolicy
            or type(challenge) is not bytes or len(challenge)!=32 or current.epoch==_MAX_EPOCH):
        raise ValueError('bounded next-epoch certificate required')
    return _DOMAIN + canonical_json({'previous_pin_sha256':current.digest(),
        'next_epoch':current.epoch+1,'next_policy_sha256':proposed.digest().hex(),
        'old_tip_sha256':_receipt_digest(old_tip),'new_tip_sha256':_receipt_digest(new_tip),
        'challenge':challenge.hex()})


def rotate_epoch(current: EpochPin, proposed: WitnessPolicy, old_tip: WitnessReceipt,
                 new_tip: WitnessReceipt, proof: tuple[bytes,...], *, challenge: bytes,
                 authority_signature: bytes) -> EpochPin | None:
    """Verify routine handoff with both witnesses, both log notes and offline approval.

    The old tip must extend the retained pin. New storage starts at revision
    zero with exactly that tree size/root. The epoch, not local revision,
    distinguishes the two stores. Retired keys cannot become active again.
    """
    try:
        message = rotation_bytes(current,proposed,old_tip,new_tip,challenge)
        old = current.policy
        if (challenge==current.receipt.challenge or proposed.environment!=old.environment
                or proposed.origin!=old.origin or proposed.digest()==old.digest()
                or proposed.log_key==old.witness_key or proposed.witness_key==old.log_key
                or current.authority_key in (proposed.log_key,proposed.witness_key)
                or proposed.log_key in current.retired_keys or proposed.witness_key in current.retired_keys
                or proposed.log_key==old.log_key and proposed.log_name!=old.log_name
                or new_tip.revision!=0):
            return None
        retired = tuple(sorted(set(current.retired_keys) | ({old.log_key,old.witness_key}
                          - {proposed.log_key,proposed.witness_key})))
        if len(retired)>_MAX_RETIRED or not strict_verify(current.authority_key,message,authority_signature):
            return None
        if not verify_witness_transition(old_tip,old,challenge,current.receipt,proof):
            return None
        if not verify_witness(new_tip,proposed,challenge):
            return None
        before = verify_note(old_tip.note,expected_origin=old.origin,
                             trusted_key_name=old.log_name,trusted_public_key=old.log_key)
        after = verify_note(new_tip.note,expected_origin=proposed.origin,
                            trusted_key_name=proposed.log_name,trusted_public_key=proposed.log_key)
        if before is None or before!=after:
            return None
        return EpochPin(current.epoch+1,proposed,current.authority_key,new_tip,retired)
    except (ValueError,TypeError,OverflowError,RecursionError):
        return None


def advance_pin(current: EpochPin, receipt: WitnessReceipt, proof: tuple[bytes,...], *,
                challenge: bytes) -> EpochPin | None:
    """Accept an authenticated append or unchanged fresh read in the current epoch."""
    try:
        if type(current) is not EpochPin or type(challenge) is not bytes or len(challenge)!=32:
            return None
        current.__post_init__()
        _receipt_digest(receipt)
        if challenge==current.receipt.challenge or not verify_witness_transition(
                receipt,current.policy,challenge,current.receipt,proof):
            return None
        return replace(current,receipt=receipt)
    except (ValueError,TypeError,OverflowError,RecursionError):
        return None
