prelude
import Std.Tactic.BVDecide.LRAT.Parser
import Std.Tactic.BVDecide.LRAT.Checker
set_option debug.skipKernelTC false
open Std.Sat Std.Tactic.BVDecide.LRAT

def contradiction : CNF Nat := ⟨#[(CNF.Clause.empty.add 0 true), (CNF.Clause.empty.add 0 false)]⟩
def satisfiable : CNF Nat := ⟨#[(CNF.Clause.empty.add 0 true)]⟩
def expectedProof : Array IntAction := #[.addEmpty 3 #[1, 2]]

theorem contradiction_unsat : contradiction.Unsat :=
  check_sound expectedProof contradiction (by native_decide)
#print axioms contradiction_unsat

def main : IO Unit := do
  let txt ← loadLRATProof "false.lrat"
  let bin ← loadLRATProof "true.lrat"
  if txt != expectedProof || bin != expectedProof then
    throw (IO.userError "unexpected proof bytes")
  if !(check txt contradiction && check bin contradiction) then
    throw (IO.userError "valid LRAT rejected")
  if check txt satisfiable then
    throw (IO.userError "accepted proof for satisfiable CNF")
  if check #[.addEmpty 3 #[1]] contradiction then
    throw (IO.userError "accepted incomplete hint list")
  if check #[.addEmpty 3 #[1, 999]] contradiction then
    throw (IO.userError "accepted invalid clause ID")
  if check #[] contradiction then
    throw (IO.userError "accepted empty proof")
  IO.println "PASS LRAT checker: text, binary, wrong CNF, incomplete hints, invalid ID, empty proof"
