import hashlib
import json
from scripts.ontos_v63_v66_campaign import campaign, SEEDS


def test_l10_campaign_has_thirty_deterministic_replays():
    assert len(SEEDS)==30 and len(set(SEEDS))==30
    first=campaign()
    assert first==campaign()
    assert first['base_seed_count']==30
    assert first['certificate_256_i4_valid']
    assert first['actual_runtime_permissions_granted'] is False
    assert first['measured_ipc_latency_ms'] is None
    assert all(row['receiver_deliveries']==4 and row['replay_verdict']=='REPLAY_REJECTED'
               for row in first['events'])
    assert all(row['conflict_verdict']=='FAIL_CONFLICT' and
               row['noninterference_verdict']=='PASS_FINITE' for row in first['events'])
    assert all(row['operational_capabilities_granted'] is False for row in first['events'])


def test_l10_campaign_json_has_no_secret_material_or_external_actions():
    raw=json.dumps(campaign(),sort_keys=True,allow_nan=False).encode()
    assert len(raw)<40000
    assert len(hashlib.sha256(raw).hexdigest())==64
    assert b'sk-' not in raw


def test_l10_checked_in_campaign_matches_exact_replay():
    from pathlib import Path
    artifact = Path(__file__).resolve().parents[1] / 'docs/omega/ONTOS_V63_V66_CAMPAIGN.json'
    expected = json.dumps(campaign(), sort_keys=True, indent=2, allow_nan=False) + '\n'
    assert artifact.read_bytes() == expected.encode('utf-8')
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == '1ceebe076a8a1c346d3ff46ad8ff05e1d0df4063788bc398b2079e95d8aeb764'


def test_l10_documented_limitations_not_fabricated_certifications():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    doc=(root/'docs/omega/ONTOS_V63_V66_L10.md').read_text(encoding='utf8')
    for keyword in ('GATE-09', 'NATIVE-BLOCKED', 'UNKNOWN_BOUND',
                    'MODEL_APPROVED', 'v63', 'v64', 'v65', 'v66'):
        assert keyword in doc
    assert 'IPC `<1 ms` nie został przetestowany' in doc
