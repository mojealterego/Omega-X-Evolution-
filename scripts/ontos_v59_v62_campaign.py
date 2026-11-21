"""Deterministic L9 finite-model campaign, no generated policy or host actions."""
import hashlib
import json
import math

from omega_x_evolution.ontos_v59_oscillator import KuramotoState, advance, potential_energy, order_parameter
from omega_x_evolution.ontos_v60_sheaf import SheafEdge, energy, diffuse
from omega_x_evolution.ontos_v61_faults import fault_campaign
from omega_x_evolution.ontos_v62_noise import drift_campaign, theoretical_error

SEEDS=tuple(9100+29*i for i in range(30))


def report():
    s=KuramotoState((0.,.75,1.5,2.25),(0.,0.,0.,0.),
                    ((1.,.3),(.8,.4),(.4,.9),(.3,1.)))
    start_osc=potential_energy(s)
    start_order=order_parameter(s)
    s=advance(s,.02,steps=100)
    start=((2.,-1.),(0.,2.),(-2.,.5))
    I=((1.,0.),(0.,1.))
    edges=(SheafEdge(0,1,I,I,1.),SheafEdge(1,2,I,I,.5))
    sheaf_start=energy(start,edges)
    end=diffuse(start,edges,.02,steps=100)
    sheaf_end=energy(end,edges)
    faults=fault_campaign(SEEDS)
    drift=drift_campaign(SEEDS)
    assert all(r['after_error']<r['before_error'] for r in faults['runs'])
    return {
        'schema':'ontos-l9-v59-v62-offline-1',
        'no_operational_actions':True,
        'seed_count':len(SEEDS),
        'v59':{'phase_count':4,'factor_rank':2,'steps':100,
               'energy_start':start_osc,'energy_end':potential_energy(s),
               'coherence_start':start_order,'coherence_end':order_parameter(s),
               'physical_validation':False},
        'v60':{'vertices':3,'edges':2,'steps':100,'energy_start':sheaf_start,
               'energy_end':sheaf_end,'physical_validation':False},
        'v61':faults,
        'v62':{**drift,
               'independent_model_p_0_1_checks4':theoretical_error(.1,3,correlation=0.),
               'common_cause_model_p_0_1_checks4':theoretical_error(.1,3,correlation=1.)},
        'source_suite_D_accuracy_reproduced':False,
        'source_suite_D_health_reproduced':False,
        'physical_energy_joules':'UNKNOWN',
        'deployment_verified':False,
    }


if __name__=='__main__':
    print(json.dumps(report(),sort_keys=True,indent=2,allow_nan=False))
