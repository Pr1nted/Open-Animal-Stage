"""Does the reference neuron behave like a neuron?

    python3 tests/test_lif.py

WHY THIS TEST EXISTS

This core is what the species with no published model will run -- the zebrafish,
the larva, the worm, the sea squirt. For those, the model is OURS, which means
nobody else's paper will catch it being wrong. The properties below are the ones
that would let a broken integrator look like a quiet animal:

  a brain at rest that fires anyway     -> every species looks frantic
  a brain that never fires              -> every species looks dead
  a delay that is not applied           -> the whole network resolves in one
                                           step, which is not a brain
  an inhibitory synapse that excites    -> the sign work in signs.py is undone
                                           here, silently
  an answer that depends on dt          -> the result is about the step size

Rates are compared as inequalities, not against fitted numbers. A test that
pins 5 spikes in 50 ms would break the first time a constant is tuned and would
be measuring the constant, not the neuron.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from open_animal_stage.lif import Brain, Params        # noqa: E402
from open_animal_stage.model import BrainSpec, Neuron  # noqa: E402
from open_animal_stage.signs import Sign               # noqa: E402

checks = 0
fails = 0


def ok(cond, what):
    global checks, fails
    checks += 1
    print(("  ok    " if cond else "  FAIL  ") + what)
    if not cond:
        fails += 1


# The fly model's constants, used here because they are a published set of
# numbers that produce a working neuron -- NOT because a sea squirt has a 20 ms
# membrane. Each species picks its own and preregisters them.
def params(**over):
    base = dict(v_rest=-52.0, v_reset=-52.0, v_threshold=-45.0, tau_m=20.0,
                tau_s=5.0, t_refractory=2.2, t_delay=1.8, dt=0.1)
    base.update(over)
    return Params(**base)


PROV = {"neurons": "t", "signs": "t", "sensory": "t", "motor": "t"}


def pair(sign=Sign.EXCITATORY, w=50.0):
    """Two neurons, 0 -> 1, with the presynaptic sign under test."""
    ns = [Neuron("a", sign), Neuron("b", Sign.EXCITATORY)]
    return BrainSpec("toy", ns, [(0, 1, w)], {"in": [0]}, {"out": [1]}, dict(PROV))


def drive(brain, amount, ms, per_ms=1.0):
    """Sustained input, the way an encode actually delivers it."""
    total = {}
    for _ in range(int(ms / per_ms)):
        brain.stimulate([0], amount)
        for k, v in brain.run(per_ms).items():
            total[k] = total.get(k, 0) + v
    return total


print("LIF\n")
print("== silence and threshold ==")
b = Brain(pair(), params())
ok(b.run(100.0) == {}, "a brain with no input does not fire")
b = Brain(pair(), params())
b.stimulate([0], 30.0)
ok(b.run(50.0) == {}, "and a sub-threshold kick does not either")
b = Brain(pair(), params())
b.stimulate([0], 60.0)
ok(b.run(50.0).get(0, 0) == 1, "a supra-threshold kick fires once")

print("\n== A SPIKE ARRIVES LATER THAN IT LEAVES ==")
# Without the delay the whole network resolves within one step, which is not a
# brain -- it is a boolean circuit.
#
# Measured as a GAP, not against a fixed millisecond. The first version of this
# asserted the presynaptic neuron fires within 1 ms of a supra-threshold kick;
# with tau_m = 20 ms it takes over 3, and the test was measuring the membrane
# time constant while claiming to measure the delay.
b = Brain(pair(), params())
b.stimulate([0], 60.0)
first = {}
p0 = params()
for step in range(400):                      # 40 ms in 0.1 ms slices
    for i in b.run(p0.dt):
        first.setdefault(i, step * p0.dt)
ok(0 in first, "the presynaptic neuron fires (at %.1f ms)" % first.get(0, -1))
ok(1 in first, "and so does its target (at %.1f ms)" % first.get(1, -1))
if 0 in first and 1 in first:
    gap = first[1] - first[0]
    ok(gap >= p0.t_delay,
       "the target fires at least the %.1f ms delay later (%.1f ms)"
       % (p0.t_delay, gap))
    # And not MUCH later than the delay plus its own charging time -- a gap of
    # twenty milliseconds would mean the delay is being applied repeatedly.
    ok(gap < 25.0, "and not implausibly later (%.1f ms)" % gap)

print("\n== the sign survives the synapse ==")
exc = drive(Brain(pair(Sign.EXCITATORY), params()), 8.0, 60.0)
inh = drive(Brain(pair(Sign.INHIBITORY), params()), 8.0, 60.0)
ok(exc.get(0, 0) > 0, "the driven neuron fires either way (%d)" % exc.get(0, 0))
ok(exc.get(0, 0) == inh.get(0, 0),
   "at the same rate -- the sign is about its TARGETS, not itself")
ok(exc.get(1, 0) > 0, "an excitatory presynaptic neuron makes its target fire")
ok(inh.get(1, 0) < exc.get(1, 0),
   "and an inhibitory one does not (%d vs %d)" % (inh.get(1, 0), exc.get(1, 0)))

print("\n== an unknown sign is dropped, not assumed ==")
# signs.py refuses to guess; this is where that refusal has to hold.
unk = drive(Brain(pair(Sign.UNKNOWN), params()), 8.0, 60.0)
ok(unk.get(0, 0) > 0, "the unknown-sign neuron itself still fires")
ok(unk.get(1, 0) == 0,
   "but its synapse is not carried, so the target is untouched")

print("\n== the refractory period bounds the rate ==")
hard = drive(Brain(pair(), params()), 200.0, 100.0)
p = params()
ceiling = 100.0 / p.t_refractory
ok(hard.get(0, 0) <= ceiling,
   "however hard it is driven, %d spikes is under the %.0f the refractory "
   "period allows" % (hard.get(0, 0), ceiling))
ok(hard.get(0, 0) > 10, "and it is genuinely firing fast (%d)" % hard.get(0, 0))

print("\n== THE ANSWER IS NOT AN ARTEFACT OF THE STEP SIZE ==")
coarse = drive(Brain(pair(), params(dt=0.1)), 8.0, 60.0).get(0, 0)
fine = drive(Brain(pair(), params(dt=0.025)), 8.0, 60.0).get(0, 0)
ok(abs(coarse - fine) <= max(1, coarse * 0.25),
   "halving dt twice barely moves the count (%d vs %d)" % (coarse, fine))

print("\n== the parameters refuse to be nonsense ==")


def refuses(kw, word, what):
    try:
        params(**kw).check()
    except ValueError as e:
        ok(word in str(e), what + "  [%s]" % str(e)[:52])
        return
    ok(False, what + "  (accepted)")


refuses(dict(dt=0), "positive", "a zero step")
refuses(dict(dt=10.0), "artefact", "a step larger than the time constants")
refuses(dict(v_threshold=-60.0), "fires for ever", "a threshold below rest")
refuses(dict(t_refractory=-1.0), "negative", "a negative refractory period")
ok(params().check() is True, "and a sane set passes")

print("\n== reset puts it back ==")
b = Brain(pair(), params())
drive(b, 8.0, 40.0)
b.reset()
ok(b.run(100.0) == {}, "after reset, an undriven brain is silent again")

print("\n%d checks, %d failed" % (checks, fails))
sys.exit(1 if fails else 0)
