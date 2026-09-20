"""Can a species load a brain that is subtly wrong?

    python3 tests/test_model.py

WHY THIS TEST EXISTS

Every failure below produces a brain that RUNS. A synapse pointing past the
neuron table, an empty sensory channel, two orders reading the same cell -- none
of them crashes, and all of them make the animal play badly. "Plays badly" is
indistinguishable from "this animal is bad at strategy", which is the conclusion
nobody should be able to reach because of a loading mistake.

So each case here is a wrong brain that the validator must refuse, and the test
is that it refuses for the RIGHT reason: the message has to name the thing, or
whoever hits it at three in the morning learns nothing.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from open_animal_stage.model import BrainSpec, Neuron    # noqa: E402
from open_animal_stage.signs import Sign                 # noqa: E402

checks = 0
fails = 0


def ok(cond, what):
    global checks, fails
    checks += 1
    print(("  ok    " if cond else "  FAIL  ") + what)
    if not cond:
        fails += 1


PROV = {"neurons": "toy v1", "signs": "assigned by hand for the test",
        "sensory": "toy annotation", "motor": "toy annotation"}


def spec(**over):
    base = dict(
        species="toy",
        neurons=[Neuron("n%d" % i, Sign.EXCITATORY) for i in range(10)],
        synapses=[(0, 1, 1.0), (1, 2, -0.5), (2, 3, 1.0)],
        sensory={"sugar": [0], "bitter": [1]},
        motor={"attack": [8], "build": [9]},
        provenance=dict(PROV),
    )
    base.update(over)
    return BrainSpec(**base)


def refuses(s, word, what):
    """It must raise, and the message must contain `word`."""
    try:
        s.validate()
    except ValueError as e:
        ok(word in str(e), what + "  [%s]" % str(e)[:64])
        return
    ok(False, what + "  (it was ACCEPTED)")


print("Model\n")
print("== a well-formed brain loads ==")
report = spec().validate()
ok("10 neurons" in report and "3 synapses" in report,
   "and the report says what was loaded: " + report[:58])

print("\n== A SYNAPSE THAT POINTS NOWHERE ==")
# The classic silent corruption: an index past the end either throws deep in a
# simulation loop or, in a language with no bounds check, reads whatever is next.
refuses(spec(synapses=[(0, 99, 1.0)]), "outside",
        "a synapse into neuron 99 of 10 is refused")
refuses(spec(synapses=[(-1, 0, 1.0)]), "outside",
        "and a negative index is too")

print("\n== an edge that is not an edge ==")
refuses(spec(synapses=[(0, 1, 0.0)]), "weight 0",
        "a zero-weight synapse is refused rather than carried")

print("\n== a channel wired to nothing ==")
# An empty sensory group does not crash. It makes the animal ignore that input,
# which reads as a decision.
refuses(spec(sensory={"sugar": []}), "empty",
        "an empty sensory channel is refused")
refuses(spec(motor={"attack": []}), "empty",
        "and an empty motor group is too")
refuses(spec(sensory={}), "cannot be given",
        "no sensory sets at all is refused")
refuses(spec(motor={}), "cannot answer",
        "and no motor sets at all")
refuses(spec(sensory={"sugar": [42]}), "outside",
        "a sensory group naming a neuron that does not exist")

print("\n== TWO ORDERS READING ONE CELL ==")
# The subtle one. Overlapping motor groups always fire together, and the game
# sees a brain that always does two things at once.
refuses(spec(motor={"attack": [8, 9], "build": [9]}), "always fire together",
        "overlapping motor groups are refused, and the message says why")

print("\n== provenance is required ==")
for key in BrainSpec.REQUIRED_PROVENANCE:
    p = dict(PROV)
    p.pop(key)
    refuses(spec(provenance=p), key, "a brain with no %r provenance" % key)
refuses(spec(provenance={}), "chosen because they gave a good result",
        "and the message says WHY it is required")

print("\n== how much of it is measured ==")
half = [Neuron("n%d" % i, Sign.EXCITATORY if i < 5 else Sign.UNKNOWN)
        for i in range(10)]
s = spec(neurons=half)
ok(abs(s.measured_fraction() - 50.0) < 1e-9,
   "a brain with half its signs unknown reports 50%")
ok("5 neuron(s) of unknown sign (50.0%)" in s.validate(),
   "and the load report says so, where a reader trips over it")
ok(spec(neurons=[]).measured_fraction() == 0.0,
   "an empty brain does not divide by zero")
refuses(spec(neurons=[]), "no neurons", "and is refused anyway")
refuses(spec(synapses=[]), "wired to nothing", "as is one with no synapses")

print("\n%d checks, %d failed" % (checks, fails))
sys.exit(1 if fails else 0)
