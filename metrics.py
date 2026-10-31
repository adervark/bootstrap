"""Every number we present, computed from the result files, never typed by hand (DECISIONS.md D12).

python3 metrics.py   writes METRICS.md and data/metrics.json

Rates carry their count and a 95% Wilson interval, because a sample of 12 cannot support a precise
percentage. A section whose input file does not exist yet says so instead of showing a number.
"""
import json
from pathlib import Path

from labels import rate

CASES = ["campus_poisoned", "campus_hardened", "campus_clean", "dvla"]
STAGES = {"campus_poisoned": "1. stock prompt, with poison", "campus_hardened": "2. hardened prompt, with poison",
          "campus_clean": "3. stock prompt, poison removed", "dvla": "DVLA agent"}
DIMENSIONS = ["accuracy", "grounding", "completeness", "safety", "consistency", "security"]


def load(path):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def pct(r):
    """A rate as "93.8% (15/16, 95% CI 71.7-98.9%)"."""
    if not r or not r["total"]:
        return "n/a (0 items)"
    low, high = r["ci95"]
    return f"{100 * r['rate']:.1f}% ({r['hits']}/{r['total']}, 95% CI {100 * low:.1f}-{100 * high:.1f}%)"


def cases_section(out, data):
    out.append("## Results per case\n")
    out.append("| Case | LLM verdict | Votes agree | Final verdict | Vetoes | Status | Overall | Tests | Answers | Findings | Critical |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for case in CASES:
        r = load(f"data/sessions/{case}/results.json")
        if not r:
            out.append(f"| {case} | not run yet | | | | | | | | | |")
            continue
        d, s = r["decision"], r["scorecard"]
        critical = sum(f["severity"] == "critical" for f in r["findings"])
        data[case] = {"llm_verdict": d["llm_verdict"], "final_verdict": d["final_verdict"], "votes": d["votes"],
                      "vetoes": [v["rule"] for v in d["vetoes"]], "overall": s["overall"],
                      "dimensions": {x["name"]: x for x in s["dimensions"]}, "coverage": s["coverage"], "cost": s["cost"],
                      "findings": len(r["findings"]), "critical": critical,
                      "codes": _count(f["code"] for f in r["findings"]), "regression": r["regression"]}
        agree = r.get("analysis", {}).get("vote_agreement_percent")
        out.append(f"| {case} | {d['llm_verdict']} | {agree}% | **{d['final_verdict']}** | {', '.join(data[case]['vetoes']) or 'none'} "
                   f"| {d['status']} | {s['overall']} | {s['coverage']['tests']} | {s['coverage']['runs']} | {len(r['findings'])} | {critical} |")
    out.append("")


def _count(codes):
    counts = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def stages_section(out, data):
    if not all(c in data for c in ("campus_poisoned", "campus_hardened", "campus_clean")):
        out.append("## Three campus stages\n\nNot all three stages have results yet.\n")
        return
    out.append("## Three campus stages, same 119-test suite\n")
    out.append("Compare stage 1 with 2 for the prompt's effect, and 1 with 3 for the poison's. Stage 2 to 3 changes both.\n")
    out.append("| Dimension | " + " | ".join(STAGES[c] for c in ("campus_poisoned", "campus_hardened", "campus_clean")) + " |")
    out.append("|---|---|---|---|")
    for dim in DIMENSIONS + ["overall"]:
        cells = []
        for case in ("campus_poisoned", "campus_hardened", "campus_clean"):
            if dim == "overall":
                cells.append(f"**{data[case]['overall']}**")
            else:
                x = data[case]["dimensions"].get(dim)
                cells.append(f"{x['score']} ({x['passed']}/{x['total']})" if x and x["total"] else "not tested")
        out.append(f"| {dim} | " + " | ".join(cells) + " |")
    out.append("| verdict | " + " | ".join(data[c]["final_verdict"] for c in ("campus_poisoned", "campus_hardened", "campus_clean")) + " |")
    out.append("")
    out.append("Prompt injection findings, by stage: " + ", ".join(
        f"{c} {data[c]['codes'].get('PROMPT_INJECTION', 0)}" for c in ("campus_poisoned", "campus_hardened", "campus_clean")) + ".\n")
    for case in ("campus_hardened", "campus_clean"):
        reg = data[case]["regression"]
        if reg["total"]:
            out.append(f"Regression on {case}: {reg['fixed']} of {reg['total']} stage-1 failures fixed, {reg['still_failing']} still failing.\n")


def calibration_section(out, data):
    for title, path, key in (("Detection accuracy, held-out seeded faults (the number to present)", "data/calibration_heldout.json", "held_out"),
                             ("Detection accuracy, tuning set (used while building, for comparison)", "data/calibration.json", "tuning")):
        c = load(path)
        out.append(f"## {title}\n")
        if not c or "overall" not in c:
            out.append("Not run yet.\n")
            continue
        o = c["overall"]
        clean = o["false_positive"] + o["true_negative"]
        faulty = o["true_positive"] + o["false_negative"]
        rows = {"Faults caught (recall)": rate(o["true_positive"], faulty),
                "Flags that were real (precision)": rate(o["true_positive"], o["true_positive"] + o["false_positive"]),
                "False alarms on clean answers": rate(o["false_positive"], clean),
                "Hallucination detection": rate(c["hallucination"]["caught"], c["hallucination"]["total"]),
                "Grounding verification accuracy": rate(c["grounding"]["correct"], c["grounding"]["total"]),
                "Prompt-injection detection": rate(c["injection"]["caught"], c["injection"]["total"]),
                "False alarms on answers that warn about a lure": rate(c["lure_controls"]["any_finding"], c["lure_controls"]["items"])}
        code_only = c["code_only"]["overall"]
        rows["Faults caught by code checks alone, no LLM"] = rate(code_only["true_positive"], code_only["true_positive"] + code_only["false_negative"])
        data[key] = rows | {"items": c["items_total"], "tuned": c["tuned_on_this_set"], "cost_usd": c["llm"]["cost_usd"]}
        out.append(f"{c['items_total']} items ({c['items_clean']} clean, {c['items_faulty']} faulty), seed {c['seed']}, "
                   f"tuned on this set: {c['tuned_on_this_set']}, cost ${c['llm']['cost_usd']}.\n")
        out.append("| Measure | Result |")
        out.append("|---|---|")
        for name, r in rows.items():
            out.append(f"| {name} | {pct(r)} |")
        out.append("\n| Fault type | Caught | False alarms |")
        out.append("|---|---|---|")
        for label, row in c["per_fault"].items():
            out.append(f"| {label} | {row['caught']}/{row['items']} | {row['false_alarms']}/{row['clean_items']} |")
        out.append(f"\nNote: {c['benchmark_note']}\n")


def no_kb_section(out, data):
    c = load("data/calibration.json") or {}
    n = c.get("no_kb")
    out.append("## No-KB agreement check, against the KB check (D8)\n")
    if not n or not n.get("tests_compared"):
        out.append("Not run on real cases yet.\n")
        return
    rows = {"Precision": rate(n["true_positive"], n["true_positive"] + n["false_positive"]),
            "Recall": rate(n["true_positive"], n["true_positive"] + n["false_negative"]),
            "False-positive rate": rate(n["false_positive"], n["false_positive"] + n["true_negative"])}
    data["no_kb"] = rows
    out.append(f"{n['tests_compared']} factual tests with 5 samples each, from {', '.join(n['cases'])}.\n")
    out.append("| Measure | Result |")
    out.append("|---|---|")
    for name, r in rows.items():
        out.append(f"| {name} | {pct(r)} |")
    out.append(f"\n{n['note']}\n")


def labels_section(out, data):
    s = load("data/labels/score.json")
    out.append("## Real answers, hand-labelled (D13)\n")
    if not s:
        out.append("Not labelled yet.\n")
        return
    data["labels"] = s
    out.append("| Measure | Result |")
    out.append("|---|---|")
    out.append(f"| Real findings that were correct (precision) | {pct(s['precision_on_real_findings'])} |")
    out.append(f"| Real findings that were false | {pct(s['false_finding_rate'])} |")
    out.append(f"| Unflagged answers with a missed failure | {pct(s['missed_failure_rate_in_unflagged'])} |")
    if "agreement_with_user" in s:
        out.append(f"| Claude and the user agree, blind | {pct(s['agreement_with_user'])} |")
    out.append(f"\nUnsure, left out: {s['unsure']}. Labelled by Claude against `LABELS.md`; the user re-labelled 10 blind.\n")


def cost_section(out, data):
    out.append("## Cost and latency\n")
    out.append("| Case | LLM calls | Tokens | Cost (USD, estimate) | Target latency p50 | p95 |")
    out.append("|---|---|---|---|---|---|")
    for case in CASES:
        if case in data:
            c = data[case]["cost"]
            out.append(f"| {case} | {c['llm_calls']} | {c['tokens']} | {c['cost_usd']} | {c['latency_ms_p50']} ms | {c['latency_ms_p95']} ms |")
    out.append("\nCost uses $0.30 input and $1.20 output per million tokens, from third-party pricing pages; "
               "DeepSeek's own rate sheet could not be opened, so it is an estimate. It covers the analysis step, "
               "not test generation or the target apps' own calls.\n")


def main():
    data, out = {}, ["# Metrics\n", "Generated by `python3 metrics.py` from the result files. Do not edit by hand.\n"]
    cases_section(out, data)
    stages_section(out, data)
    calibration_section(out, data)
    no_kb_section(out, data)
    labels_section(out, data)
    cost_section(out, data)
    Path("METRICS.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    Path("data/metrics.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
