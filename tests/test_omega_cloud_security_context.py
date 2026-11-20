"""Cloud admission must reject effective security-context overrides."""
import copy
import pytest
from omega_x_evolution.cloud import CloudOrchestrator, Job, Policy, manifest, _match


def policy():
    return Policy('omega-test', 'registry.example/engine@sha256:'+'a'*64,
                  100000, 1000, 1000, 1000)


def mutated(body, location, patch):
    actual = copy.deepcopy(body)
    actual['metadata']['uid'] = 'fixture-uid'
    pod = actual['spec']['template']['spec']
    target = {'pod': pod, 'pod-security': pod['securityContext'],
              'container-security': pod['containers'][0]['securityContext']}[location]
    target.update(patch)
    return actual


@pytest.mark.parametrize('location,patch', [
    ('container-security', {'runAsNonRoot': False, 'runAsUser': 0}),
    ('container-security', {'seccompProfile': {'type': 'Unconfined'}}),
    ('container-security', {'procMount': 'Unmasked'}),
    ('pod-security', {'sysctls': [{'name': 'kernel.shm_rmid_forced', 'value': '1'}]}),
    ('pod', {'shareProcessNamespace': True}),
])
def test_cloud_rejects_security_override_after_reservation(tmp_path, location, patch):
    class Provider:
        namespace = 'omega-test'
        identity = 'deterministic-admission-contract'
        def create(self, body):
            self.actual = mutated(body, location, patch)
            return self.actual
        def get(self, name):
            return self.actual
        def delete(self, name, uid):
            pytest.fail('unverified workload must not be deleted')

    controller = CloudOrchestrator(tmp_path/'ledger.db', b'k'*32, policy(),
                                   Provider(), ledger_id='b'*64, create=True)
    with pytest.raises(ValueError):
        controller.submit(Job('first', 'cpu', 1, 0, 10, 42, 16), authorized=True)
    row = controller.inspect()['jobs']['first']
    assert row['status'] == 'reserved' and row['uid'] is None
    with pytest.raises(ValueError):
        controller.reconcile('first', authorized=True)
    assert controller.stop(authorized=True)['delete_errors'] == ['first']


def test_cloud_allows_equivalent_security_defaults():
    body = manifest(policy(), Job('first', 'cpu', 1, 0, 10, 42, 16), 'b'*64)
    actual = mutated(body, 'container-security', {'runAsNonRoot': True,
                     'runAsUser': 10001, 'seccompProfile': {'type': 'RuntimeDefault'},
                     'procMount': 'Default'})
    actual['spec']['template']['spec']['shareProcessNamespace'] = False
    assert _match(actual, body) == 'fixture-uid'
