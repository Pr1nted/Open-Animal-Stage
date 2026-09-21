# Reddit

Three posts, one per subreddit, spaced out (not the same day). Drafts only:
nothing here has been posted. Replace `<URL>` with the itch page once it is live.

Read each subreddit's sidebar rules the day you post; the notes below are what
they were understood to be when this was written, and they change.

Rules that hold for all three:

- Post from Pr1nted's account and say in the post that you made it.
- Answer comments, especially the sceptical ones. The honest caveats are the
  interesting part; do not argue a critic into agreeing the fly is clever.
- The only benchmark result that may be quoted is the sentence in the posts
  below. No rankings of species, in the post or in replies.

---

## 1. r/neuroscience

**Why here.** The project's substance is the datasets and what can and cannot
honestly be done with them: mapping game state onto annotated sensory neurons,
a shuffled-wiring control, and a mouse that is only shown the map because a
patch of V1 has no motor output. This audience will check the credits and the
caveats, which is what the page is written for.

**Norms.** Low tolerance for hype and for "AI brain" framing. Self-promotion is
tolerated when it is substantive and the author engages. Use a text post (the
details matter more than the image); put the link in the body. Pick the
flair the sidebar asks for (content, or whatever the equivalent is that day).

**Title**

> I put published connectomes (FlyWire, MaleCNS, Fish1, Ciona, C. elegans) into a strategy game as simple LIF models, with a shuffled-wiring control. Notes on what that can and cannot show

**Body**

