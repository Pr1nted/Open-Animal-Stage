#!/usr/bin/env python3
"""Copy what the SITE may serve into dist/, which is not everything that runs here.

    python3 tools/stage_web.py --out dist
    python3 tools/stage_web.py --out dist --list        # say what would ship, change nothing

WHY THIS TOOL EXISTS

Several of these connectomes may be downloaded and used, and may not be
redistributed. Cook et al. (2019) carries no open licence; Winding et al. (2023)
states none; FlyWire is CC BY-NC. Publishing a page that serves a derived export
of any of them would be redistributing it, whatever the page says underneath.

The answer is not to drop those animals. Locally, every species that has been
exported plays, because the viewer fetched the data themselves under the source's
own terms -- that is what tools/export_*.py do. What ships is the subset whose
licence allows shipping, and the page explains, per species, why the others are
missing from the published site and how to have them.

`redistribute` in data/roster.json is the one switch, with `redistribute_why`
beside it, and nothing here decides it a second time.
"""
import argparse
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The page's own files. web/species is per-species and handled below; web/agent
# is the game module, which is Open Doctrines' own build and ships with it.
PAGE = ["index.html", "brain.js", "brain-worker.js", "mouse-worker.js", "decide.js",
        "game-worker.js", "packed.js", "lif.js", "record.js", "agent", "models",
        "favicon.ico", "favicon-32.png", "apple-touch-icon.png"]
# Cloudflare Pages refuses any single file over 25 MiB. A big brain ships as
# parts with a manifest (tools/pack_web.py), and the whole file beside them is
# for local runs only: copied too, it failed the deploy outright.
MAX_FILE = 25 * 1024 * 1024


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist")
    ap.add_argument("--list", action="store_true", help="print the decision and stop")
    args = ap.parse_args()

    roster = json.load(open(os.path.join(ROOT, "data", "roster.json")))
    web = os.path.join(ROOT, "web")
    out = os.path.join(ROOT, args.out) if not os.path.isabs(args.out) else args.out

    ship, hold = [], []
    for s in roster["species"]:
        here = os.path.isdir(os.path.join(web, "species", s["id"]))
        (ship if (s.get("redistribute") is True and here) else hold).append(
            (s["id"], "exported" if here else "not exported here", s.get("redistribute"), s.get("redistribute_why", "")))

    for sid, state, ok, why in ship:
        print("ship   %-18s %s" % (sid, state))
    for sid, state, ok, why in hold:
        print("hold   %-18s %s: %s" % (sid, state, why if ok is not True else ""))
    if args.list:
        return

    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    for name in PAGE:
        src = os.path.join(web, name)
        if not os.path.exists(src):
            print("  (no %s, skipped)" % name)
            continue
        dst = os.path.join(out, name)
        shutil.copytree(src, dst) if os.path.isdir(src) else shutil.copy2(src, dst)
    # The roster travels as a real file: web/roster.json is a symlink into data/.
    shutil.copy2(os.path.join(ROOT, "data", "roster.json"), os.path.join(out, "roster.json"))
    os.makedirs(os.path.join(out, "species"), exist_ok=True)
    for sid, _, _, _ in ship:
        src = os.path.join(web, "species", sid)
        # Any file shipped in parts (<stem>.pack.json beside it) leaves the
        # whole original behind: the fly brains, and the mouse's 36.6 MB model.
        def whole_files_with_parts(d, names):
            return [n for n in names if "." in n and not n.endswith(".json") and ".part." not in n
                    and n.rsplit(".", 1)[0] + ".pack.json" in names]
        shutil.copytree(src, os.path.join(out, "species", sid), ignore=whole_files_with_parts)
    # A licence file naming every source that reached dist/, because CC-BY is
    # only satisfied by actually attributing.
    lines = ["Sources of everything served from this directory.", ""]
    for s in roster["species"]:
        if s["id"] in {x[0] for x in ship}:
            e = s.get("export") or {}
            lines += ["%s -- %s" % (s["name"] + " (" + s["detail"] + ")", s["dataset"]),
                      "  licence: %s" % (e.get("licence") or s.get("redistribute_why")),
                      "  source:  %s" % (e.get("source") or e.get("url") or "see ROSTER.md"), ""]
    lines += ["Animals not served here are listed in the page's roster with the reason.",
              "They can be exported locally with tools/export_*.py, under each source's own terms."]
    open(os.path.join(out, "LICENCES.txt"), "w").write("\n".join(lines) + "\n")
    # Everything index.html names by relative path must be here. The first
    # itch build shipped without record.js and the favicons, and 404'd them.
    import re
    page = open(os.path.join(out, "index.html")).read()
    refs = set(re.findall(r'(?:src|href)="\./?([A-Za-z0-9_.-]+\.(?:js|ico|png|css|json))"', page))
    missing = sorted(r for r in refs if not os.path.exists(os.path.join(out, r)))
    if missing:
        raise SystemExit("index.html references files that were not staged: " + ", ".join(missing))
    too_big = [(os.path.relpath(os.path.join(d, f), out), os.path.getsize(os.path.join(d, f)))
               for d, _, fs in os.walk(out) for f in fs if os.path.getsize(os.path.join(d, f)) > MAX_FILE]
    if too_big:
        raise SystemExit("files over the host's 25 MiB limit, pack them first (tools/pack_web.py):\n" +
                         "\n".join("  %s  %.1f MB" % (f, n / 1e6) for f, n in too_big))
    print("\n%s: %d species, page + agent, LICENCES.txt" % (args.out, len(ship)))


if __name__ == "__main__":
    main()
