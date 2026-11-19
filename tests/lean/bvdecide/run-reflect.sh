#!/usr/bin/env bash
set -euo pipefail
: "${LEAN:?}" "${LEAN_PATH:?}" "${CADICAL:?}" "${LRAT_CHECKER:?}"
cd -- "$(dirname -- "$0")"
flags=(-t 0 -DwarningAsError=true -Dinterpreter.prefer_native=false)
"$LEAN" "${flags[@]}" --run ReflectSmoke.lean emit
for op in add sub mul xor and or; do
  rc=0
  timeout 45 "$CADICAL" --seed=0 --plain --lrat --no-binary "$op.cnf" "$op.lrat" > "$op-solver.log" 2>&1 || rc=$?
  [[ "$rc" == 20 && -s "$op.lrat" ]] || { echo "FAIL $op solver exit=$rc"; exit 1; }
  rc=0
  timeout 45 "$CADICAL" --seed=0 --plain --lrat --binary "$op.cnf" "$op.bin.lrat" > "$op-binary-solver.log" 2>&1 || rc=$?
  [[ "$rc" == 20 && -s "$op.bin.lrat" ]] || { echo "FAIL $op binary solver exit=$rc"; exit 1; }
  timeout 45 "$LRAT_CHECKER" "$op.cnf" "$op.bin.lrat" > "$op-checker.log" 2>&1
  grep -q 'VERIFIED' "$op-checker.log" || { cat "$op-checker.log"; exit 1; }
  echo "PASS $op independent Isabelle-exported LRAT checker"
done
rc=0
timeout 45 "$CADICAL" sat.cnf > sat-solver.log 2>&1 || rc=$?
[[ "$rc" == 10 ]] || { echo "FAIL negative SAT exit=$rc"; exit 1; }
"$LEAN" "${flags[@]}" --run ReflectSmoke.lean check
python3 generate-theorems.py
"$LEAN" "${flags[@]}" ReflectTheorems.lean
