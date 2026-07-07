import Mathlib
import CCD.Containment
import CCD.Functionality

/-!
# Causal Controlled Degradation (Algorithm 1)

Formalizes CCD and its guarantees (**Prop. "Correctness and complexity of CCD"**):
* **Correctness** — assuming an exact functionality estimate, any intervention returned
  by CCD is a solution to the degradation problem.
* **Complexity** — CCD runs in `O(|X| (|V| + |U| + |𝓔|) + c)` time.

TODO: the `ccd` procedure and its correctness/complexity theorems, building on
`CCD.Containment` and `CCD.Functionality`.
-/

namespace CCD

-- TODO: `def ccd ...`, `theorem ccd_correct ...`, `theorem ccd_complexity ...`.

end CCD
