#!/usr/bin/env python3
import json
from pathlib import Path
source=Path('ReflectSmoke.lean').read_text().split('def main (args',1)[0]
for op in ('add','sub','mul','xor','and','or'):
    proof=Path(op+'.lrat').read_text()
    source+=f'\ntheorem {op}_unsat : {op}Case.Unsat :=\n  Reflect.unsat_of_verifyBVExpr_eq_true {op}Case {json.dumps(proof)} (by native_decide)\n#print axioms {op}_unsat\n'
Path('ReflectTheorems.lean').write_text(source)
