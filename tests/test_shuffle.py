"""Is the shuffled control actually a control?

    python3 tests/test_shuffle.py

WHY THIS TEST EXISTS

A brain against a shuffled copy of itself is the one comparison on this stage
that is not mostly about the mappings we wrote. That argument holds only if the
shuffle preserves everything except who connects to whom. If it also changes the
degree sequence, or the synapse count, or the weights, then the real brain wins
against a straw man and the result means nothing.

The test that matters is therefore not "does it shuffle" but "what did it keep".
And to show that the check has teeth, the same properties are run against
target_shuffle, a control that is deliberately wrong -- if both pass everything,
the test is not measuring anything.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from open_animal_stage.shuffle import (        # noqa: E402
    degree_preserving, target_shuffle, degrees, rewired_fraction)

checks = 0
fails = 0


def ok(cond, what):
    global checks, fails
    checks += 1
    print(("  ok    " if cond else "  FAIL  ") + what)
    if not cond:
        fails += 1


def make_net(n_nodes=400, n_edges=1200, seed=7):
    """A network with a HUB, because that is what a real brain has.

    400 nodes, not 120: the hub below takes 200 distinct sources, and an
    earlier version of this fixture asked for 200 out of range(1, 120), got
    119, and then tested that a "200-synapse hub" had shrunk. It had not. A
    fixture that cannot build what it describes tests something else."""
    rng = random.Random(seed)
    edges = set()
    while len(edges) < n_edges - 200:
        a, b = rng.randrange(n_nodes), rng.randrange(n_nodes)
        if a != b:
            edges.add((a, b))
    # node 0 receives 200 synapses: the hub.
    src = [x for x in range(1, n_nodes)]
    rng.shuffle(src)
    for a in src[:200]:
        edges.add((a, 0))
    return [(a, b, 1.0 + (a % 3)) for a, b in sorted(edges)]


net = make_net()
rng = random.Random(11)
shuf = degree_preserving(net, rng)
bad = target_shuffle(net, random.Random(11))

print("Shuffle\n")
print("== a control keeps everything but the wiring ==")
ok(len(shuf) == len(net), "the synapse count is unchanged")

o0, i0 = degrees(net)
o1, i1 = degrees(shuf)
ok(o0 == o1, "every neuron keeps its OUT-degree")
ok(i0 == i1, "every neuron keeps its IN-degree")

ok(sorted(e[2] for e in shuf) == sorted(e[2] for e in net),
   "the weights are the same multiset")
ok(len({(a, b) for a, b, _ in shuf}) == len(shuf),
   "and no two edges collapsed onto each other")
ok(not any(a == b for a, b, _ in shuf), "no self-loops were created")

print("\n== ...and it does move the wiring ==")
moved = rewired_fraction(net, shuf)
ok(moved > 0.5, "more than half the edges are somewhere else (%.0f%%)" % (moved * 100))

print("\n== WHAT THE CHEAP CONTROL ACTUALLY BREAKS ==")
# This section was written believing target_shuffle destroyed the degree
# sequence. It does not: permuting the postsynaptic column leaves the number of
# times each node appears as a target exactly as it was, so in-degree per node
# survives intact. The test said so and the belief was wrong.
#
# What it really does is quieter and worse. It pairs sources and targets at
# random, so some edges land on a==b and others land on a pair that already
# exists -- and the second kind silently MERGES, so the control ends up with
# fewer distinct synapses than the brain it is a control for.
ob, ib = degrees(bad)
ok(ob == o0, "target_shuffle keeps out-degree")
ok(ib == i0, "AND in-degree -- a permuted column cannot change either")

loops = sum(1 for a, b, _ in bad if a == b)
ok(loops > 0, "but it creates self-loops (%d of them)" % loops)

distinct_bad = len({(a, b) for a, b, _ in bad})
ok(distinct_bad < len(bad),
   "and collapses %d edges onto pairs that already existed"
   % (len(bad) - distinct_bad))
ok(len({(a, b) for a, b, _ in shuf}) == len(shuf),
   "which is exactly what degree_preserving refuses to do")

# THE POINT. A control with fewer synapses than the brain loses to it for a
# reason that has nothing to do with wiring.
ok(distinct_bad < len({(a, b) for a, b, _ in shuf}),
   "so the cheap control is a WEAKER network, not merely a rewired one")

print("\n== the same seed gives the same shuffle ==")
# A control that differs between two runs cannot be compared against anything.
again = degree_preserving(net, random.Random(11))
ok(again == shuf, "it is deterministic in its rng")
other = degree_preserving(net, random.Random(12))
ok(other != shuf, "and a different seed gives a different control")

print("\n== degenerate inputs ==")
ok(degree_preserving([], random.Random(1)) == [], "an empty network shuffles to itself")
ok(len(degree_preserving([(0, 1, 1.0)], random.Random(1))) == 1,
   "a single edge survives, with nothing to swap it with")
ok(rewired_fraction([], []) == 0.0, "and the rewired fraction of nothing is zero")

print("\n%d checks, %d failed" % (checks, fails))
sys.exit(1 if fails else 0)
