"""Several brains, one world, one turn at a time.

Open Fly has one seat and one worker. This is the part that makes a stage: a
list of seats, each with its own species, its own brain, and its own mapping
from the game to senses and from spikes to orders.

    stage = Stage(game, [Seat("drosophila_male", brain, encode, decode),
                         Seat("zebrafish_larva", brain2, encode2, decode2)])
    while stage.turn():
        ...

WHAT THIS DELIBERATELY DOES NOT DO

It does not run brains in parallel. The game is turn-based, so it does not have
to, and a stage that is correct before it is fast is the right order -- the
browser build puts each species in its own worker, and that is a transport
detail rather than a change to this loop.

SIMULATED TIME IS THE UNIT, NOT WALL-CLOCK

Every seat runs for a duration of its OWN simulated time, stated per species.
A stage that gave every animal the same number of milliseconds of CPU would be
comparing computers. A worm at 302 neurons and a zebrafish at 187,053 are not
the same amount of work by three orders of magnitude, and the honest thing is
to let the fish take as long as it takes and SHOW the viewer the wait -- which
is why `Seat` records wall-clock per turn even though nothing in the loop uses
it to decide anything.

A SEAT THAT FAILS DOES NOT TAKE THE STAGE WITH IT

If one brain raises, that seat passes for the turn and the failure is recorded
against it. A stage of four animals where one is broken should show three
playing and one with a visible fault, not a blank page -- and a seat that is
quietly skipped is worse than one that is visibly broken.
"""
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class Seat:
    """One animal at one country.

    `encode(game, country)` returns {channel: amount} for the brain's sensory
    sets. `decode(counts)` turns spike counts into a list of orders. Both are
    per-species and both are preregistered: they are where nearly all the
    competence in a seat comes from, and pretending otherwise is the mistake
    PREREGISTRATION.md exists to prevent.
    """
    species: str
    brain: object
    encode: Callable
    decode: Callable
    window_ms: float
    country: Optional[int] = None

    turns: int = 0
    orders_given: int = 0
    spikes: int = 0
    faults: List[str] = field(default_factory=list)
    last_wall_ms: float = 0.0
    total_wall_ms: float = 0.0

    def play(self, game):
        """One turn. Returns the orders given, and never raises."""
        started = time.perf_counter()
        try:
            stimulus = self.encode(game, self.country)
            for channel, amount in stimulus.items():
                ids = self.brain.spec.sensory.get(channel)
                if ids is None:
                    # A mapping naming a channel the brain does not have is a
                    # mismatch between the encode and the spec, and it is
                    # silent: the stimulus simply goes nowhere. Recorded as a
                    # fault rather than ignored.
                    raise KeyError("encode produced channel %r, which %s's "
                                   "brain does not have" % (channel, self.species))
                self.brain.stimulate(ids, amount)

            counts = self.brain.run(self.window_ms)
            self.spikes += sum(counts.values())
            orders = self.decode(counts) or []
            for o in orders:
                game.order(self.country, o)
            self.orders_given += len(orders)
            self.turns += 1
            return orders
        except Exception as e:
            # One broken brain must not take the stage with it.
            self.faults.append("%s: %s" % (type(e).__name__, e))
            return []
        finally:
            self.last_wall_ms = (time.perf_counter() - started) * 1000.0
            self.total_wall_ms += self.last_wall_ms


class Stage:
    def __init__(self, game, seats: List[Seat]):
        if not seats:
            raise ValueError("a stage with no seats has nothing to show")
        # Two animals on one country would issue contradictory orders for the
        # same seat, and the game would take whichever arrived last -- which
        # looks like one of them losing.
        taken = {}
        for s in seats:
            if s.country is None:
                raise ValueError("seat %r has no country" % s.species)
            if s.country in taken:
                raise ValueError(
                    "seats %r and %r are both on country %s; two brains giving "
                    "orders to one country is not a pairing, it is a race"
                    % (taken[s.country], s.species, s.country))
            taken[s.country] = s.species
        self.game = game
        self.seats = seats
        self.turn_number = 0

    def turn(self) -> bool:
        """Play one game turn: every seat in order, then the world advances."""
        if self.game.finished():
            return False
        for seat in self.seats:
            seat.play(self.game)
        self.game.advance()
        self.turn_number += 1
        return True

    def report(self) -> List[Dict]:
        """What each seat did, including how long it made everyone wait."""
        out = []
        for s in self.seats:
            out.append({
                "species": s.species,
                "country": s.country,
                "turns": s.turns,
                "orders": s.orders_given,
                "spikes": s.spikes,
                "faults": len(s.faults),
                "first_fault": s.faults[0] if s.faults else None,
                "ms_per_turn": round(s.total_wall_ms / s.turns, 2) if s.turns else None,
            })
        return out
