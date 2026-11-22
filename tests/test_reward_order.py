"""Focused tests for the finite-pair inversion guard; reference: arXiv:2209.13085v2."""
import dataclasses
import unittest

from omega_x_evolution.reward_order import (
    RewardReference, RewardScore, assess_reward_order,
)


def sample(values=(('none', '0'), ('attic', '1'), ('bed_and_kitchen', '2'))):
    return RewardReference(tuple(RewardScore(i, v) for i, v in values))


class RewardOrderTests(unittest.TestCase):
    def test_rhg_001_detects_proxy_inversion(self):
        ref = sample()
        result = assess_reward_order(ref, {
            'none': '0', 'attic': '1', 'bed_and_kitchen': '0',
        }, trusted_reference_digest=ref.digest)
        self.assertEqual(result['status'], 'REJECT_INVERSION')
        self.assertEqual(result['inversion_count'], 1)
        self.assertEqual(result['witnesses'][0]['higher_proxy'], 'attic')
        self.assertEqual(result['witnesses'][0]['higher_reference'], 'bed_and_kitchen')
        self.assertFalse(result['release_authorized'])

    def test_rhg_002_ties_are_not_inversions(self):
        ref = sample()
        res = assess_reward_order(ref, {'none': '0', 'attic': '1', 'bed_and_kitchen': '1'},
                                  trusted_reference_digest=ref.digest)
        self.assertEqual(res['status'], 'PASS_FINITE_NO_INVERSION_UNATTESTED')
        self.assertEqual(res['inversion_count'], 0)
        self.assertEqual(res['pairs_compared'], 3)

    def test_rhg_003_wrong_digest_rejected(self):
        ref = sample()
        with self.assertRaises(ValueError):
            assess_reward_order(ref, {'none':'0', 'attic':'1', 'bed_and_kitchen':'2'},
                                trusted_reference_digest='a'*64)

    def test_rhg_004_missing_and_extra_evidence_fail_closed(self):
        ref = sample()
        for evidence in ({'none':'0', 'attic':'1'},
                         {'none':'0', 'attic':'1', 'bed_and_kitchen':'2', 'extra':'1'},
                         {'none':'0', 'attic':'1', 'bed_and_kitchen':'NaN'},
                         {'none':'0', 'attic':'1', 'bed_and_kitchen':2.0},
                         None):
            with self.subTest(evidence=evidence):
                res = assess_reward_order(ref, evidence, trusted_reference_digest=ref.digest)
                self.assertEqual(res['status'], 'REJECT_INVALID_EVIDENCE')

    def test_rhg_005_duplicate_policy_fails(self):
        with self.assertRaises(ValueError):
            sample((('a','1'),('a','2')))

    def test_rhg_006_disallow_nan_inf_whitespace_huge_numbers(self):
        for v in ['NaN', 'Inf', '-Infinity', ' 1', '1e999999', '1'*100, '+0.1', '1_000']:
            with self.subTest(v=v), self.assertRaises(ValueError):
                sample((('a', v), ('b', '2')))

    def test_rhg_007_constant_proxy_not_positive_evidence(self):
        ref = sample()
        res = assess_reward_order(ref, {'none':'1','attic':'1','bed_and_kitchen':'1'},
                                  trusted_reference_digest=ref.digest)
        self.assertEqual(res['status'], 'INCONCLUSIVE_CONSTANT_REWARD')

    def test_rhg_008_constant_reference_not_positive_evidence(self):
        ref=sample((('a','2'),('b','2')))
        res=assess_reward_order(ref, {'a':'1','b':'2'}, trusted_reference_digest=ref.digest)
        self.assertEqual(res['status'], 'INCONCLUSIVE_CONSTANT_REWARD')

    def test_rhg_009_mutation_of_frozen_evidence_detected(self):
        ref=sample()
        object.__setattr__(ref.scores[1], 'value', 'bogus')
        with self.assertRaises(ValueError):
            assess_reward_order(ref, {'none':'0','attic':'1','bed_and_kitchen':'2'},
                                trusted_reference_digest='a'*64)

    def test_rhg_010_tiny_differences_are_not_rounded(self):
        ref=sample((('a','1.000000000000000000000001'),('b','1')))
        res=assess_reward_order(ref, {'a':'0.999999999999999999999999','b':'1'},
                                trusted_reference_digest=ref.digest)
        self.assertEqual(res['status'], 'REJECT_INVERSION')

    def test_rhg_011_stable_order_and_digest(self):
        ref=sample((('z','2.00'),('b','0'),('a','1')))
        rev=sample((('a','1'),('z','2.00'),('b','0')))
        self.assertEqual(ref.digest, rev.digest)

    def test_rhg_012_bounded_input(self):
        with self.assertRaises(ValueError):
            RewardReference(tuple(RewardScore(f'p{i}', '0') for i in range(129)))

    def test_rhg_013_more_than_one_witness_bounded(self):
        ref=sample((('a','0'),('b','1'),('c','2'),('d','3')))
        res=assess_reward_order(ref, {'a':'3','b':'2','c':'1','d':'0'},
                                trusted_reference_digest=ref.digest, witness_limit=2)
        self.assertEqual(res['inversion_count'], 6)
        self.assertEqual(len(res['witnesses']),2)
        self.assertEqual(res['pairs_compared'],6)

    def test_rhg_014_cannot_mutate_threshold_or_inject_invalid_limit(self):
        ref=sample()
        for n in [None, 0, -1, 129, True, 1.5]:
            with self.subTest(n=n),self.assertRaises(ValueError):
                assess_reward_order(ref, {'none':'0','attic':'1','bed_and_kitchen':'2'},
                                    trusted_reference_digest=ref.digest,witness_limit=n)

    def test_rhg_016_invalid_policy_identifier(self):
        for identifier in ["INVALID", "bad/id", "", None]:
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                RewardScore(identifier, '1')

    def test_rhg_017_reference_type_required(self):
        with self.assertRaises(ValueError):
            assess_reward_order(None, {'a': '1'}, trusted_reference_digest='a' * 64)

    def test_rhg_015_no_universal_claim(self):
        ref=sample()
        res=assess_reward_order(ref, {'none':'0','attic':'1','bed_and_kitchen':'2'},
                                trusted_reference_digest=ref.digest)
        self.assertFalse(res['human_values_alignment_proved'])
        self.assertFalse(res['reference_attested'])
        self.assertFalse(res['release_authorized'])
        self.assertEqual(res['policy_scope'],'FINITE_LIST_ONLY')


if __name__=='__main__':
    unittest.main()
