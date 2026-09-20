"""Do several brains share a world without spoiling each other's turn?

    python3 tests/test_stage.py

WHY THIS TEST EXISTS

The stage is the only part of this project Open Fly does not already have, so
it is the part with no prior art to be wrong about. Three failures matter:

  two seats on one country    Not a pairing, a race: the game takes whichever
                              order arrived last, and one animal looks like it
                              lost. Refused at construction.
  one broken brain            A stage of four where one raises must show three
                              playing and one visibly faulted -- not a blank
                              page, and not a seat quietly skipped, which is
                              worse because it looks like the animal choosing
                              to do nothing.
  an encode naming a channel  The stimulus goes nowhere and the animal looks
  the brain does not have     thoughtful. Recorded as a fault.

The brains here are stubs. What is under test is the loop, not the neuron --
test_lif.py owns that.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from open_animal_stage.stage import Seat, Stage     # noqa: E402

checks = 0
fails = 0


def ok(cond, what):
    global checks, fails
    checks += 1
    print(("  ok    " if cond else "  FAIL  ") + what)
    if not cond:
        fails += 1


class FakeGame:
    def __init__(self, turns=5):
        self.left = turns
        self.given = []

    def order(self, country, what):
        self.given.append((self.left, country, what))

    def advance(self):
        self.left -= 1

    def finished(self):
        return self.left <= 0


class StubBrain:
    """A brain shaped like the real one, with the spec the stage reads."""
    class Spec:
        sensory = {"sugar": [0, 1], "bitter": [2]}
    spec = Spec()

    def __init__(self, spikes=3, raises=None):
        self.spikes = spikes
        self.raises = raises
        self.stimulated = []

    def stimulate(self, ids, amount):
        self.stimulated.append((tuple(ids), amount))

    def run(self, ms):
        if self.raises:
            raise self.raises
        return {9: self.spikes}


def enc(game, country):
    return {"sugar": 1.0}


def dec(counts):
    return ["attack"] * (1 if counts.get(9, 0) > 0 else 0)


def seat(name, country, **kw):
    return Seat(name, StubBrain(**kw), enc, dec, window_ms=10.0, country=country)


print("Stage\n")
print("== several animals share one world ==")
g = FakeGame(4)
st = Stage(g, [seat("fly", 1), seat("fish", 2), seat("worm", 3)])
played = 0
while st.turn():
    played += 1
ok(played == 4, "the stage plays until the game says it is over (%d turns)" % played)
ok(len(g.given) == 12, "three seats times four turns is twelve orders (%d)" % len(g.given))
ok({c for _, c, _ in g.given} == {1, 2, 3},
   "and every seat reached its own country")
r = {x["species"]: x for x in st.report()}
ok(all(x["turns"] == 4 for x in r.values()), "each seat took every turn")
ok(all(x["faults"] == 0 for x in r.values()), "with no faults")

print("\n== TWO SEATS ON ONE COUNTRY IS A RACE, NOT A PAIRING ==")
try:
    Stage(FakeGame(), [seat("fly", 1), seat("fish", 1)])
    ok(False, "two seats on country 1 is refused")
except ValueError as e:
    ok("race" in str(e), "two seats on one country is refused: %s" % str(e)[:58])
try:
    Stage(FakeGame(), [Seat("fly", StubBrain(), enc, dec, 10.0, None)])
    ok(False, "a seat with no country is refused")
except ValueError as e:
    ok("no country" in str(e), "and a seat with no country at all")
try:
    Stage(FakeGame(), [])
    ok(False, "an empty stage is refused")
except ValueError as e:
    ok("nothing to show" in str(e), "as is a stage with no seats")

print("\n== ONE BROKEN BRAIN DOES NOT TAKE THE STAGE WITH IT ==")
g = FakeGame(3)
broken = seat("fish", 2, raises=RuntimeError("out of memory"))
st = Stage(g, [seat("fly", 1), broken, seat("worm", 3)])
while st.turn():
    pass
r = {x["species"]: x for x in st.report()}
ok(r["fly"]["turns"] == 3 and r["worm"]["turns"] == 3,
   "the working seats played every turn")
ok(r["fish"]["turns"] == 0, "the broken one took none")
ok(r["fish"]["faults"] == 3, "and its faults are counted, once per turn (%d)"
   % r["fish"]["faults"])
ok("out of memory" in (r["fish"]["first_fault"] or ""),
   "with the reason kept: %s" % r["fish"]["first_fault"])
ok(r["fly"]["faults"] == 0, "and the fault is not blamed on its neighbours")

print("\n== an encode naming a channel the brain lacks is a fault, not silence ==")
# The stimulus would otherwise go nowhere and the animal would look thoughtful.
def enc_wrong(game, country):
    return {"magnetic_field": 1.0}


g = FakeGame(2)
s = Seat("fly", StubBrain(), enc_wrong, dec, 10.0, country=1)
st = Stage(g, [s])
while st.turn():
    pass
ok(s.faults, "a channel the brain does not have is recorded")
ok("magnetic_field" in s.faults[0] and "does not have" in s.faults[0],
   "and the message names it: %s" % s.faults[0][:60])
ok(not g.given, "and no orders were given on a turn that failed")

print("\n== the wait is measured, because the viewer should see it ==")
g = FakeGame(2)
s = seat("fly", 1)
st = Stage(g, [s])
while st.turn():
    pass
rep = st.report()[0]
ok(rep["ms_per_turn"] is not None and rep["ms_per_turn"] >= 0,
   "wall-clock per turn is reported (%s ms)" % rep["ms_per_turn"])
ok(rep["spikes"] == 6, "and the spikes are totalled across turns (%d)" % rep["spikes"])

print("\n%d checks, %d failed" % (checks, fails))
sys.exit(1 if fails else 0)
