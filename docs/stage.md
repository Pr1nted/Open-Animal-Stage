# The stage

Open Fly has one brain, one seat and one worker. Everything below is what
changes when there are several.

## Seats

Open Doctrines already runs a world of many countries, and its **agent session**
is how something outside the engine plays one of them — it is what Open Fly
drives. A stage with four animals on it is four agent seats in one world, each
fed by a different brain. Nothing in the game needs to change for this; the
game does not know what is on the other end of a seat.

Seats are taken by species with `"seat": true` in `data/roster.json`. Species
with `"station": true` and no seat are shown but do not play — the mouse is the
standing example, and the male fly may join it.

## Turn order

The game is turn-based, so the stage does not need brains to run at the same
time. Each turn:

1. The world advances to the next seat.
2. That seat's game state is encoded into its species' sensory neurons.
3. That brain runs for its own simulated duration.
4. Its motor neurons are decoded into orders.

This is Open Fly's loop with a seat index on the front. It means a stage is
correct before it is fast, which is the right order.

## THE ASYMMETRY THAT DECIDES THE ARCHITECTURE

A worm is 302 neurons. A fly is 138,639. A zebrafish is 187,053. They are not
the same amount of work by three orders of magnitude, and a page that runs them
one after another in a single worker will spend all its time on the fish while
the worm's turn is invisible.

Three things follow, and they should be settled before any of it is written:

- **One worker per animal**, not one worker for the stage. A stage of four is
  four workers, and a species' cost is then its own problem rather than
  everybody's.
- **Simulated time is the unit, not wall-clock.** Every brain runs for a stated
  duration of *its own* simulated time — Open Fly's fly runs 200 ms — and the
  page waits. A stage that gave every animal the same number of milliseconds of
  CPU would be comparing computers, not brains.
- **The page must show the wait.** If the fish takes four seconds of real time
  to think and the worm takes four milliseconds, hiding that behind a spinner
  tells the viewer something false about both. Show the clock.

## Fairness, and what it cannot be

There is no fair fight here and the design should not pretend otherwise.

The brains differ by three orders of magnitude in size. The mappings from game
to senses and from spikes to orders are ours, written separately per species,
and they are where nearly all the competence in a seat comes from. A stage that
declares a winner is declaring something about the mappings.

What the stage can honestly offer:

- **A species against a shuffled version of itself.** Same mapping, same size,
  same everything, with the connections permuted. This is the only opponent that
  holds our contribution fixed and varies the animal's own wiring, and it is the
  one comparison on this stage that means what it looks like it means.
- **A species against itself under two different mappings.** Which tells you
  about the mappings, and says so.
- **Everything else, as a spectacle**, labelled as one.

## Stations

Each species has a station in the room, in Open Fly's style — that page is a 3D
room with a free camera, the fly at a keyboard and its brain lit up beside it.
A fish gets a tank with a screen on the glass. A worm gets a dish under a lens.
The mouse gets a screen and no keyboard, which is the whole point of the mouse.

Stations are generated rather than hand-modelled, as Open Fly's are: a script in
`scene/` emits the geometry so a change to the roster does not need an artist.

## The pieces, and which exist

| Piece | State |
|---|---|
| Open Doctrines as WASM with an agent session | exists, Open Fly uses it |
| LIF brain core | exists, `open_fly/brain.py` |
| Fly encode / decode | exists, Open Fly |
| Multi-seat driver | **to write** |
| One worker per animal | **to write** |
| Per-species encode / decode | **to write, one per species** |
| Zebrafish model from Fish1 | **to write**, the largest piece |
| Shuffled-wiring control | **to write**, and it is the one that makes the stage worth anything |
| Stations | **to write**, generated |