> I made a browser page where simplified models built on published wiring diagrams play a turn-based strategy game (Open Doctrines) against each other in one world. Link: <URL>
>
> What plays, and how:
>
> - Adult female fly (FlyWire 783, 138,639 neurons): the Shiu et al. 2024 LIF model, ported to JavaScript and matched spike for spike against the original.
> - Adult male fly (MaleCNS v1.0, 166,700 neurons), with the female's mapping and constants unchanged.
> - Zebrafish larva (Fish1, 187,052 somas), sea squirt larva (Ryan et al. 2016, 207 neurons, gap junctions kept separate), both C. elegans sexes (Cook et al. 2019, 302 and 385 neurons) and the fly larva (Winding et al. 2023, 2,952 neurons). The worms and the larva only run in a local copy: their data has no licence that allows redistribution.
> - Every species uses the same neuron model. Where there is no published model, one synaptic weight is set by a rule written before any game (match the female fly's breadth of motor activity under a fixed drive).
>
> Each turn, the game becomes four numbers (reward, harm, reserve, threat) that drive sensory neurons named from each dataset's own annotations, for 200 ms of simulated time. The motor set (descending neurons, or motor neurons) is dealt into the game's 39 action groups. That mapping is ours, written down before each species played, and it is where most of any seat's competence comes from.
>
> The caveats, which I think are the interesting part:
>
> - A stage with two animals on it compares two mappings I wrote, not two animals. The page never says one species beat another.
> - The fair comparison is an animal against its own wiring shuffled (activity-matched). With its real wiring the fly is more active and more aggressive than with shuffled wiring, and against the game's AI that loses land. That is the only result I am claiming.
> - Fish1's axons are mostly not yet attached to their cell bodies in the proofread data, so no path runs from a peripheral sense to a motor neuron. The fish senses through four brain nuclei instead, by a convention I chose on reachability, and the page shows it as a warning. The larva's sensory neurons are assumed cholinergic because only 243 of 2,952 neurons have a published transmitter.
> - The mouse (MICrONS) does not play. A cubic millimetre of visual cortex has no motor output, so seating it would mean inventing the rest of the animal. Instead, the world map is shown each turn to the MICrONS digital twin (Wang et al., Nature 2025), and the page draws what it predicts for 8,221 recorded neurons of that mouse.
> - None of these models learned anything, and none of them can feel anything. They are simplifications.
>
> Every dataset's citation and licence is on the page. I'd welcome corrections, especially on the sensory and motor choices per species.

---

## 2. r/webdev

**Why here, and not r/proceduralgeneration.** Nothing on the page is
procedurally generated in the sense that subreddit means. What it does have is
a web-engineering story: seven brain models in Web Workers, a C++ game compiled
to WebAssembly, and a recurrent vision model exported to ONNX and run on WebGPU,
all in a static page with no server.

**Norms.** Self-promotion only in the **Showoff Saturday** thread or as a
Saturday post with the Showoff Saturday flair; check the sidebar that week.
Technical detail is welcome; marketing is not. Lead with how it is built.

**Title**

> [Showoff Saturday] Several spiking brain models, a WASM strategy game and an ONNX vision model in one static page

**Body**

> Open Animal Stage: <URL>
>
> It is a zero-player page. Simplified models of real animal brains (from published connectomes: fruit flies, a zebrafish larva, a sea squirt larva; roundworms in a local copy) each play a country in the same game, turn by turn, and a model of a mouse's visual cortex is shown the map.
>
> How it is put together:
>
> - **One Web Worker per animal.** The brains differ by three orders of magnitude (302 to 187,052 cells), so one worker for the whole stage would spend every turn on the fish. Every brain runs 200 ms of its own simulated time per turn, and the page shows the wait instead of hiding it.
> - **The game is Open Doctrines' own engine, compiled to WebAssembly**, driven through its agent session with several seats in one world.
> - **The mouse is the MICrONS digital twin exported to ONNX** (34.9 MiB) and run with onnxruntime-web. Its recurrent state is lifted out into explicit inputs and outputs. On WebGPU with the state kept on the GPU it measured 94 ms per frame on an Apple-silicon Mac, against 322 ms on single-threaded WASM, with the output matching the PyTorch original to a relative error of 2.4e-6.
> - **The heavy data is the flies' wiring**: 91 MB for the female and 150 MB for the male. Some species cannot be served at all because their data has no redistribution licence, so the page lists them and says why.
>
> Caveat, since it comes up: none of the models learned to play and none of them is good at it. How game events become sensory input and how spikes become orders is my design, not biology.
>
> Happy to answer questions about the worker setup or the ONNX export.

---

## 3. r/StrategyGames

**Why here, and not r/incremental_games.** It is not an incremental game. It is
a grand strategy game with zero human players, and the people who care what the
AI in Open Doctrines does are in the strategy audience. The joke (a sea squirt larva
running a country) carries without any neuroscience background.

**Norms.** Self-promotion is limited (check the sidebar for a ratio or a
weekly thread). Posts that show gameplay do better than posts that pitch. It is
a spectator page, so say so in the title; nobody should click expecting to play.

**Title**

> Not a game you play: I let simulated animal brains (flies, a zebrafish larva, a sea squirt larva) run countries against each other in a grand strategy game

**Body**

> This is a spectator page, not a game you play. Link: <URL>
>
> Each seat in a game of Open Doctrines (a free browser grand strategy game) is run by a simplified model of a real animal's brain, built from its published wiring diagram. Every turn, what happened to its country (land won or lost, money, wars) is fed in as stimulation of its sensory neurons, the brain runs, and its most active motor neurons pick the orders: fund industry, build a fort, repress, conciliate, bombard.
>
> You pick who sits down (up to eight seats; the roundworms and the fly larva only run in a local copy, because their data cannot be redistributed), the map (or import your own .odmap), and whether each animal gets its real wiring or a shuffled copy. A mouse's visual cortex watches the map.
>
> Honest expectations: they are not good at it. None of them learned to play, and a pairing of two animals says more about how I wired each one to the game than about the animals. The one thing I will claim is that with its real wiring the fly is more active and more aggressive than with shuffled wiring, and against the game's AI that loses land.
>
> You will do better than any of them in the real game: <https://pr1nted.itch.io/open-doctrines>
