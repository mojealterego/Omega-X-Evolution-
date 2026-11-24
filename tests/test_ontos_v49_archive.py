import hashlib
import io
import stat
import warnings
import zipfile

import pytest

from omega_x_evolution.ontos_v49_manifest import (
    SOURCE_PATHS, SourceRecord, audit_inventory, read_source_archive,
)


def archive(entries, compression=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=compression) as z:
        for name, data in entries:
            z.writestr(name, data)
    return buffer.getvalue()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def test_archive_full_inventory_without_automatic_promotion():
    payloads = {p: p.encode() for p in SOURCE_PATHS}
    raw = archive(list(reversed(list(payloads.items()))))
    records = tuple(SourceRecord(p, digest(data), 'REUSE', 'Reviewed test fixture.', 'MIT')
                    for p, data in payloads.items())
    actual = read_source_archive(raw, digest(raw))
    assert actual == payloads
    assert tuple(actual) == SOURCE_PATHS
    report = audit_inventory(records, actual)
    assert report['checked_blobs'] == 33
    assert report['eligible_for_manual_review'] is True
    assert report['ready_for_integration'] is False


def test_archive_partial_and_wrong_content_are_not_promoted():
    raw = archive([('README.md', b'changed')])
    records = tuple(SourceRecord(p, digest(b'expected') if p == 'README.md' else None,
                                 'RESEARCH', 'Reviewed test fixture.', 'UNKNOWN')
                    for p in SOURCE_PATHS)
    with pytest.raises(ValueError, match='digest mismatch'):
        audit_inventory(records, read_source_archive(raw, digest(raw)))
    assert len(read_source_archive(raw, digest(raw))) == 1


@pytest.mark.parametrize('path', ['../README.md', '/README.md', 'src\\bad',
                                  'src/../README.md', 'README.md/', 'other.py'])
def test_archive_rejects_unknown_or_unsafe_paths(path):
    raw = archive([(path, b'x')])
    with pytest.raises(ValueError):
        read_source_archive(raw, digest(raw))


def test_archive_rejects_duplicate_and_symlink():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        duplicate = archive([('README.md', b'a'), ('README.md', b'b')])
    link = zipfile.ZipInfo('README.md')
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    for raw in (duplicate, archive([(link, b'target')])):
        with pytest.raises(ValueError):
            read_source_archive(raw, digest(raw))


def test_archive_rejects_invalid_pin_format_and_corrupt_archive():
    raw = archive([('README.md', b'x')])
    for pin in ('0' * 64, digest(raw).upper(), None):
        with pytest.raises(ValueError):
            read_source_archive(raw, pin)
    corrupt = b'not a zip'
    with pytest.raises(ValueError):
        read_source_archive(corrupt, digest(corrupt))


def test_archive_rejects_member_and_total_expansion_budgets():
    for entries in ([('README.md', b'x' * 65537)],
                    [(p, b'x' * 65536) for p in SOURCE_PATHS[:17]]):
        raw = archive(entries)
        with pytest.raises(ValueError):
            read_source_archive(raw, digest(raw))


def test_archive_rejects_unsupported_codec_and_embedded_null():
    unsupported = archive([('README.md', b'x')], zipfile.ZIP_BZIP2)
    nul = archive([('README.mdX', b'x')]).replace(b'README.mdX', b'README.md\x00')
    for raw in (unsupported, nul):
        with pytest.raises(ValueError):
            read_source_archive(raw, digest(raw))


def test_archive_rejects_crc_damage():
    raw = archive([('README.md', b'unique-payload')], zipfile.ZIP_STORED)
    damaged = raw.replace(b'unique-payload', b'broken-payload')
    with pytest.raises(ValueError):
        read_source_archive(damaged, digest(damaged))
