#!/usr/bin/env python3
"""Fail-closed native Lean acceptance for the bootstrap additive fragment."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from omega_x_evolution.lean_native import check_lean
from omega_x_evolution.polyglot import Program


def main() -> int:
    x,y,z=('x',),('y',),('lit',0)
    obligations = (
        ('LEAN-CORE-01', ('sub',('add',x,y),y), x, True),
        ('LEAN-CORE-02', ('add',x,z), x, True),
        ('LEAN-CORE-03', ('sub',y,y), z, True),
        ('LEAN-CORE-04', ('add',x,('add',('lit',65535),('lit',1))), ('add',x,z), True),
        ('LEAN-CORE-05', x, y, False),
    )
    passed = True
    for ident,left,right,expected in obligations:
        result = check_lean(Program(left), Program(right), core_only=True)
        ok = (result['strategy']=='core-addsub' and result['proved'] is expected and
              result['status']==('checked' if expected else 'rejected'))
        passed &= ok
        print(json.dumps({'id':ident,'expected':expected,'pass':ok,'report':result},sort_keys=True))
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
