"""The only opponent on this stage that means what it looks like it means.

THE PROBLEM WITH EVERY OTHER PAIRING

A fly against a worm compares two mappings we wrote -- what counts as a sense,
what counts as an order, how long the brain runs -- far more than it compares
two animals. The mappings are separate code, written by us, and nearly all the
competence in a seat comes from them. A result from that pairing is a result
about our work.

A brain against a SHUFFLED COPY OF ITSELF holds all of that fixed. Same species,
same mapping, same neuron count, same synapse count, same in-degree and
out-degree for every cell, same distribution of weights, same sensory and motor
sets. The only thing that differs is which neuron is wired to which. If the real
wiring plays better than the shuffle, the wiring is doing something. If it does
not, it is not -- and that is worth knowing and worth publishing.

WHAT "SHUFFLED" HAS TO MEAN

A shuffle that changes the degree sequence is not a control, it is a different
animal. If the real brain has a hub with 4,000 outputs and the shuffle spreads
those over 4,000 cells with one each, the comparison is between a brain and a
mist, and of course the brain wins.

So: `degree_preserving` rewires by repeatedly swapping the targets of two edges,
which changes who connects to whom and leaves every neuron's in-degree and
out-degree exactly as it was. That is the standard configuration-model move and
it is the one this project uses.

`target_shuffle` is offered as well and is NOT a substitute -- but not for the
reason it looks like. Permuting the postsynaptic column preserves BOTH degrees:
each node appears as a target the same number of times, whatever order the
column is in. That was written here as "destroys in-degree" and it was wrong;
the test said so.

What it actually does is quieter. It pairs sources and targets at random, so
some edges land on a self-loop and others land on a pair that already exists --
and those MERGE. The control ends up with fewer distinct synapses than the brain
it is a control for, and then loses to it for a reason that has nothing to do
with wiring. That is the failure mode to remember: a bad control is usually not
obviously broken, it is slightly weaker.
"""
import random


def _edge_key(e):
    return (e[0], e[1])


def degree_preserving(edges, rng=None, swaps_per_edge=10):
    """Rewire by double-edge swaps. Every node keeps its in- and out-degree.

    `edges` is a sequence of (pre, post, weight). Returns a new list; the input
    is not touched.

    A swap takes two edges (a->b, c->d) and makes them (a->d, c->b). Both
    endpoints keep their degrees by construction, so there is no accounting to
    get wrong -- which is the reason to do it this way rather than by rebuilding
    from a degree sequence.

    A swap is REFUSED when it would make a self-loop or duplicate an edge that
    already exists. Refusing rather than retrying forever keeps the running time
    bounded; the cost is that the result is slightly less mixed than a perfect
    shuffle, and `swaps_per_edge` is how much slack that is given.
    """
    rng = rng or random.Random(0)
    out = [tuple(e) for e in edges]
    if len(out) < 2:
        return out

    present = {_edge_key(e) for e in out}
    attempts = len(out) * swaps_per_edge
    made = 0

    for _ in range(attempts):
        i = rng.randrange(len(out))
        j = rng.randrange(len(out))
        if i == j:
            continue
        a, b, wab = out[i]
        c, d, wcd = out[j]

        # A self-loop is not a synapse onto another cell, and a duplicate would
        # merge two edges into one and quietly drop a connection -- which would
        # change the synapse count and make the control weaker than the brain
        # for a reason that has nothing to do with wiring.
        if a == d or c == b:
            continue
        if (a, d) in present or (c, b) in present:
            continue

        present.discard((a, b))
        present.discard((c, d))
        # THE WEIGHTS TRAVEL WITH THE EDGE, not with the position. A swap that
        # left wab on the (a,d) slot would be shuffling wiring and weights
        # together, and a difference could then be either one.
        out[i] = (a, d, wab)
        out[j] = (c, b, wcd)
        present.add((a, d))
        present.add((c, b))
        made += 1

    return out


def target_shuffle(edges, rng=None):
    """Permute the postsynaptic column. A DELIBERATELY BAD CONTROL.

    Out-degree survives, in-degree does not: a neuron that received 4,000
    synapses now receives whatever the permutation happens to give it. Provided
    so the difference between this and a real control can be demonstrated rather
    than asserted -- see the test.
    """
    rng = rng or random.Random(0)
    out = [tuple(e) for e in edges]
    posts = [e[1] for e in out]
    rng.shuffle(posts)
    return [(e[0], p, e[2]) for e, p in zip(out, posts)]


def degrees(edges):
    """(out-degree, in-degree) per node, as two dicts. For checking a control."""
    outd, ind = {}, {}
    for pre, post, _ in edges:
        outd[pre] = outd.get(pre, 0) + 1
        ind[post] = ind.get(post, 0) + 1
    return outd, ind


def rewired_fraction(before, after):
    """How much of the wiring actually moved, 0..1.

    A control that reports itself as shuffled and is 98% identical is not a
    control. This is the number to print beside any shuffle result.
    """
    if not before:
        return 0.0
    a = {_edge_key(e) for e in before}
    b = {_edge_key(e) for e in after}
    return len(a - b) / len(a)
