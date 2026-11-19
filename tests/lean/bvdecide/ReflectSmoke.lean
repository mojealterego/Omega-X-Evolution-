prelude
import Std.Tactic.BVDecide
import Std.Sat.CNF.Dimacs
set_option debug.skipKernelTC false
open Std.Sat Std.Tactic.BVDecide

def x : BVExpr 16 := .var 0
def y : BVExpr 16 := .var 1
def one : BVExpr 16 := .const 1
def zero : BVExpr 16 := .const 0
def two : BVExpr 16 := .const 2
def neg (a : BVExpr 16) : BVExpr 16 := .bin (.un .not a) .add one
def diseq (a b : BVExpr 16) : BVLogicalExpr := .not (.literal (.bin a .eq b))
def addCase := diseq (.bin x .add y) (.bin y .add x)
def subCase := diseq (.bin (.bin x .add y) .add (neg y)) x
def mulCase := diseq (.bin x .mul two) (.bin x .add x)
def xorCase := diseq (.bin (.bin x .xor y) .xor y) x
def andCase := diseq (.bin x .and y) (.bin y .and x)
def orCase := diseq (.bin x .or y) (.bin y .or x)
def satCase := diseq (.bin x .add y) x

def cases : List (String × BVLogicalExpr) :=
  [("add", addCase), ("sub", subCase), ("mul", mulCase), ("xor", xorCase), ("and", andCase), ("or", orCase)]

def main (args : List String) : IO Unit := do
  match args with
  | ["emit"] =>
    for (name, expr) in cases ++ [("sat", satCase)] do
      IO.FS.writeFile (name ++ ".cnf") (CNF.dimacs (AIG.toCNF expr.bitblast.relabelNat))
    IO.println "PASS Lean bitblast -> native DIMACS for 7 formulas"
  | ["check"] =>
    for (name, expr) in cases do
      let cert ← IO.FS.readFile (name ++ ".lrat")
      if !Reflect.verifyBVExpr expr cert then
        throw (IO.userError (name ++ ": LRAT rejected"))
      let actions ← LRAT.loadLRATProof (name ++ ".bin.lrat")
      if !LRAT.check actions (AIG.toCNF expr.bitblast.relabelNat) then
        throw (IO.userError (name ++ ": binary LRAT rejected"))
      if Reflect.verifyBVExpr expr "invalid\n" then
        throw (IO.userError (name ++ ": malformed certificate accepted"))
      if Reflect.verifyBVExpr satCase cert then
        throw (IO.userError (name ++ ": proof accepted for satisfiable formula"))
      IO.println ("PASS " ++ name ++ ": valid proof accepted, malformed/wrong formula rejected")
  | _ => throw (IO.userError "expected emit or check")
