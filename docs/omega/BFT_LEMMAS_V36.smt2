; Fixed, independent integer proof obligations for the cardinality model.
; A and B are quorum voter sets in a universe of N; I is intersection size.
; This is not a proof of state-machine liveness or implementation equivalence.
(set-logic QF_LIA)
(set-option :timeout 3000)
(declare-const n Int)
(declare-const f Int)
(declare-const a Int)
(declare-const b Int)
(declare-const i Int)
(assert (and (>= n 1) (>= f 0) (> n (* 3 f))))
(assert (and (>= a (- n f)) (<= a n) (>= b (- n f)) (<= b n)))
(assert (and (>= i 0) (<= i a) (<= i b) (<= (- (+ a b) i) n)))
; Counterexample: every voter in the intersection could be Byzantine.
(assert (<= i f))
(check-sat)
(reset)
; Distinct consecutive leader identities, with at most f faulty identities.
; A rotation of f+1 distinct identities cannot consist exclusively of faults.
(set-logic QF_LIA)
(set-option :timeout 3000)
(declare-const n Int)
(declare-const f Int)
(declare-const leaders Int)
(declare-const faulty_leaders Int)
(assert (and (>= n 1) (>= f 0) (> n (* 3 f))))
(assert (and (= leaders (+ f 1)) (<= leaders n)))
(assert (and (>= faulty_leaders 0) (<= faulty_leaders f)))
; Counterexample: all leaders are faulty.
(assert (= leaders faulty_leaders))
(check-sat)
