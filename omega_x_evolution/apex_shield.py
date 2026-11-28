"""Pure deterministic APEX model admission, not a hardware driver.

Trusted supervisor supplies validated conservative limits and coherent telemetry.
No implicit calibration, device I/O, or claim of actual silicon safety. Unknown
or stale inputs deny; caller must stop rather than execute a denied proposal.
"""
from dataclasses import dataclass


def _int(x,lo,hi): return type(x) is int and lo<=x<=hi


@dataclass(frozen=True,slots=True)
class Limits:
    max_age_ms: int
    max_temp_mc: int
    vtcm_bytes: int
    mtj_write_max_uv: int | None
    mtj_backhop_from_uv: int | None
    mtj_ic0_ua: int | None


@dataclass(frozen=True,slots=True)
class Telemetry:
    observed_ms: int
    temp_mc: int
    vtcm_used_bytes: int
    feram_ready: bool
    reram_busy: bool
    reram_polled: bool


@dataclass(frozen=True,slots=True)
class HTP:
    additional_vtcm_bytes: int
    spill_bytes: int


@dataclass(frozen=True,slots=True)
class FeRAM:
    op: str
    mode: str
    deselect_ns: int
    address: int
    length: int


@dataclass(frozen=True,slots=True)
class ReRAM:
    op: str
    length: int


@dataclass(frozen=True,slots=True)
class MTJ:
    op: str
    magnitude: int  # microvolts for write, microamperes for read


@dataclass(frozen=True,slots=True)
class Decision:
    allowed: bool
    reason: str


def decide(limits,telemetry,action,*,now):
    """Model-only predicate; no action is executed by this function."""
    def deny(reason): return Decision(False,reason)
    if type(limits) is not Limits or type(telemetry) is not Telemetry:
        return deny('typed limits and telemetry required')
    l,t=limits,telemetry
    if (not _int(now,0,2**63-1) or not _int(l.max_age_ms,1,60000)
            or not _int(l.max_temp_mc,1,125000) or not _int(l.vtcm_bytes,1,8*1024*1024)
            or not _int(t.observed_ms,0,now) or now-t.observed_ms>l.max_age_ms
            or not _int(t.temp_mc,-40000,l.max_temp_mc-1)
            or not _int(t.vtcm_used_bytes,0,l.vtcm_bytes)
            or any(type(x) is not bool for x in (t.feram_ready,t.reram_busy,t.reram_polled))):
        return deny('invalid stale or unsafe telemetry envelope')
    if type(action) is HTP:
        if not _int(action.additional_vtcm_bytes,0,l.vtcm_bytes-t.vtcm_used_bytes) or not _int(action.spill_bytes,0,0):
            return deny('VTCM or spill bound')
    elif type(action) is FeRAM:
        a=action
        if type(a.mode) is not str or a.mode not in ('qpi','xip') or not _int(a.deselect_ns,80 if a.mode=='qpi' else 100,10**9):
            return deny('FeRAM mode or deselect time')
        if type(a.op) is not str or a.op not in ('status','read','frqad','write'):
            return deny('unsupported FeRAM command subset')
        if a.op=='frqad' and not t.feram_ready: return deny('FRQAD before valid POR command')
        if a.op=='status':
            if not _int(a.address,0,0) or not _int(a.length,0,0): return deny('status shape')
        elif not _int(a.address,0,1048575) or not _int(a.length,1,1048576-a.address):
            return deny('FeRAM address range')
        elif a.op=='write' and (a.address%4 or a.length%4): return deny('FeRAM row alignment')
    elif type(action) is ReRAM:
        if type(action.op) is not str: return deny('typed ReRAM operation required')
        if action.op=='poll' and _int(action.length,0,0): pass
        elif action.op=='write' and _int(action.length,1,256) and not t.reram_busy and t.reram_polled: pass
        else: return deny('ReRAM page size or WIP polling')
    elif type(action) is MTJ:
        if type(action.op) is not str: return deny('typed MTJ operation required')
        if action.op=='write':
            if (not _int(l.mtj_write_max_uv,1,10**7) or not _int(l.mtj_backhop_from_uv,1,10**7)
                    or not _int(action.magnitude,1,min(l.mtj_write_max_uv,l.mtj_backhop_from_uv-1))):
                return deny('uncalibrated or forbidden MTJ write envelope')
        elif action.op=='read':
            if not _int(l.mtj_ic0_ua,1,10**7) or not _int(action.magnitude,1,l.mtj_ic0_ua//5):
                return deny('uncalibrated or excessive MTJ read current')
        else: return deny('unknown MTJ operation')
    else: return deny('unsupported action')
    return Decision(True,'model constraints satisfied')
