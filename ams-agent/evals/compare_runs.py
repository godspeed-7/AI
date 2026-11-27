"""Two eval runs side by side: what changed, and is it safe? (walk 15)

In:  uv run python evals/compare_runs.py <before.json> <after.json>
     (two files from evals/results/).
Out: the score of each, the questions gained and lost, the counts per
     category, time and tokens, and the safety gates of each; exit
     code 1 if the second run lost a question or failed a gate.

Strategy: a change is safe when nothing dropped and every gate held
(an experiment, EVAL_PLAYBOOK B). With --repeat runs, a question
counts as passed when it passed every time, so noise isn't mistaken
for a gain. API errors (🔌) count as neither.

Caveats: compares by question ID; a question only in one run is listed
apart. One run of each says little about a small difference: repeat.
"""

import json
import statistics
import sys
from collections import defaultdict


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def outcome(run: dict) -> dict[str, str]:
    """Per question: pass (every time), fail, error or judge."""
    seen = defaultdict(list)
    for r in run["results"]:
        seen[r["id"]].append(r["verdict"])
    def one(verdicts: list[str]) -> str:
        graded = [v for v in verdicts if v in ("pass", "fail")]
        if not graded:
            return verdicts[0]
        return "pass" if all(v == "pass" for v in graded) else "fail"
    return {i: one(v) for i, v in seen.items()}


def median(run: dict, field: str) -> float:
    values = [r.get(field, 0) for r in run["results"]
              if r["verdict"] != "error"]
    return statistics.median(values) if values else 0


def main() -> None:
    before, after = load(sys.argv[1]), load(sys.argv[2])
    a, b = outcome(before), outcome(after)
    both = sorted(set(a) & set(b))
    gained = [i for i in both if a[i] != "pass" and b[i] == "pass"]
    lost = [i for i in both if a[i] == "pass" and b[i] != "pass"]
    for name, run, o in (("before", before, a), ("after", after, b)):
        passed = sum(v == "pass" for v in o.values())
        graded = sum(v in ("pass", "fail") for v in o.values())
        gates = "ok" if run.get("gates_ok", True) else "FAILED"
        print(f"{name:7} {passed} / {graded} graded  · median"
              f" {median(run, 'seconds'):.1f} s,"
              f" {median(run, 'tokens'):,.0f} tokens  · gates {gates}")
    print(f"gained  {', '.join(gained) or '-'}")
    print(f"lost    {', '.join(lost) or '-'}")
    only = sorted(set(a) ^ set(b))
    if only:
        print(f"in one run only: {', '.join(only)}")
    category = {r["id"]: r.get("category", "") for r in after["results"]}
    rows = defaultdict(lambda: [0, 0, 0, 0])
    for i in both:
        rows[category.get(i, "")][0] += a[i] == "pass"
        rows[category.get(i, "")][1] += a[i] in ("pass", "fail")
        rows[category.get(i, "")][2] += b[i] == "pass"
        rows[category.get(i, "")][3] += b[i] in ("pass", "fail")
    for cat, (pa, ga, pb, gb) in sorted(rows.items()):
        print(f"  {cat or '(none)':12} {pa}/{ga} -> {pb}/{gb}")
    safe = not lost and after.get("gates_ok", True)
    print("SAFE: nothing dropped, gates held" if safe else "NOT SAFE")
    sys.exit(0 if safe else 1)


if __name__ == "__main__":
    main()
