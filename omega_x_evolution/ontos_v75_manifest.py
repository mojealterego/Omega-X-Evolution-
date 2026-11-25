"""L12 manifest admission from in-memory payloads or an independently pinned ZIP."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from .ontos_v49_manifest import SourceRecord, audit_inventory, read_source_archive
from .ontos_v72_jcs import parse_json

_HEX = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)


@dataclass(frozen=True, slots=True)
class SourceArchive:
    """Untrusted archive bytes and an operator-pinned SHA-256 digest."""
    raw: bytes
    pin: str


def verify_manifest(raw: bytes, pin: str, payloads: dict[str, bytes] | SourceArchive) -> dict:
    """Verify registered inventory and bytes without extracting or executing code.

    Archive and dictionary inputs have identical per-file and disposition rules.
    The pins must be provisioned independently; PASS is manual-review eligibility,
    never a release or legal approval.
    """
    failed = {'status': 'FAIL', 'inventory_verified': False, 'registered': 0,
              'checked_blobs': 0, 'release_authorized': False}
    try:
        if (type(raw) is not bytes or len(raw) > 1024 * 1024 or type(pin) is not str
                or _HEX.fullmatch(pin) is None or sha256(raw).hexdigest() != pin):
            return failed
        obj = parse_json(raw)
        if (type(obj) is not dict or obj.get('schema') != 'ontos-source-register-v49-v1'
                or type(obj.get('entries')) is not list or len(obj['entries']) != 33):
            return failed
        records = tuple(SourceRecord(**row) for row in obj['entries'])
        if type(payloads) is SourceArchive:
            payloads = read_source_archive(payloads.raw, payloads.pin)
        result = audit_inventory(records, payloads)
        if result['manifest_sha256'] != obj.get('entry_digest_sha256'):
            return failed
        return {**result, 'status': 'PASS' if result['eligible_for_manual_review'] else 'BLOCKED',
                'inventory_verified': True, 'register_file_sha256': pin, 'release_authorized': False}
    except (ValueError, TypeError, KeyError, RecursionError):
        return failed
