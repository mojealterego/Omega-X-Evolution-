"""Fixed 3-of-4 witness quorum using actual monotonic v72 stores.

Safety assumes at most one faulty witness (including rollback of its store),
fixed externally pinned membership, independent administration and no bypass
of the trusted store. Not a consensus protocol or a membership-change service.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from .ontos_v72_checkpoint_note import Checkpoint, _name, verify_note
from .ontos_v72_jcs import canonical_json
from .ontos_v72_merkle import leaf_hash, verify_consistency, verify_inclusion
from .ontos_v72_receipts import _prime_order_point
from .ontos_v72_witness import WitnessPolicy, WitnessReceipt, WitnessStore, verify_witness

QUORUM = 3
MEMBERS = 4
_DOMAIN = b'OMEGA-X/v72/witness-quorum/v1\x00'


@dataclass(frozen=True, slots=True)
class QuorumPolicy:
    environment: str
    origin: str
    log_name: str
    log_key: bytes
    epoch: int
    witness_keys: tuple[bytes, ...]

    def __post_init__(self) -> None:
        _name(self.origin)
        _name(self.log_name)
        if (type(self.environment) is not str or self.environment not in ('simulation','operational')
                or type(self.epoch) is not int or not 0<=self.epoch<2**31
                or not _prime_order_point(self.log_key) or type(self.witness_keys) is not tuple
                or len(self.witness_keys)!=MEMBERS or not all(_prime_order_point(k) for k in self.witness_keys)
                or tuple(sorted(set(self.witness_keys)))!=self.witness_keys or self.log_key in self.witness_keys):
            raise ValueError('four distinct pinned witness keys, epoch and log required')

    def digest(self) -> bytes:
        self.__post_init__()
        return sha256(canonical_json({'schema':'omega-v72-quorum-v1','environment':self.environment,
            'origin':self.origin,'log_name':self.log_name,'log_key':self.log_key.hex(),
            'epoch':self.epoch,'witness_keys':[k.hex() for k in self.witness_keys],
            'threshold':QUORUM})).digest()

    def member(self,key: bytes) -> WitnessPolicy:
        self.__post_init__()
        if type(key) is not bytes or key not in self.witness_keys:
            raise ValueError('unregistered witness key')
        return WitnessPolicy(self.environment,self.origin,self.log_name,self.log_key,key)


def quorum_challenge(policy: QuorumPolicy, challenge: bytes) -> bytes:
    if type(policy) is not QuorumPolicy or type(challenge) is not bytes or len(challenge)!=32:
        raise ValueError('pinned policy and fresh 32-byte challenge required')
    return sha256(_DOMAIN+policy.digest()+challenge).digest()


@dataclass(frozen=True, slots=True)
class Vote:
    witness_key: bytes
    receipt: WitnessReceipt


@dataclass(frozen=True, slots=True)
class QuorumCertificate:
    note: bytes
    votes: tuple[Vote,...]
    consistency: tuple[bytes,...]


class QuorumWitness:
    """One separately administered native WitnessStore; no shared mutable state."""

    def __init__(self,path: Path,policy: QuorumPolicy,signer: Ed25519PrivateKey):
        if type(policy) is not QuorumPolicy or not isinstance(signer,Ed25519PrivateKey):
            raise ValueError('pinned roster and native key required')
        self._key=signer.public_key().public_bytes_raw()
        self._policy=policy
        self._pin=policy.digest()
        self._store=WitnessStore(path,policy.member(self._key),signer)

    @classmethod
    def initialize(cls,path: Path,policy: QuorumPolicy,signer: Ed25519PrivateKey,genesis_note: bytes):
        if type(policy) is not QuorumPolicy or not isinstance(signer,Ed25519PrivateKey):
            raise ValueError('pinned roster and native key required')
        WitnessStore.initialize(path,policy.member(signer.public_key().public_bytes_raw()),signer,genesis_note)
        return cls(path,policy,signer)

    def current(self,challenge: bytes) -> Vote:
        if self._policy.digest()!=self._pin:
            raise ValueError('witness roster changed')
        return Vote(self._key,self._store.read(quorum_challenge(self._policy,challenge)))

    def vote(self,note: bytes,proof: tuple[bytes,...],*,expected_revision: int,challenge: bytes) -> Vote | None:
        # Validate the challenge before mutating durable state.
        if self._policy.digest()!=self._pin:
            raise ValueError('witness roster changed')
        quorum_challenge(self._policy,challenge)
        status=self._store.advance(note,proof,expected_revision=expected_revision)
        if status not in ('ADVANCED','UNCHANGED'):
            return None
        vote=self.current(challenge)
        # A competing append may have advanced the store before read(). Never
        # present that newer receipt as a vote for the originally requested note.
        return vote if vote.receipt.note==note else None


def verify_quorum(policy: QuorumPolicy, previous: Checkpoint, challenge: bytes,
                  certificate: QuorumCertificate) -> Checkpoint | None:
    """Authenticate at least 3 distinct members on one exact note and prior pin.

    Caller must retain the previously accepted checkpoint independently and
    generate an unpredictable fresh challenge. Each member's local revision
    is authenticated, but revisions are not comparable across witnesses.
    """
    try:
        if (type(policy) is not QuorumPolicy or type(previous) is not Checkpoint
                or type(certificate) is not QuorumCertificate or type(certificate.votes) is not tuple
                or not QUORUM<=len(certificate.votes)<=MEMBERS):
            return None
        previous.__post_init__()
        ch=quorum_challenge(policy,challenge)
        if previous.origin!=policy.origin:
            return None
        checkpoint=verify_note(certificate.note,expected_origin=policy.origin,
                               trusted_key_name=policy.log_name,trusted_public_key=policy.log_key)
        if checkpoint is None or not verify_consistency(previous.tree_size,checkpoint.tree_size,
                previous.root,checkpoint.root,certificate.consistency):
            return None
        seen=set()
        for vote in certificate.votes:
            if (type(vote) is not Vote or type(vote.witness_key) is not bytes
                    or vote.witness_key in seen or type(vote.receipt) is not WitnessReceipt
                    or vote.receipt.note!=certificate.note
                    or not verify_witness(vote.receipt,policy.member(vote.witness_key),ch)):
                return None
            seen.add(vote.witness_key)
        return checkpoint
    except (ValueError,TypeError,OverflowError,RecursionError):
        return None


def verify_quorum_review(data: bytes,policy: QuorumPolicy,previous: Checkpoint,challenge: bytes,
                         certificate: QuorumCertificate,inclusion: tuple[bytes,...],
                         evaluator_keys: tuple[bytes,...]) -> bool:
    """Quorum-backed v75 review-leaf contract, separate from gate reduction.

    The caller must compute the exact authenticated review leaf from v75;
    this function does not verify evaluator receipts or authorize release.
    """
    try:
        if (type(policy) is not QuorumPolicy or policy.environment!='operational'
                or type(evaluator_keys) is not tuple or not 1<=len(evaluator_keys)<=8
                or any(not _prime_order_point(k) for k in evaluator_keys)
                or any(k==policy.log_key or k in policy.witness_keys for k in evaluator_keys)):
            return False
        checkpoint=verify_quorum(policy,previous,challenge,certificate)
        return (checkpoint is not None and checkpoint.tree_size>0 and verify_inclusion(
            leaf_hash(data),checkpoint.tree_size-1,checkpoint.tree_size,inclusion,checkpoint.root))
    except (ValueError,TypeError,OverflowError,RecursionError):
        return False
