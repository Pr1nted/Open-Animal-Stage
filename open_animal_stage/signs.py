"""Does a synapse excite or inhibit?

A leaky integrate-and-fire model has to know. A connectome does not say: it says
two cells touch, and how often. Every species on this stage answers the question
differently, and the difference is the single biggest source of "this model is
ours, not the animal's" in the whole project -- so it lives in one file, with the
provenance of each answer written next to it.

WHERE EACH SPECIES' SIGNS COME FROM

  drosophila_female   FlyWire's neurotransmitter predictions. Used by the Shiu
                      et al. model that Open Fly runs.
  drosophila_male     MaleCNS v1.0 ships predicted neurotransmitters for all
                      166,691 neurons. Same kind of answer as the female.
  zebrafish_larva     MEASURED, not predicted, and only for some cells. The
                      Fish1 specimen was imaged with confocal light microscopy
                      as well as EM: 26,915 cells are vglut2a-positive
                      (glutamatergic, excitatory) and 14,510 are gad1b-positive
                      (GABAergic, inhibitory). That is 41,425 of 187,053 -- 22%.
                      The other 78% have no label at all.
  c_elegans           Neurotransmitter assignments are published per neuron and
                      have been for years.
  ciona_larva         Not established per neuron in the connectome paper.

THE UNLABELLED ARE A DECISION, NOT A FACT

Three quarters of the fish is unlabelled. What we do with those cells decides
what the model is, and there is no neutral option:

  EXCITATORY    Assume the unlabelled are excitatory. Defensible -- glutamate is
                the commonest transmitter in a vertebrate brain -- and it makes
                a model that is four fifths assumption.
  DROP          Keep only the 41,425 cells with a measured label. An honest
                small model of a real subset, and a different animal: dropping
                78% of a brain is not the same brain with fewer neurons in it.
  INFER         Assign by a stated rule (region, morphology, a classifier).
                Only acceptable if the rule is written down BEFORE it is run
                and does not consult the result.

This module refuses to pick for you. `policy` is a required argument
everywhere, and it is recorded in the export metadata so that a later reader
can tell which of the three models they are looking at.
"""
from enum import Enum


class Sign(Enum):
    """What a presynaptic cell does to its targets."""
    EXCITATORY = 1
    INHIBITORY = -1
    UNKNOWN = 0


class Unlabelled(Enum):
    """What to do with a cell that carries no marker."""
    EXCITATORY = "excitatory"
    DROP = "drop"
    INFER = "infer"


# The Fish1 markers, and what each one means. Kept as data rather than as an
# if-chain so that adding a third marker is a line here and not a code change
# in three places.
FISH1_MARKERS = {
    "vglut2a": Sign.EXCITATORY,   # glutamatergic
    "gad1b":   Sign.INHIBITORY,   # GABAergic
}

# Counts from the Fish1 release, for the coverage report below. Recorded here
# so a report can say what fraction of a model is measured without querying
# CAVE, and so a drift between the release's numbers and ours is visible.
FISH1_RELEASE = {
    "somas": 187053,
    "vglut2a": 26915,
    "gad1b": 14510,
}


def fish1_sign(markers, policy):
    """The sign for one Fish1 cell.

    `markers` is what the light-microscopy tables say about it: a container of
    marker names. `policy` is an `Unlabelled`, and there is no default.

    Returns a `Sign`, or None meaning "this cell is not in the model", which is
    only possible under DROP.
    """
    if not isinstance(policy, Unlabelled):
        raise TypeError("policy must be an Unlabelled, not %r -- see the module "
                        "docstring: what happens to the unlabelled 78%% is a "
                        "modelling decision and cannot be defaulted"
                        % type(policy).__name__)

    hits = [FISH1_MARKERS[m] for m in markers if m in FISH1_MARKERS]

    # BOTH MARKERS IS NOT A TIE TO BREAK. A cell reported as both
    # vglut2a-positive and gad1b-positive is a measurement that contradicts
    # itself -- a segmentation error, a bleed-through, a genuinely dual
    # transmitter -- and picking one silently would bury it. It is unknown, and
    # the coverage report counts it.
    if len(set(hits)) > 1:
        return Sign.UNKNOWN if policy is not Unlabelled.DROP else None
    if hits:
        return hits[0]

    if policy is Unlabelled.EXCITATORY:
        return Sign.EXCITATORY
    if policy is Unlabelled.DROP:
        return None
    return Sign.UNKNOWN     # INFER: the rule runs elsewhere, and is preregistered


def coverage(labelled, total):
    """How much of a model is measured rather than assumed, as a percentage.

    Printed by the exporter and carried in the metadata. A model that is 22%
    measured is a different object from one that is 100% measured, and the
    number belongs somewhere a reader trips over it.
    """
    if total <= 0:
        return 0.0
    return 100.0 * labelled / total


def fish1_expected_coverage():
    """What the Fish1 release's own numbers imply, before any export runs."""
    lab = FISH1_RELEASE["vglut2a"] + FISH1_RELEASE["gad1b"]
    return coverage(lab, FISH1_RELEASE["somas"])
