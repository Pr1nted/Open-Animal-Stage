#!/usr/bin/env bash
# Every test in this repository. No build step: it is Python and a static page.
#
#   tests/run_all.sh
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
fail=0
for t in "$root"/tests/test_*.py; do
    printf '\n=== %s ===\n' "$(basename "$t" .py)"
    python3 "$t" || fail=1
done

printf '\n=== the roster is valid and agrees with itself ===\n'
python3 - "$root" <<'PY' || fail=1
import json, re, sys, os
root = sys.argv[1]
d = json.load(open(os.path.join(root, "data", "roster.json")))
ids = [s["id"] for s in d["species"]]
bad = 0
if len(ids) != len(set(ids)):
    print("  FAIL  duplicate ids"); bad = 1
for s in d["species"]:
    # A species that cannot take a seat must say why, in the file, not in a
    # commit message somebody has to go looking for.
    if s["seat"] is False and not s.get("why_no_seat"):
        print("  FAIL  %s has no seat and no reason given" % s["id"]); bad = 1
    if s["status"] == "verify" and not s.get("blocker"):
        print("  FAIL  %s is unverified and does not say what to check" % s["id"]); bad = 1
md = open(os.path.join(root, "ROSTER.md")).read()
for s in d["species"]:
    if s["dataset"] not in md:
        print("  FAIL  %s: dataset %r is in the data and not in ROSTER.md"
              % (s["id"], s["dataset"])); bad = 1
if not bad:
    print("  ok    %d species, every unseated one gives a reason, "
          "every dataset is documented" % len(ids))
sys.exit(bad)
PY

printf '\n'
[ $fail -eq 0 ] && echo "ALL PASSED" || echo "SOMETHING FAILED"
exit $fail
