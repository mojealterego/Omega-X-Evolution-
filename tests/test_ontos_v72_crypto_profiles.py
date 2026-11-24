import hmac
import shutil
import subprocess

import pytest

from omega_x_evolution.ontos_v72_crypto_profiles import (
    Profile, signature_preimage, tag, verify_tag, verify_pq_signature, public_der,
    validate_kem_ciphertext,
)

KEY = bytes(range(32))
MSG = b'v72 evidence fixture'


def test_hmac_context_and_test_key_separation():
    expected = hmac.digest(KEY, b'OMEGA-X/v72/HMAC-SHA256\x00TEST\x00' + MSG, 'sha256')
    actual = tag(KEY, MSG, test_only=True)
    assert actual == expected
    assert verify_tag(KEY, MSG, actual, test_only=True)
    assert not verify_tag(KEY, MSG, actual, test_only=False)
    assert not verify_tag(KEY, MSG+b'x', actual, test_only=True)
    assert not verify_tag(bytes(32), MSG, actual, test_only=True)
    assert not verify_tag(KEY, MSG, actual[:-1], test_only=True)


@pytest.mark.parametrize('key,message,flag', [(b'x',MSG,True),(KEY,b'x'*(1048576+1),True),(KEY,MSG,1)])
def test_hmac_bounds(key,message,flag):
    with pytest.raises(ValueError): tag(key,message,test_only=flag)
    assert not verify_tag(key,message,bytes(32),test_only=flag)


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, timeout=20).stdout


def native_binary(profile):
    binary = shutil.which('openssl')
    if binary is None:
        pytest.skip('native OpenSSL qualification unavailable')
    kind = '-kem-algorithms' if profile is Profile.ML_KEM_768 else '-signature-algorithms'
    try:
        available = run(binary, 'list', kind).decode('ascii')
    except (subprocess.SubprocessError, OSError):
        pytest.skip('native OpenSSL algorithm discovery unavailable')
    if profile.value not in available:
        pytest.skip('native OpenSSL profile unavailable: ' + profile.value)
    return binary


@pytest.mark.parametrize('profile,size,sigsize', [(Profile.ML_DSA_65,1952,3309),(Profile.SLH_DSA_SHA2_128S,32,7856)])
def test_native_signature_profile(tmp_path,profile,size,sigsize):
    binary = native_binary(profile)
    key, pub, msg, sig = [tmp_path/x for x in ('key.pem','pub.der','message','signature')]
    run(binary,'genpkey','-algorithm',profile.value,'-out',str(key))
    run(binary,'pkey','-in',str(key),'-pubout','-outform','DER','-out',str(pub))
    raw = pub.read_bytes()[-size:]
    assert public_der(profile,raw) == pub.read_bytes()
    msg.write_bytes(signature_preimage(profile,MSG))
    run(binary,'pkeyutl','-sign','-rawin','-inkey',str(key),'-in',str(msg),'-out',str(sig))
    signed = sig.read_bytes()
    assert len(signed) == sigsize
    assert verify_pq_signature(profile,raw,MSG,signed,openssl=binary) == 'PASS'
    assert verify_pq_signature(profile,raw,MSG+b'x',signed,openssl=binary) == 'FAIL'
    assert verify_pq_signature(profile,raw,MSG,bytes([signed[0]^1])+signed[1:],openssl=binary) == 'FAIL'
    assert verify_pq_signature(profile,raw,MSG,signed[:-1],openssl=binary) == 'FAIL'
    assert verify_pq_signature(profile,raw,MSG,signed,openssl='/no/such/openssl') == 'BLOCKED'


def test_kem_profile_real_roundtrip_and_role_separation(tmp_path):
    p = Profile.ML_KEM_768
    binary = native_binary(p)
    key, pub, ct, ss, recovered = [tmp_path/x for x in ('key.pem','pub.der','ct','ss','recovered')]
    run(binary,'genpkey','-algorithm',p.value,'-out',str(key))
    run(binary,'pkey','-in',str(key),'-pubout','-outform','DER','-out',str(pub))
    raw = pub.read_bytes()[-1184:]
    assert public_der(p,raw) == pub.read_bytes()
    run(binary,'pkeyutl','-encap','-pubin','-keyform','DER','-inkey',str(pub),'-out',str(ct),'-secret',str(ss))
    run(binary,'pkeyutl','-decap','-inkey',str(key),'-in',str(ct),'-secret',str(recovered))
    assert len(ss.read_bytes()) == 32 and ss.read_bytes() == recovered.read_bytes()
    assert validate_kem_ciphertext(p,ct.read_bytes())
    assert not validate_kem_ciphertext(p,ct.read_bytes()[:-1])
    assert not validate_kem_ciphertext(Profile.ML_DSA_65,ct.read_bytes())
    assert verify_pq_signature(p,raw,MSG,ct.read_bytes(),openssl=binary) == 'FAIL'
    with pytest.raises(ValueError): signature_preimage(p,MSG)


def test_invalid_profiles_and_key_shapes():
    with pytest.raises(ValueError): public_der(Profile.ML_DSA_65,bytes(32))
    with pytest.raises(ValueError): public_der('ML-DSA-65',bytes(1952))
    assert verify_pq_signature('ML-DSA-65',bytes(1952),MSG,bytes(3309),openssl='/usr/bin/openssl') == 'FAIL'
