"""Bounded R2 index, R3 checkpoint replay and one-shot R4 local release.

Derived plaintext is ephemeral; returned data cannot be recalled. Trusted local
supervisor retains both fences, clocks, and one ledger per provisioned vault.
No network dispatch, arbitrary operator execution or deep model unlearning.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

from .ontos_otce import Read, read_bytes, _name, _pin, _time, _int
from .ontos_sealed_otce import SealedOTCEJournal
from .ontos_managed_journal import ManagedJournal, Fence
from .ontos_epoch_journal_core import IntegrityError
from .ontos_v72_jcs import canonical_json, parse_json
from .ontos_v72_receipts import strict_verify

DOMAIN=b'OMEGA-X/RCC-operators/v1\x00'
MAX_RELEASES=16


@dataclass(frozen=True, slots=True)
class Index:
    postings: tuple[tuple[str,tuple[str,...]],...]
    sources: tuple[str,...]


@dataclass(frozen=True, slots=True)
class Checkpoint:
    scope: str
    prefix: tuple[str,...]
    weights: tuple[int,...]


@dataclass(frozen=True, slots=True)
class Model:
    checkpoint: Checkpoint
    reused: int


def _train(weights, rows):
    for _,x,y in rows:
        label=1 if y>0 else -1
        if label*sum(a*b for a,b in zip(weights,x))<=0:
            weights=tuple(a+label*b for a,b in zip(weights,x))
    return weights


@dataclass(frozen=True, slots=True)
class Permit:
    nonce: str
    recipient: str
    digest: str
    issued: int
    expires: int
    signature: bytes


def permit_bytes(pin,j,r,g):
    if (not _pin(pin) or type(g) is not Permit or not _pin(g.nonce) or not _name(g.recipient)
            or not _pin(g.digest) or not _time(g.issued) or not _time(g.expires)
            or not 0<g.expires-g.issued<=64 or type(g.signature) is not bytes or len(g.signature)!=64):
        raise ValueError('invalid release permit')
    token=sha256(read_bytes(j._scope,r)+r.signature).hexdigest()
    return DOMAIN+canonical_json([pin,j._state_pin(),g.nonce,g.recipient,g.digest,g.issued,g.expires,token])


@dataclass(frozen=True, slots=True)
class Release:
    status: str
    fence: Fence | None
    payload: bytes | None


class ExportLedger:
    """Separate fenced receipt journal; signed permits are consumed at most once."""
    def __init__(self,anchor,segments,j,approver):
        if (type(j) is not OperatorJournal or type(approver) is not bytes or len(approver)!=32
                or approver in (j._scope.writer,j._scope.revoker,j._scope.reader)):
            raise ValueError('independent release approver required')
        dirs=[Path(anchor).parent.resolve(),Path(segments).resolve(),j._vault_path.parent.resolve(),
              j._journal.anchor.parent.resolve(),j._journal.segments]
        if any(a==b or a in b.parents or b in a.parents for i,a in enumerate(dirs) for b in dirs[i+1:]):
            raise ValueError('separate trust directories required')
        self.approver=approver
        self.source=j._state_pin()
        self.pin=sha256(DOMAIN+canonical_json([self.source,approver.hex()])).hexdigest()
        self._journal=ManagedJournal(anchor,segments,self._hash,self._replay,self._encode,self._decode)

    def _encode(self,rows):
        if type(rows) is not tuple or len(rows)>MAX_RELEASES: raise ValueError('receipt budget')
        return canonical_json([self.pin,[x.hex() for x in rows]])

    def _hash(self,rows): return sha256(DOMAIN+self._encode(rows)).digest()

    def _receipt(self,raw):
        preimage,sig=parse_json(raw)
        if canonical_json([preimage,sig])!=raw: raise ValueError('noncanonical receipt')
        preimage=bytes.fromhex(preimage); sig=bytes.fromhex(sig)
        if not preimage.startswith(DOMAIN) or len(sig)!=64: raise ValueError('receipt domain')
        fields=parse_json(preimage[len(DOMAIN):])
        pin,source,nonce,recipient,digest,issued,expires,token=fields
        if (canonical_json(fields)!=preimage[len(DOMAIN):] or pin!=self.pin or source!=self.source
                or not all(_pin(x) for x in (nonce,digest,token)) or not _name(recipient)
                or not _time(issued) or not _time(expires) or not 0<expires-issued<=64
                or not strict_verify(self.approver,preimage,sig)):
            raise ValueError('invalid signed receipt')
        return nonce

    def _decode(self,raw):
        pin,rows=parse_json(raw)
        if pin!=self.pin or type(rows) is not list or len(rows)>MAX_RELEASES: raise ValueError('ledger scope')
        rows=tuple(bytes.fromhex(x) for x in rows)
        if self._encode(rows)!=raw or len({self._receipt(x) for x in rows})!=len(rows):
            raise ValueError('receipt integrity')
        return rows

    def _replay(self,rows,raw):
        try:
            if len(rows)>=MAX_RELEASES or self._receipt(raw) in {self._receipt(x) for x in rows}: return None
            return rows+(raw,)
        except (ValueError,TypeError,AttributeError): return None

    def initialize(self): return self._journal.initialize(()).fence

    def read(self,retained):
        if type(retained) is not Fence: raise ValueError('independent receipt fence required')
        return tuple(self._receipt(x) for x in self._journal.read(retained).state)

    def recover_from_anchor(self): return self._journal.read().fence

    def _consume(self,expected,preimage,signature):
        self.read(expected)
        raw=canonical_json([preimage.hex(),signature.hex()])
        return self._journal.append(expected,raw)


class OperatorJournal(SealedOTCEJournal):
    """R2/R3 materialize only authorized current-view data; R4 releases one R0."""
    def _operator(self,r,op):
        if type(r) is not Read or r.operation!=op or r.query.branch!='actual':
            raise ValueError('dedicated observed-view operator token required')

    def index(self,r,*,retained,now):
        self._operator(r,'r2')
        with self._vault() as db:
            nodes,_=self._selection(r,retained=retained,now=now)
            postings={}; sources=[]
            for n in nodes:
                if n['kind']!='R0' or n['evidence']!='observed' or n['payload']['key']!=r.key: continue
                plain=self._decrypt(db,n); sources.append(n['output'])
                for token in set(re.findall(r'\w+',plain['value'].casefold())):
                    postings.setdefault(token,[]).append(n['id'])
            return Index(tuple((k,tuple(v)) for k,v in sorted(postings.items())),tuple(sources))

    def model(self,r,*,retained,now,checkpoint=None):
        self._operator(r,'r3')
        with self._vault() as db:
            nodes,_=self._selection(r,retained=retained,now=now)
            rows=[]
            for n in nodes:
                if n['kind']=='R1':
                    p=self._decrypt(db,n); rows.append((n['output'],tuple(p['x']),p['y']))
            prefix=tuple(x[0] for x in rows); weights=(0,)*self._scope.dimension; reused=0
            if checkpoint is not None:
                if (type(checkpoint) is not Checkpoint or checkpoint.scope!=self._state_pin()
                        or type(checkpoint.prefix) is not tuple or len(checkpoint.prefix)>16
                        or any(not _pin(x) for x in checkpoint.prefix) or type(checkpoint.weights) is not tuple
                        or len(checkpoint.weights)!=len(weights) or any(not _int(x,-16_000_000,16_000_000) for x in checkpoint.weights)):
                    raise ValueError('invalid checkpoint')
                k=len(checkpoint.prefix)
                if prefix[:k]==checkpoint.prefix:
                    weights=_train(weights,rows[:k])
                    if weights!=checkpoint.weights: raise ValueError('checkpoint mismatch')
                    reused=k
            weights=_train(weights,rows[reused:])
            return Model(Checkpoint(self._state_pin(),prefix,weights),reused)

    def export(self,ledger,expected,r,g,*,retained,now):
        self._operator(r,'r4')
        if type(ledger) is not ExportLedger or ledger.source!=self._state_pin(): raise ValueError('release ledger scope')
        preimage=permit_bytes(ledger.pin,self,r,g)
        if not _time(now) or not g.issued<=now<g.expires or not strict_verify(ledger.approver,preimage,g.signature):
            raise ValueError('release authorization')
        with self._vault() as db:
            selected,_=self._selection(r,retained=retained,now=now)
            reader=self._reduce(self._journal.read(retained).state)[2]
            if reader==ledger.approver: raise ValueError('release roles must remain distinct')
            if g.nonce in ledger.read(expected): return Release('REJECTED',None,None)
            for n in reversed(selected):
                if n['kind']=='R0' and n['evidence']=='observed' and n['payload']['key']==r.key:
                    payload=canonical_json(self._decrypt(db,n)['value'])
                    if sha256(payload).hexdigest()!=g.digest: raise ValueError('release digest mismatch')
                    result=ledger._consume(expected,preimage,g.signature)
                    if result.status!='COMMITTED': return Release(result.status,None,None)
                    return Release('COMMITTED',result.snapshot.fence,payload)
            raise ValueError('no active observed fact to release')
