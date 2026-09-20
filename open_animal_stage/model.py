"""What a species has to hand over before it can take a seat.

ROSTER.md lists five gates a species must pass. Four of them are about data, and
prose cannot check them -- so they are here, as a shape with a validator, and a
species that does not satisfy it cannot be loaded at all.

    spec = BrainSpec(
        species="drosophila_male",
        neurons=[...],          # one Neuron per cell
        synapses=[...],         # (pre_index, post_index, weight)
        sensory={"sugar": [12, 88, ...], "bitter": [...]},
        motor={"declare_war": [4001, ...], "build": [...]},
        provenance={...},       # where every one of the above came from
    )
    spec.validate()             # raises, with the reason, or returns a report

WHY A DATACLASS AND NOT A DICT

Because the failure this guards against is a species that loads and is subtly
wrong: a synapse pointing past the end of the neuron table, a sensory set that
is empty, a motor group that overlaps another so one order always fires with
another. Every one of those produces a brain that runs and plays badly, and
"plays badly" is indistinguishable from "this animal is bad at strategy", which
is the conclusion nobody should be able to reach by accident.

PROVENANCE IS REQUIRED, NOT OPTIONAL

`provenance` must say where the neurons came from, where the signs came from,
and -- the one that matters -- how the sensory and motor sets were CHOSEN. The
gate in ROSTER.md says those must be "named from the source's own annotations,
not chosen by us because they gave a good result", and the only way to keep
anybody honest about that is to make them write down the annotation they used.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from .signs import Sign


@dataclass
class Neuron:
    """One cell. `ident` is whatever the source calls it, kept verbatim."""
    ident: str
    sign: Sign
    # Free-form, from the source: a cell type, a region, a marker. Not used by
    # the model; carried so a result can be traced back to a real annotation.
    label: str = ""


@dataclass
class BrainSpec:
    species: str
    neurons: List[Neuron]
    synapses: List[Tuple[int, int, float]]
    sensory: Dict[str, Sequence[int]]
    motor: Dict[str, Sequence[int]]
    provenance: Dict[str, str] = field(default_factory=dict)

    # Every key here must be present and non-empty. Named rather than checked
    # inline so the error can say which one and the list can be read.
    REQUIRED_PROVENANCE = (
        "neurons",       # which release, which version
        "signs",         # measured, predicted, or assumed -- and by whom
        "sensory",       # the annotation the sensory sets were taken from
        "motor",         # the same, for the motor sets
    )

    def validate(self):
        """Raise ValueError with a reason, or return a one-line report."""
        n = len(self.neurons)
        if n == 0:
            raise ValueError("%s: no neurons" % self.species)
        if not self.synapses:
            raise ValueError("%s: no synapses -- %d neurons wired to nothing"
                             % (self.species, n))

        # A synapse index past the end is the classic silent corruption: it
        # either throws deep inside a simulation loop or, worse, wraps.
        for k, (pre, post, w) in enumerate(self.synapses):
            if not (0 <= pre < n and 0 <= post < n):
                raise ValueError(
                    "%s: synapse %d connects %d -> %d, outside the %d neurons"
                    % (self.species, k, pre, post, n))
            if w == 0:
                raise ValueError("%s: synapse %d has weight 0, which is an edge "
                                 "that is not there -- drop it at export rather "
                                 "than carrying it" % (self.species, k))

        if not self.sensory:
            raise ValueError("%s: nothing to stimulate. A brain with no sensory "
                             "set cannot be given the game." % self.species)
        if not self.motor:
            raise ValueError("%s: nothing to read. A brain with no motor set "
                             "cannot answer." % self.species)

        for kind, groups in (("sensory", self.sensory), ("motor", self.motor)):
            for name, ids in groups.items():
                if len(ids) == 0:
                    raise ValueError("%s: %s group %r is empty, so that channel "
                                     "is wired to nothing and will look like the "
                                     "animal ignoring it"
                                     % (self.species, kind, name))
                for i in ids:
                    if not (0 <= i < n):
                        raise ValueError("%s: %s group %r names neuron %d, "
                                         "outside the %d neurons"
                                         % (self.species, kind, name, i, n))

        # OVERLAPPING MOTOR GROUPS ARE THE SUBTLE ONE. If two orders read the
        # same cells, they fire together, and the game sees a brain that always
        # does two things at once -- which reads as a decision rather than as a
        # wiring mistake.
        seen = {}
        for name, ids in self.motor.items():
            for i in ids:
                if i in seen:
                    raise ValueError(
                        "%s: neuron %d is in motor groups %r and %r. Two orders "
                        "reading one cell always fire together, and that looks "
                        "like a choice." % (self.species, i, seen[i], name))
                seen[i] = name

        missing = [k for k in self.REQUIRED_PROVENANCE
                   if not self.provenance.get(k)]
        if missing:
            raise ValueError(
                "%s: provenance is missing %s. ROSTER.md's gate is that sensory "
                "and motor sets are named from the source's own annotations and "
                "not chosen because they gave a good result; writing down which "
                "annotation is how that stays true."
                % (self.species, ", ".join(missing)))

        unknown = sum(1 for x in self.neurons if x.sign is Sign.UNKNOWN)
        return ("%s: %d neurons, %d synapses, %d sensory channel(s), "
                "%d motor group(s), %d neuron(s) of unknown sign (%.1f%%)"
                % (self.species, n, len(self.synapses), len(self.sensory),
                   len(self.motor), unknown, 100.0 * unknown / n))

    def measured_fraction(self):
        """How much of this brain has a sign that was not assumed, 0..100."""
        if not self.neurons:
            return 0.0
        known = sum(1 for x in self.neurons if x.sign is not Sign.UNKNOWN)
        return 100.0 * known / len(self.neurons)
