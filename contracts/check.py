"""Check a case folder against the contract.

Usage: python3 contracts/check.py [--timeline] <case_dir>

The contract is contracts/sample/: every CSV there must exist in the case
folder with exactly the same columns, in the same order. With --timeline,
analyze.timeline(case_dir) must also have the same shape as
contracts/timeline.json. Prints OK and exits 0, or prints each FAIL and exits 1.
"""
import csv
import json
import sys
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parent
ROOT = CONTRACTS.parent


def header(path):
    with open(path, newline="", encoding="utf-8") as f:
        return next(csv.reader(f), [])


def kind(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def shape_problem(got, want, path):
    """Return where got's shape first differs from want's, or None."""
    if isinstance(want, dict):
        if not isinstance(got, dict):
            return f"{path} is {kind(got)}, contract says object"
        if set(got) != set(want):
            return f"{path} keys {sorted(got)}, contract says {sorted(want)}"
        for key in want:
            problem = shape_problem(got[key], want[key], f"{path}.{key}")
            if problem:
                return problem
    elif isinstance(want, list):
        if not isinstance(got, list):
            return f"{path} is {kind(got)}, contract says list"
        if got and want:  # an empty list fits any list, e.g. a case with no incidents
            return shape_problem(got[0], want[0], f"{path}[0]")
    elif "null" not in (kind(got), kind(want)) and kind(got) != kind(want):
        return f"{path} is {kind(got)}, contract says {kind(want)}"
    return None


def check(case_dir, timeline=False):
    problems = []
    samples = sorted((CONTRACTS / "sample").glob("*.csv"))
    if not samples:
        problems.append("contracts/sample/ has no CSVs yet")
    for sample in samples:
        target = case_dir / sample.name
        if not target.exists():
            problems.append(f"missing {target}")
        elif header(target) != header(sample):
            problems.append(f"{target} columns {header(target)}, contract says {header(sample)}")
    if timeline:
        sys.path.insert(0, str(ROOT))
        import analyze
        want = json.loads((CONTRACTS / "timeline.json").read_text(encoding="utf-8"))
        problem = shape_problem(analyze.timeline(case_dir), want, "timeline")
        if problem:
            problems.append(problem)
    return problems


if __name__ == "__main__":
    args = sys.argv[1:]
    timeline = "--timeline" in args
    case_dir = Path([a for a in args if a != "--timeline"][0])
    problems = check(case_dir, timeline)
    for problem in problems:
        print("FAIL", problem)
    if problems:
        sys.exit(1)
    print("OK", case_dir, "matches the contract")
