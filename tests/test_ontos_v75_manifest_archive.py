from dataclasses import asdict
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from omega_x_evolution.ontos_v49_manifest import SOURCE_PATHS, SourceRecord, audit_inventory
from omega_x_evolution.ontos_v72_jcs import canonical_json
from omega_x_evolution.ontos_v75_manifest import SourceArchive, verify_manifest


def digest(data):
    return sha256(data).hexdigest()


def fixture():
    payloads = {path: path.encode() for path in SOURCE_PATHS}
    records = tuple(SourceRecord(p, digest(data), 'REUSE', 'Synthetic fixture only.', 'MIT')
                    for p, data in payloads.items())
    raw = canonical_json({'schema': 'ontos-source-register-v49-v1',
                          'entries': [asdict(r) for r in records],
                          'entry_digest_sha256': audit_inventory(records, payloads)['manifest_sha256']})
    return raw, payloads


def packed(payloads):
    buffer = BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as z:
        for name, data in payloads.items():
            z.writestr(name, data)
    raw = buffer.getvalue()
    return SourceArchive(raw, digest(raw))


def test_archive_equals_legacy_dictionary_admission():
    raw, payloads = fixture()
    actual = verify_manifest(raw, digest(raw), packed(payloads))
    assert actual == verify_manifest(raw, digest(raw), payloads)
    assert actual['status'] == 'PASS' and actual['checked_blobs'] == 33
    assert actual['release_authorized'] is False
    assert actual['ready_for_integration'] is False


def test_partial_archive_remains_blocked():
    raw, payloads = fixture()
    payloads.pop(SOURCE_PATHS[0])
    result = verify_manifest(raw, digest(raw), packed(payloads))
    assert result['status'] == 'BLOCKED' and result['checked_blobs'] == 32
    assert result['unknown'] == (SOURCE_PATHS[0],)


@pytest.mark.parametrize('failure', ['pin', 'content', 'path', 'format', 'manifest_pin', 'empty'])
def test_archive_rejected_fail_closed(failure):
    raw, payloads = fixture()
    manifest_pin = digest(raw)
    if failure == 'content':
        payloads[SOURCE_PATHS[0]] = b'changed'
    if failure == 'path':
        payloads['../README.md'] = b'bad'
    if failure == 'empty':
        payloads = {}
    archive = packed(payloads)
    if failure == 'pin':
        archive = SourceArchive(archive.raw, '0' * 64)
    if failure == 'format':
        archive = SourceArchive(b'bad zip', digest(b'bad zip'))
    if failure == 'manifest_pin':
        manifest_pin = '0' * 64
    result = verify_manifest(raw, manifest_pin, archive)
    assert result['status'] == 'FAIL' and result['checked_blobs'] == 0
    assert result['release_authorized'] is False


def test_invalid_entry_digest_cannot_admit_archive():
    raw, payloads = fixture()
    from omega_x_evolution.ontos_v72_jcs import parse_json
    obj = parse_json(raw)
    obj['entry_digest_sha256'] = '0' * 64
    changed = canonical_json(obj)
    assert verify_manifest(changed, digest(changed), packed(payloads))['status'] == 'FAIL'


def test_research_only_manifest_cannot_be_promoted():
    raw, payloads = fixture()
    records = tuple(SourceRecord(p, digest(data), 'RESEARCH', 'Synthetic fixture only.', 'UNKNOWN')
                    for p, data in payloads.items())
    raw = canonical_json({'schema': 'ontos-source-register-v49-v1',
                          'entries': [asdict(r) for r in records],
                          'entry_digest_sha256': audit_inventory(records, payloads)['manifest_sha256']})
    result = verify_manifest(raw, digest(raw), packed(payloads))
    assert result['checked_blobs'] == 33 and result['status'] == 'BLOCKED'
    assert not result['release_authorized']
