"""Read-only ONTOS Phase0 source inventory. No source execution or disk access.

The 33 path names originate from the ONTOS Ω∞ source file register.
A manifest entry or its declared digest is not evidence of code safety.
Binary content is checked only when explicitly passed as bytes, never imported.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re

SOURCE_PATHS = (
    'README.md',
    'pyproject.toml',
    'requirements-lock.txt',
    'config/ontos_l12_config.json',
    'schemas/telemetry_schema.json',
    'src/omega_ontos/__init__.py',
    'src/omega_ontos/types.py',
    'src/omega_ontos/poly_interface.py',
    'src/omega_ontos/cognitive_substrate.py',
    'src/omega_ontos/living_memory.py',
    'src/omega_ontos/causal_engine.py',
    'src/omega_ontos/thermodynamics.py',
    'src/omega_ontos/immune_kernel.py',
    'src/omega_ontos/uir_evolution.py',
    'src/omega_ontos/organism.py',
    'simulators/__init__.py',
    'simulators/environments.py',
    'simulators/hardware_substrates.py',
    'benchmarks/__init__.py',
    'benchmarks/run_benchmarks.py',
    'tests/__init__.py',
    'tests/test_ontos_suite.py',
    'interfaces/wit/ontos_poly.wit',
    'runtime/rust_zenoh_core/Cargo.toml',
    'runtime/rust_zenoh_core/src/main.rs',
    'compiler/mlir/ontos_uir.mlir',
    'compiler/egglog/uir_eqsat.egg',
    'hardware/rtl/static_shell_guard.sv',
    'hardware/rtl/dfx_cfc_accel.sv',
    'formal/lean4/OntosInvariants.lean',
    'formal/smt/hyperltl_noninterference.smt2',
    'scripts/compute_manifest_sha256.py',
    'scripts/verify_all.sh',
)
_DECISIONS = frozenset(('REUSE', 'PORT', 'REJECT', 'RESEARCH'))
_LICENSES = frozenset(('UNKNOWN', 'Apache-2.0', 'MIT', 'BSD-3-Clause',
                       'GPL-3.0-only', 'CC-BY-4.0', 'Proprietary'))
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_MAX_FILE = 65536
_MAX_TOTAL = 1048576


@dataclass(frozen=True, slots=True)
class SourceRecord:
    path: str
    sha256: str | None
    decision: str
    rationale: str
    license_id: str

    def __post_init__(self) -> None:
        if type(self.path) is not str or self.path not in SOURCE_PATHS:
            raise ValueError('unknown source path')
        if self.sha256 is not None and (type(self.sha256) is not str or not _SHA.fullmatch(self.sha256)):
            raise ValueError('invalid SHA-256 digest')
        if type(self.decision) is not str or self.decision not in _DECISIONS:
            raise ValueError('invalid source disposition')
        if (type(self.rationale) is not str or not 8 <= len(self.rationale) <= 300
                or self.rationale != self.rationale.strip()
                or any(ord(c) < 32 or ord(c) == 127 for c in self.rationale)):
            raise ValueError('source rationale contract')
        if type(self.license_id) is not str or self.license_id not in _LICENSES:
            raise ValueError('unknown license classification')
        if self.decision in ('REUSE', 'PORT') and (self.sha256 is None or self.license_id == 'UNKNOWN'):
            raise ValueError('source reuse requires digest and reviewed license')


def audit_inventory(records: tuple[SourceRecord, ...], payloads: dict[str, bytes]) -> dict:
    """Verify fixed manifest and optionally actual bytes; never import or run input.

    Counts describe structural metadata and verified byte identities, not
    authenticated provenance, runtime integration, or license sufficiency.
    """
    if (type(records) is not tuple or len(records) != len(SOURCE_PATHS)
            or any(type(record) is not SourceRecord for record in records)
            or type(payloads) is not dict or len(payloads) > len(SOURCE_PATHS)):
        raise ValueError('manifest size and type contract')
    index = {}
    for record in records:
        # Recheck despite frozen dataclass; object.__setattr__ can bypass it.
        SourceRecord(record.path, record.sha256, record.decision,
                     record.rationale, record.license_id)
        if record.path in index:
            raise ValueError('duplicate source path')
        index[record.path] = record
    if frozenset(index) != frozenset(SOURCE_PATHS):
        raise ValueError('source manifest incomplete')
    if any(type(path) is not str or path not in index or type(data) is not bytes
           for path, data in payloads.items()):
        raise ValueError('unrecognized source payload')
    if any(len(data) > _MAX_FILE for data in payloads.values()) or sum(map(len, payloads.values())) > _MAX_TOTAL:
        raise ValueError('source byte budget')

    checked = []
    unknown = []
    for path in SOURCE_PATHS:
        record = index[path]
        if path in payloads:
            if record.sha256 is None:
                raise ValueError('source digest not declared')
            digest = hashlib.sha256(payloads[path]).hexdigest()
            if digest != record.sha256:
                raise ValueError('source digest mismatch')
            checked.append(record.sha256)
        else:
            unknown.append(path)
    canonical = [dict(path=r.path, sha256=r.sha256, decision=r.decision,
                      rationale=r.rationale, license_id=r.license_id)
                 for r in (index[path] for path in SOURCE_PATHS)]
    serialized = json.dumps(canonical, sort_keys=True, ensure_ascii=True,
                            separators=(',', ':'), allow_nan=False).encode('ascii')
    return {
        'registered': len(index),
        'checked_blobs': len(checked),
        'verified_digests': tuple(sorted(checked)),
        'unknown': tuple(unknown),
        'research_only': sum(r.decision == 'RESEARCH' for r in records),
        # Hash matches and a license tag are necessary metadata, not a
        # trusted approval or executable-code safety certificate. Never promote.
        'eligible_for_manual_review': (len(checked) == len(SOURCE_PATHS)
                                       and all(r.decision in ('REUSE', 'PORT')
                                               and r.license_id in ('Apache-2.0', 'MIT', 'BSD-3-Clause')
                                               for r in records)),
        'ready_for_integration': False,
        'manifest_sha256': hashlib.sha256(serialized).hexdigest(),
    }


def read_source_archive(raw: bytes, archive_pin: str) -> dict[str, bytes]:
    """Read a pinned, bounded ZIP of exact registered paths without extracting.

    The caller must obtain the archive pin independently. This function only
    transports bytes; pass its result to audit_inventory or v75 audit_l12 for
    per-file verification. A partial archive cannot establish full acceptance.
    Directory entries and wrapper paths are intentionally not accepted.
    """
    import io
    import stat
    import zipfile
    import zlib

    if (type(raw) is not bytes or not 0 < len(raw) <= 2 * _MAX_TOTAL
            or type(archive_pin) is not str or not _SHA.fullmatch(archive_pin)
            or hashlib.sha256(raw).hexdigest() != archive_pin):
        raise ValueError('invalid archive bytes or pin')
    payloads: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if not 0 < len(entries) <= len(SOURCE_PATHS):
                raise ValueError('archive member count')
            names: set[str] = set()
            total = 0
            for entry in entries:
                name = entry.filename
                kind = stat.S_IFMT(entry.external_attr >> 16)
                if (name != entry.orig_filename or name not in SOURCE_PATHS
                        or name in names or entry.is_dir() or kind not in (0, stat.S_IFREG)
                        or entry.external_attr & 0x10 or entry.flag_bits & 1
                        or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise ValueError('invalid archive member')
                names.add(name)
                if not 0 <= entry.file_size <= _MAX_FILE:
                    raise ValueError('archive member byte budget')
                total += entry.file_size
                if total > _MAX_TOTAL:
                    raise ValueError('archive total byte budget')
            for entry in entries:
                with archive.open(entry) as member:
                    data = member.read(entry.file_size + 1)
                if len(data) != entry.file_size:
                    raise ValueError('archive member size mismatch')
                payloads[entry.filename] = data
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError,
            EOFError, zlib.error, UnicodeError, OverflowError) as exc:
        raise ValueError('invalid source archive') from exc
    return {path: payloads[path] for path in SOURCE_PATHS if path in payloads}
