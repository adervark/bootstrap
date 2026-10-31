"""Real-answer labels (DECISIONS.md D13, rubric in LABELS.md).

  python3 labels.py sample   draw 30 findings and 30 unflagged answers into data/labels/
  python3 labels.py score    precision, missed failures and agreement, with 95% Wilson intervals

items.csv has an empty `label` and `reason` per item for Claude to fill. blind.csv holds 10 of
the same items without those columns, for the user to label in `user_label`.
"""
import csv
import json
import math
import random
import sys
from pathlib import Path

import store

CASES = ["campus_poisoned", "campus_hardened", "campus_clean", "dvla"]
OUT = Path("data/labels")
COLUMNS = ["item", "kind", "case", "test_id", "run_id", "code", "check", "evidence", "prompt", "answer",
           "sources", "label", "reason"]


def wilson(hits, total, z=1.96):
    """The 95% Wilson interval for hits out of total, as (low, high); (None, None) when total is 0."""
    if not total:
        return None, None
    p = hits / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)


def rate(hits, total):
    low, high = wilson(hits, total)
    return {"hits": hits, "total": total, "rate": round(hits / total, 3) if total else None, "ci95": [low, high]}


def read(path):
    return store.read_csv(path)


def sample():
    findings, clean = [], []
    for case in CASES:
        folder = Path("data/sessions", case)
        results = store.results(folder)
        runs = {row["run_id"]: row for row in read(folder / "runs.csv")}
        tests = {row["test_id"]: row for row in read(folder / "tests.csv")}
        flagged_runs = {f["run_id"] for f in results["findings"]}
        for f in results["findings"]:
            run = runs.get(f["run_id"], {})
            findings.append({"kind": "flagged", "case": case, "test_id": f["test_id"], "run_id": f["run_id"],
                             "code": f["code"], "check": f["check"], "evidence": f["evidence"],
                             "prompt": tests.get(f["test_id"], {}).get("prompt", ""), "answer": run.get("answer", ""),
                             "sources": ", ".join(s["id"] for s in json.loads(run.get("sources") or "[]"))})
        for run_id, run in runs.items():
            if run_id not in flagged_runs and not run["error"]:
                clean.append({"kind": "unflagged", "case": case, "test_id": run["test_id"], "run_id": run_id,
                              "code": "", "check": "", "evidence": "", "prompt": tests.get(run["test_id"], {}).get("prompt", ""),
                              "answer": run["answer"], "sources": ", ".join(s["id"] for s in json.loads(run["sources"] or "[]"))})
    rng = random.Random(13)
    items = rng.sample(findings, min(30, len(findings))) + rng.sample(clean, min(30, len(clean)))
    for number, item in enumerate(items, 1):
        item.update(item=f"L-{number:02d}", label="", reason="")
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "items.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, COLUMNS)
        writer.writeheader()
        writer.writerows(items)
    blind = rng.sample(items, 10)
    with open(OUT / "blind.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, [c for c in COLUMNS if c not in ("label", "reason")] + ["user_label"])
        writer.writeheader()
        writer.writerows([{k: v for k, v in item.items() if k not in ("label", "reason")} | {"user_label": ""} for item in blind])
    print(f"{len(findings)} findings and {len(clean)} unflagged answers in all; sampled {len(items)}, blind {len(blind)}")


def score():
    items = read(OUT / "items.csv")
    flagged = [i for i in items if i["kind"] == "flagged" and i["label"] in ("true", "false")]
    unflagged = [i for i in items if i["kind"] == "unflagged" and (i["label"] == "clean" or i["label"].startswith("missed"))]
    result = {
        "precision_on_real_findings": rate(sum(i["label"] == "true" for i in flagged), len(flagged)),
        "false_finding_rate": rate(sum(i["label"] == "false" for i in flagged), len(flagged)),
        "missed_failure_rate_in_unflagged": rate(sum(i["label"].startswith("missed") for i in unflagged), len(unflagged)),
        "unsure": sum(i["label"] == "unsure" for i in items),
        "false_findings": [{k: i[k] for k in ("item", "case", "code", "reason")} for i in flagged if i["label"] == "false"],
        "missed": [{k: i[k] for k in ("item", "case", "label", "reason")} for i in unflagged if i["label"].startswith("missed")],
    }
    blind_path = OUT / "blind.csv"
    if blind_path.exists():
        mine = {i["item"]: i["label"] for i in items}
        theirs = [b for b in read(blind_path) if b["user_label"].strip()]
        same = sum(1 for b in theirs if b["user_label"].strip().split()[0] == mine.get(b["item"], "").split()[0])
        result["agreement_with_user"] = rate(same, len(theirs))
        result["disagreements"] = [{"item": b["item"], "claude": mine.get(b["item"]), "user": b["user_label"]}
                                   for b in theirs if b["user_label"].strip().split()[0] != mine.get(b["item"], "").split()[0]]
    (OUT / "score.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    {"sample": sample, "score": score}[sys.argv[1]]()
