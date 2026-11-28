"""Opt-in checkpoint freshness relative to an independently retained pin.

The caller must keep the newest pin outside the checkpoint's rollback domain.
If a crash commits the database but loses its new pin, reopening fails closed;
there is deliberately no automatic trust-on-first-use recovery from that DB.
"""
from __future__ import annotations

from dataclasses import dataclass
import hmac

from .checkpoint import CheckpointError, CheckpointStore


@dataclass(frozen=True, slots=True)
class CheckpointPin:
    run_id: bytes
    generation: int
    mac: bytes

    def __post_init__(self):
        if (type(self.run_id) is not bytes or len(self.run_id) != 32
                or type(self.generation) is not int or not 0 <= self.generation < 2**63
                or type(self.mac) is not bytes or len(self.mac) != 32):
            raise ValueError('invalid independent checkpoint pin')


class FencedCheckpointStore(CheckpointStore):
    """CheckpointStore-compatible explicit pin admission, with run-scoped MAC.

    One instance is owned by one engine invocation; cooperating independent
    instances use the underlying generation/MAC CAS. Pins are not self-issued
    freshness evidence: persist each committed pin in a separate trust domain.
    """
    def __init__(self, path, key, *, run_id: bytes, retained: CheckpointPin | None = None):
        if type(run_id) is not bytes or len(run_id) != 32:
            raise ValueError('independent 256-bit run ID required')
        if retained is not None:
            if type(retained) is not CheckpointPin or retained.run_id != run_id:
                raise ValueError('checkpoint pin run mismatch')
            retained.__post_init__()
        super().__init__(path,key)
        self._run_id = run_id
        self._pin = retained

    @property
    def pin(self) -> CheckpointPin | None:
        return self._pin

    def _mac(self, generation, payload):
        scoped_key = hmac.digest(self._key, b'OMEGA-X/fenced-checkpoint/v1\x00'+self._run_id, 'sha256')
        return hmac.digest(scoped_key, b'generation\x00'+generation.to_bytes(8,'big')+payload, 'sha256')

    def _advance(self):
        generation, mac = self._expected
        self._pin = CheckpointPin(self._run_id,generation,mac)

    def initialize(self,state):
        if self._pin is not None:
            raise CheckpointError('cannot initialize with a retained pin')
        super().initialize(state)
        self._advance()

    def load(self):
        self._expected = None
        if self._pin is None:
            raise CheckpointError('independent checkpoint pin required')
        try:
            generation,state = super().load()
            if (generation != self._pin.generation
                    or not hmac.compare_digest(self._expected[1],self._pin.mac)):
                raise CheckpointError('checkpoint differs from retained pin')
            return generation,state
        except BaseException:
            self._expected = None
            raise

    def save(self,generation,state):
        if (self._pin is None or self._expected != (self._pin.generation,self._pin.mac)
                or type(generation) is not int or not 0 < generation < 2**63):
            raise CheckpointError('validated checkpoint pin required for save')
        super().save(generation,state)
        self._advance()


async def run_fenced_memory(cfg, proposal, *, source_fence, checkpoint,
                            resume=False, evaluation_processes=1):
    """Opt-in dual-fenced engine entry point; no release or continuous lease.

    The supervisor supplies the independently retained source fence, not a value
    recovered from the proposal or from a restored source database.
    """
    from .engine import run
    from .engine_memory import MemoryProposal
    from .ontos_epoch_journal_core import IntegrityError
    from .ontos_managed_journal import Fence

    from .durable_checkpoint import DurableCheckpointStore

    if type(proposal) is not MemoryProposal or type(checkpoint) not in (FencedCheckpointStore, DurableCheckpointStore):
        raise ValueError('typed memory proposal and fenced checkpoint required')
    if type(source_fence) is not Fence or source_fence != proposal.retained:
        raise IntegrityError('independently retained source fence mismatch')
    source_fence.__post_init__()
    return await run(cfg, proposal, checkpoint=checkpoint, resume=resume,
                     evaluation_processes=evaluation_processes)
