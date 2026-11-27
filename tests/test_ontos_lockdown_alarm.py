from itertools import combinations

import pytest

from omega_x_evolution.ontos_v63_interface import CAPABILITIES, Frame, Session, transition


@pytest.mark.parametrize('phase',['IDLE','OBSERVED','ASSESSED','PROPOSED_C','PROPOSED_D','MODEL_APPROVED','LOCKDOWN'])
def test_alarm_is_sticky_in_every_phase(phase):
    for n in range(4):
        for combo in combinations(sorted(CAPABILITIES),n):
            root=frozenset(combo)
            if phase.startswith('PROPOSED') and not root:
                continue
            caps=frozenset() if phase=='LOCKDOWN' else root
            pending=sorted(caps)[0] if phase.startswith('PROPOSED') else None
            start=Session(root,caps,12,phase=phase,pending_cap=pending)
            alarm=transition(start,Frame('B','alarm','alarm',1,alarm=True))
            assert alarm.phase=='LOCKDOWN' and not alarm.caps and alarm.pending_cap is None
            restart=transition(alarm,Frame('E','restart','restart',2))
            assert restart.phase=='LOCKDOWN' and not restart.caps
            with pytest.raises(ValueError): transition(restart,Frame('A','observe','obs',3))
            assert not restart.operational_capabilities_granted
