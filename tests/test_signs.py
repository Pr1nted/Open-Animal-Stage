"""Does a synapse excite or inhibit, and do we admit when we do not know?

    python3 tests/test_signs.py

WHY THIS TEST EXISTS

The sign of a synapse is where a connectome stops being data and starts being
our model. Three quarters of the Fish1 cells carry no marker, so three quarters
of any fish model is a decision somebody made -- and the failure this guards
against is that decision being made silently, by a default argument or by a
tie-break, and then reported as though the data said it.

So the properties under test are not "does it return excitatory for vglut2a".
They are: can the policy be defaulted (no), does a contradictory measurement
get quietly resolved (no), and does the coverage number tell the truth about
how much of the model is measured.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from open_animal_stage.signs import (          # noqa: E402
    Sign, Unlabelled, fish1_sign, coverage, fish1_expected_coverage,
    FISH1_RELEASE)

checks = 0
fails = 0


def ok(cond, what):
    global checks, fails
    checks += 1
    print(("  ok    " if cond else "  FAIL  ") + what)
    if not cond:
        fails += 1


print("Signs\n")
print("== the measured cells ==")
ok(fish1_sign(["vglut2a"], Unlabelled.DROP) is Sign.EXCITATORY,
   "vglut2a is glutamatergic, so excitatory")
ok(fish1_sign(["gad1b"], Unlabelled.DROP) is Sign.INHIBITORY,
   "gad1b is GABAergic, so inhibitory")
ok(fish1_sign(["vglut2a", "something_else"], Unlabelled.DROP) is Sign.EXCITATORY,
   "an unrelated marker alongside one we know does not confuse it")

print("\n== THE POLICY CANNOT BE DEFAULTED ==")
# The one that matters. A default here would mean the commonest way to call
# this function also silently decides what 78% of the fish is.
try:
    fish1_sign(["vglut2a"])
    ok(False, "calling it with no policy is refused")
except TypeError:
    ok(True, "calling it with no policy is refused")
try:
    fish1_sign([], "excitatory")
    ok(False, "a policy that merely looks right is refused")
except TypeError:
    ok(True, "a string that merely looks like a policy is refused")

print("\n== A CONTRADICTION IS NOT A TIE TO BREAK ==")
# A cell reported as both excitatory and inhibitory is a measurement
# disagreeing with itself. Picking one would bury it.
both = ["vglut2a", "gad1b"]
ok(fish1_sign(both, Unlabelled.EXCITATORY) is Sign.UNKNOWN,
   "a cell marked both ways is UNKNOWN, not the first one listed")
ok(fish1_sign(both, Unlabelled.INFER) is Sign.UNKNOWN,
   "and under INFER too")
ok(fish1_sign(both, Unlabelled.DROP) is None,
   "and under DROP it leaves the model entirely")
ok(fish1_sign(list(reversed(both)), Unlabelled.EXCITATORY) is Sign.UNKNOWN,
   "and the answer does not depend on the order the markers arrived in")

print("\n== the three policies do three different things ==")
ok(fish1_sign([], Unlabelled.EXCITATORY) is Sign.EXCITATORY,
   "EXCITATORY assumes the unlabelled are excitatory")
ok(fish1_sign([], Unlabelled.DROP) is None,
   "DROP leaves them out of the model")
ok(fish1_sign([], Unlabelled.INFER) is Sign.UNKNOWN,
   "INFER marks them for a rule that runs elsewhere")
ok(len({fish1_sign([], p) for p in Unlabelled}) == 3,
   "and no two policies agree on an unlabelled cell")

print("\n== coverage tells the truth ==")
ok(coverage(0, 100) == 0.0, "nothing measured is 0%")
ok(coverage(100, 100) == 100.0, "everything measured is 100%")
ok(coverage(5, 0) == 0.0, "and a model with no cells does not divide by zero")

pct = fish1_expected_coverage()
ok(21.0 < pct < 23.0,
   "Fish1 is about 22%% measured, from the release's own counts (%.1f%%)" % pct)
# The number above is arithmetic on three constants copied from the release.
# If somebody edits one of them, this says so rather than letting a quietly
# wrong coverage figure into the metadata.
ok(FISH1_RELEASE["vglut2a"] + FISH1_RELEASE["gad1b"] < FISH1_RELEASE["somas"],
   "and the labelled cells are a subset of the somas, not more than all of them")

print("\n%d checks, %d failed" % (checks, fails))
sys.exit(1 if fails else 0)
