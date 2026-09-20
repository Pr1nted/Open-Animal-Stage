"""A leaky integrate-and-fire core, in plain Python, for one decision window.

WHAT THIS IS AND IS NOT

It is the reference implementation: readable, dependency-free, and slow. Its job
is to be the thing a faster implementation is checked against -- the browser
worker, or a Brian2 build for a species that has one -- not to run 187,053
neurons in a page.

Open Fly does not use this. It runs the Shiu et al. model through Brian2 and
matches it spike for spike, and that model's constants are its own. THIS core
exists for the species that have no published model: the zebrafish, the larva,
the worm, the sea squirt. For those, the model is ours, and a model that is ours
needs an implementation somebody can read in one sitting.

THE EQUATIONS

    dv/dt = (v_rest - v + g) / tau_m          membrane, leaky toward rest
    dg/dt = -g / tau_s                        synaptic input, decaying

A spike when v > v_threshold; v is then held at v_reset for the refractory
period and g is cleared. A presynaptic spike adds (weight x sign) to the
target's g after the transmission delay.

This is the same shape as the fly model, deliberately, so that a species run
here and a species run in Brian2 are not two different theories of a neuron.

WHAT IT REFUSES TO GUESS

Every constant is an argument with no default. A membrane time constant is a
claim about an animal, and a core that quietly supplies 20 ms for a sea squirt
is making that claim on the species' behalf. `Params` has to be constructed, and
each species' values are preregistered with its mapping.
"""
from dataclasses import dataclass
from typing import Dict, List, Sequence

from .signs import Sign


@dataclass
class Params:
    """Every one is a claim about an animal. None has a default."""
    v_rest: float       # mV
    v_reset: float      # mV
    v_threshold: float  # mV
    tau_m: float        # ms, membrane
    tau_s: float        # ms, synaptic
    t_refractory: float # ms
    t_delay: float      # ms, presynaptic to postsynaptic
    dt: float           # ms, integration step

    def check(self):
        if self.dt <= 0:
            raise ValueError("dt must be positive")
        # A step at or above the smaller time constant does not integrate the
        # equation, it replaces it with something else that happens to run.
        smallest = min(self.tau_m, self.tau_s)
        if self.dt > smallest / 2.0:
            raise ValueError(
                "dt=%g is more than half the smallest time constant (%g). "
                "The result would be an artefact of the step size, not of the "
                "model." % (self.dt, smallest))
        if self.v_threshold <= self.v_rest:
            raise ValueError(
                "threshold %g is at or below rest %g, so every neuron fires "
                "for ever with no input at all"
                % (self.v_threshold, self.v_rest))
        if self.t_refractory < 0 or self.t_delay < 0:
            raise ValueError("a refractory period or delay cannot be negative")
        return True


class Brain:
    """One network, built once, run in windows.

    Built once because rebuilding the synapse table per turn is what makes a
    whole-brain model unusable in a game -- the same reason Open Fly departs
    from the published model.py.
    """

    def __init__(self, spec, params):
        params.check()
        self.spec = spec
        self.p = params
        n = len(spec.neurons)
        self.n = n

        # Outgoing edges per neuron, with the sign folded in ONCE at build
        # time. A sign applied per spike is the same arithmetic done fifteen
        # million times a window.
        self.out: List[List] = [[] for _ in range(n)]
        for pre, post, w in spec.synapses:
            s = spec.neurons[pre].sign
            if s is Sign.UNKNOWN:
                # An unknown sign is not zero and not excitatory. A brain
                # carrying them has to say what it did; the spec's report gives
                # the count, and the export's policy gives the reason.
                continue
            self.out[pre].append((post, w * s.value))

        self.v = [params.v_rest] * n
        self.g = [0.0] * n
        self.refractory_until = [-1.0] * n
        self.t = 0.0
        # Spikes in flight: index by the step they land on.
        self._pending: Dict[int, List] = {}

    def stimulate(self, indices: Sequence[int], amount: float):
        """Inject into a sensory set, as the game's encode does."""
        for i in indices:
            self.g[i] += amount

    def run(self, duration_ms: float) -> Dict[int, int]:
        """Advance by `duration_ms`. Returns spike counts per neuron index."""
        p = self.p
        steps = int(round(duration_ms / p.dt))
        counts: Dict[int, int] = {}
        delay_steps = max(1, int(round(p.t_delay / p.dt)))

        for _ in range(steps):
            step = int(round(self.t / p.dt))
            for post, w in self._pending.pop(step, ()):
                self.g[post] += w

            fired = []
            for i in range(self.n):
                if self.t < self.refractory_until[i]:
                    # Held at reset, and NOT integrating. The fly model's
                    # equations carry `(unless refractory)`, and dropping input
                    # arriving during the refractory period is part of the
                    # model rather than an optimisation.
                    self.v[i] = p.v_reset
                    self.g[i] += -self.g[i] * (p.dt / p.tau_s)
                    continue
                dv = (p.v_rest - self.v[i] + self.g[i]) / p.tau_m
                self.v[i] += dv * p.dt
                self.g[i] += (-self.g[i] / p.tau_s) * p.dt
                if self.v[i] > p.v_threshold:
                    fired.append(i)

            for i in fired:
                self.v[i] = p.v_reset
                self.g[i] = 0.0
                self.refractory_until[i] = self.t + p.t_refractory
                counts[i] = counts.get(i, 0) + 1
                land = step + delay_steps
                self._pending.setdefault(land, []).extend(self.out[i])

            self.t += p.dt
        return counts

    def reset(self):
        """Back to rest, with nothing in flight. Between turns, not within."""
        self.v = [self.p.v_rest] * self.n
        self.g = [0.0] * self.n
        self.refractory_until = [-1.0] * self.n
        self._pending.clear()
        self.t = 0.0
