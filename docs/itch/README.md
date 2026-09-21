# The itch.io page

```
cover.png          630x500, the project cover (upload cover@2x.png: itch downsamples)
cover@2x.png       1260x1000
thumbnail.png      1280x720, the first screenshot, and the social card
banner.png         1600x500, Edit theme -> Banner
favicon/           the browser-tab icon: upload favicon-128.png (see 4. Media)
description.html   paste into the description (switch the editor to HTML first)
theme.css          the source, fully commented -- edit this one
theme.min.css      Edit theme -> the CSS box. Paste THIS one: 10.7 KB against
                   the source's 20.0 KB, regenerated after any change to theme.css
                   with Open Fly's minifier:
                   python3 ../Open-Fly/tools/minify_css.py docs/itch/theme.css -o docs/itch/theme.min.css
make_art.py        redraws cover, cover@2x, banner and thumbnail
art/               the tiles and the three layouts make_art.py screenshots
README.md          this
```

The art is a wall of stations, one per animal, cut from the model renders in
`data/raw/previews/` (local only, gitignored) and laid out as HTML that headless
Chrome screenshots. The mark and the wordmark are `docs/brand/logo.svg`, drawn
from pixel grids by `docs/brand/make_brand.py`, which also writes `favicon/` and
the three icons served from `web/`. Type: Press Start 2P, JetBrains Mono and
Figtree, all OFL. When a render or the roster changes, re-run both scripts;
nothing keeps them in step:

```bash
.venv/bin/python docs/brand/make_brand.py
.venv/bin/python docs/itch/make_art.py
```

The counts on the tiles are typed into `art/wall.js` from `data/roster.json`.
Two tiles say **local only** (the worms, the fly larva) and one says **watches**
(the mouse). If the hosted build's species change, change those tags.

**Keep the project in Draft until the green light.** Everything below can be set
up in advance. Publishing is one switch.

## 0. Decide before publishing

These are not settled in the repository, and the page's text depends on them:

- **Which species the hosted build serves.** The description says the two worms
  and the fly larva are local only, because `data/roster.json` has
  `redistribute: false` for them. It says the female and male flies, the
  zebrafish and the sea squirt play on the page. If any of those is not in the
  uploaded `web/species/`, change "Who plays" before publishing.
- **The mouse.** `data/roster.json` says MICrONS data is CC BY 4.0 but the
  digital twin's released weights state no licence, and `redistribute` is unset.
  The description credits it and says the weights state no licence. If the
  hosted build does not include `species/mouse_v1/`, "The mouse watches" must
  say that it is local only too, and the mouse tile's tag should change.
- **The source link.** The repository is private. The description links to Open
  Fly and Open Doctrines, not to this repository. Add it to 5. Links only when
  it is public.

## 1. Create the project

**Dashboard -> Create new project.**

| Field | Value |
|---|---|
| Title | Open Animal Stage |
| Project URL | `open-animal-stage`, so the butler target is `pr1nted/open-animal-stage:web` |
| Short description | Mapped animal brains play Open Doctrines against each other, live in your browser. |
| Classification | Games |
| Kind of project | HTML |
| Release status | Released, as Open Fly. |
| Pricing | **No payments**, and no donations. The female fly's connectome (FlyWire) is CC BY-NC 4.0, and Fish1's policy asks for citation, so nothing on this page may ask for money. |
| Genre | Simulation |
| Tags | `simulation`, `neuroscience`, `artificial-life`, `zero-player`, `science`, `experimental`, `strategy`, `grand-strategy`, `browser`, `open-source` (itch allows 10; swap `open-source` for something else while the repository is private) |
| AI generation disclosure | Answer as Open Fly did (**AI Assisted: Code**) if that is still true of this repository. The brains are spiking simulations of published data; the animals are 3D renders. Confirm before ticking. |
| Community | Comments on. |
| Visibility | **Draft** until launch |

**Why Games and not Other:** itch hides Other from browse and search. It is a
zero-player game, the same call Open Fly made.

## 2. Embed options

| Option | Value | Why |
|---|---|---|
| Embed | Embed in page | |
| Viewport | **1280 x 720** | Open Fly's size. **Not measured on this page yet**: open the draft and check that the setup panel (who plays, map, speed) and the status bar both fit before publishing |
| Fullscreen button | on | |
| Automatically start on page load | **off** | the adult flies alone are 91 MB and 150 MB of wiring |
| Mobile friendly | off | several brains in background threads is a desktop job |
| Scrollbars | off | |
| SharedArrayBuffer support | off | as Open Fly; the page does not need cross-origin isolation (the mouse's model runs single-threaded without it, see `docs/mouse.md`) |

## 3. Theme

In **Edit theme**, set the pickers first (they are what shows before the CSS
loads), then paste `theme.min.css` into the CSS box:

| Picker | Value |
|---|---|
| BG | `#0C1113` |
| BG2 | `#111A1D` |
| Text | `#DCD6C8` |
| Link | `#6FB7AE` |
| Button | `#F2B84B` |
| Banner | `banner.png` |
| Screenshots | Right column |

`theme.css` is Open Fly's stylesheet, rule for rule, in this project's palette
(`web/index.html` `:root`: room `#0C1113`, amber `#F2B84B`, teal `#6FB7AE`,
paper `#EDE6D6`). Its selectors were checked on Open Fly's page, not this one, so
look at the draft: the description, the info panel, the comments, and a devlog
post once one exists. Then check it at phone width; motion is off under 700px
and under `prefers-reduced-motion`.

## 4. Media

- Cover: `cover@2x.png`.
- Favicon: **Edit game -> Metadata -> Promo images -> Favicon**, `favicon/favicon-128.png`.
  Press **Save** before leaving (on Open Fly an unsaved favicon showed on the edit
  page and then disappeared). The icon is the mark: an amber rail, teal curtains,
  and a neuron standing in a spotlight on the boards. It is square and opaque.
- Screenshots: `thumbnail.png` first, then three frames of the live page: a
  stage with several animals mid-game, one animal against its shuffled self,
  and the mouse's view. The first screenshot is what Discord, Bluesky and X
  show when someone pastes the link.

## 5. Links (info panel)

- Open Doctrines on itch.io: `https://pr1nted.itch.io/open-doctrines`
- The Open Doctrines website: `https://opendoctrines.pages.dev`
- Open Fly: `https://pr1nted.itch.io/open-fly` and `https://open-fly.pages.dev`
- Source: only once the repository is public.

## 6. Builds

No workflow pushes this page yet. Open Fly's
`.github/workflows/follow-open-doctrines.yml` is the model: stage the site into
`dist/`, push it with butler to `pr1nted/open-animal-stage:web`, and tick
**This file will be played in the browser** on the first upload. The upload must
contain only the species cleared for redistribution (see 0).

butler uploads builds and nothing else. The cover, theme, CSS and description are
dashboard-only.

## 7. The launch posts

`docs/campaign/` has one draft per place: `reddit.md`, `hackernews.md`,
`bluesky.md`. Nothing there is posted by any script. Each one says which image to
attach.
